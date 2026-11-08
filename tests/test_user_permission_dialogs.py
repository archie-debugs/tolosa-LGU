"""Create User Account and Edit User choose permissions with one list of switches."""

import ast
from types import SimpleNamespace

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

import frontend.admin.app as admin_app  # also applies the flet compatibility shims
import flet as ft

from tests.test_account_menu_ui import click, clickable, texts, walk
from tests.test_session_revocation import AppPage, BackendSession, login, sidebar_tile

models.Base.metadata.create_all(bind=engine)


def reset_db():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.add(models.Office(name="Records Office", office_code="REC"))
        db.add(models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                           permissions="['*']", status="Active", is_active=True, full_name="Admin", email="admin@example.com"))
        db.add(models.User(username="clerk", hashed_password=get_password_hash("pw123"), role="Employee", full_name="Clerk",
                           email="clerk@example.com", permissions="['view_documents', 'delete_documents']", status="Active", is_active=True))
        db.commit()


def fire(control, event_name, value=None):
    if value is not None:
        control.value = value
    handler = getattr(control, event_name)
    event = SimpleNamespace(control=control, data=value)
    if callable(handler):
        handler(event)
    else:
        for fn in list(handler._EventHandler__handlers):
            fn(event)


def open_users_page(monkeypatch):
    reset_db()
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    page = AppPage()
    admin_app.main(page, session=login(TestClient(main.app), "admin"))
    click(sidebar_tile(page, "Users & Roles"))
    return page


def dialog(page):
    return [control for control in page.overlay if isinstance(control, ft.AlertDialog) and control.open][-1]


def switches(root):
    """{permission label: switch}: each switch sits beside its label and description."""
    found = {}
    for row in walk(root):
        if isinstance(row, ft.Row) and row.controls and isinstance(row.controls[0], ft.Switch):
            found[texts(row)[0]] = row.controls[0]
    return found


def button(root, label):
    return next(c for c in walk(root) if label in texts(c) and clickable(c) or getattr(c, "text", None) == label)


def saved_permissions(username):
    with SessionLocal() as db:
        return ast.literal_eval(db.query(models.User).filter_by(username=username).one().permissions)


def test_create_user_starts_with_nothing_on_and_saves_only_what_was_turned_on(monkeypatch):
    page = open_users_page(monkeypatch)
    click(button(page.controls[0], "Create User"))
    form = dialog(page)

    listed = switches(form)
    assert "Register Documents" in listed and "View Users" in listed
    assert not any(switch.value for switch in listed.values())
    assert "Add new documents and upload their files." in texts(form)

    fire(listed["Register Documents"], "on_change", True)
    fields = [c for c in walk(form) if isinstance(c, ft.TextField)]
    for field, value in zip(fields, ["New Clerk", "newclerk", "new@example.com", "longenough", "longenough"]):
        field.value = value
    click(button(form, "Create Account"))

    assert saved_permissions("newclerk") == ["register_documents"]


def test_choosing_an_office_adds_office_permissions_all_on_above_the_general_ones(monkeypatch):
    page = open_users_page(monkeypatch)
    click(button(page.controls[0], "Create User"))
    form = dialog(page)
    office = next(c for c in walk(form) if isinstance(c, ft.Dropdown) and c.value == "Unassigned")

    fire(office, "on_change", "Records Office")

    listed = switches(dialog(page))
    office = ["View Office Documents", "Search Office Documents", "View Office Document Details", "Scan QR",
              "Pass Office Documents", "Confirm Document Receipt", "View Office History"]
    assert list(listed)[:len(office)] == office
    assert all(listed[label].value for label in office)
    assert "Register Documents" in listed and not listed["Register Documents"].value


def walk_tables(control):
    """walk, also into DataTable rows and cells."""
    for item in walk(control):
        yield item
        for row in getattr(item, "rows", None) or []:
            for cell in row.cells:
                yield from walk_tables(cell.content)


def test_edit_user_keeps_general_permissions_when_an_office_is_assigned(monkeypatch):
    page = open_users_page(monkeypatch)
    row = next(r for c in walk_tables(page.controls[0]) for r in getattr(c, "rows", None) or []
               if "clerk" in [t for cell in r.cells for t in texts(cell.content)])
    edit = next(c for cell in row.cells for c in walk(cell.content) if isinstance(c, ft.PopupMenuItem) and texts(c) == ["Edit"])
    edit.on_click(None)
    form = dialog(page)

    listed = switches(form)
    assert listed["View Documents"].value and listed["Delete Documents"].value and not listed["Register Documents"].value

    office = next(c for c in walk(form) if isinstance(c, ft.Dropdown) and c.value == "Unassigned")
    fire(office, "on_change", "Records Office")
    assert not any("Saving removes permissions" in text for text in texts(dialog(page)))
    listed = switches(dialog(page))
    assert listed["Pass Office Documents"].value and not listed["Register Documents"].value
    fire(listed["Register Documents"], "on_change", True)

    click(button(dialog(page), "Save Changes"))
    office = ["view_office_documents", "search_office_documents", "view_office_document_details", "scan_qr",
              "pass_office_documents", "confirm_document_receipt", "view_office_history"]
    assert saved_permissions("clerk") == sorted(set(office) | {"view_documents", "delete_documents", "register_documents"})
