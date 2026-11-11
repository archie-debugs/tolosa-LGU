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


def open_users_page(monkeypatch, extra=()):
    reset_db()
    with SessionLocal() as db:
        office_id = db.query(models.Office.id).scalar()
        for username, role, permissions, in_office in extra:
            db.add(models.User(username=username, hashed_password="x", role=role, full_name=username.title(), email=f"{username}@example.com",
                               permissions=str(permissions), status="Active", is_active=True, office_id=office_id if in_office else None))
        db.commit()
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


BASE = ["View Documents", "Search Documents", "Filter Documents", "View Document Details", "Download Documents", "Print Documents"]
BASE_KEYS = ["download_documents", "filter_documents", "print_documents", "search_documents", "view_document_details", "view_documents"]


def test_create_user_starts_with_only_the_basic_document_permissions_on_and_saves_what_was_turned_on(monkeypatch):
    page = open_users_page(monkeypatch)
    click(button(page.controls[0], "Create User"))
    form = dialog(page)

    listed = switches(form)
    assert "Register Documents" in listed and "View Users" in listed
    # The basic document permissions are on and can't be switched off; nothing else is on.
    assert all(listed[label].value and listed[label].disabled for label in BASE)
    assert not any(switch.value for label, switch in listed.items() if label not in BASE)
    assert "Add new documents and upload their files." in texts(form)

    fire(listed["Register Documents"], "on_change", True)
    fields = [c for c in walk(form) if isinstance(c, ft.TextField)]
    for field, value in zip(fields, ["New Clerk", "newclerk", "new@example.com", "longenough", "longenough"]):
        field.value = value
    click(button(form, "Create Account"))

    assert saved_permissions("newclerk") == sorted(BASE_KEYS + ["register_documents"])


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
    assert saved_permissions("clerk") == sorted(set(office) | set(BASE_KEYS) | {"delete_documents", "register_documents"})


def dropdown(page, name):
    return next(c for c in walk(page.controls[0]) if isinstance(c, ft.Dropdown) and c.data == name)


def listed_usernames(page):
    table = next(c for c in walk(page.controls[0]) if isinstance(c, ft.DataTable) and c.rows and "Username" in texts(c.columns[2].label))
    return [texts(row.cells[2].content)[0] for row in table.rows]


def test_the_user_table_shows_10_at_a_time_and_filters_by_office_user_and_permission(monkeypatch):
    extra = [("desk", "Employee", ["scan_qr", "pass_office_documents"], True)]
    extra += [(f"emp{number:02}", "Employee", BASE_KEYS, False) for number in range(12)]
    page = open_users_page(monkeypatch, extra)

    assert len(listed_usernames(page)) == 10 and "Showing 10 of 15 users" in texts(page.controls[0])
    fire(dropdown(page, "Show"), "on_change", "All")
    assert len(listed_usernames(page)) == 15

    fire(dropdown(page, "Role"), "on_change", "Office User")
    assert listed_usernames(page) == ["desk"]
    assert "Office User" in [c.value for c in walk_tables(page.controls[0]) if isinstance(c, ft.Text)]
    fire(dropdown(page, "Role"), "on_change", "All")

    # Accounts store permission keys; the filter matches them by label. Typing in it shows the text.
    permission = dropdown(page, "Permission")
    assert permission.editable and permission.enable_filter
    fire(permission, "on_change", "Delete Documents")
    assert listed_usernames(page) == ["clerk"]


def test_an_office_user_can_only_be_given_office_permissions(monkeypatch):
    page = open_users_page(monkeypatch, [("desk", "Employee", ["scan_qr"], True)])
    row = next(r for c in walk_tables(page.controls[0]) for r in getattr(c, "rows", None) or []
               if "desk" in [t for cell in r.cells for t in texts(cell.content)])
    next(c for cell in row.cells for c in walk(cell.content) if isinstance(c, ft.PopupMenuItem) and texts(c) == ["Edit"]).on_click(None)
    form = dialog(page)

    listed = switches(form)
    assert "Register Documents" not in listed and "View Documents" not in listed and listed["Scan QR"].value
    office = next(c for c in walk(form) if isinstance(c, ft.Dropdown) and c.value == "Records Office")
    assert "Unassigned" not in [option.key or option.text for option in office.options]
    fire(listed["Pass Office Documents"], "on_change", True)
    click(button(dialog(page), "Save Changes"))
    assert saved_permissions("desk") == ["pass_office_documents", "scan_qr"]

    # The backend refuses employee permissions for an office user too.
    client = TestClient(main.app)
    with SessionLocal() as db:
        desk = db.query(models.User).filter_by(username="desk").one()
        desk_id, office_id = desk.id, desk.office_id
    token = client.post("/auth/login", data={"username": "admin", "password": "pw123"}).json()["access_token"]
    refused = client.put(f"/auth/users/{desk_id}", headers={"Authorization": f"Bearer {token}"}, json={
        "full_name": "Desk", "username": "desk", "email": "desk@example.com", "role": "Employee", "status": "Active",
        "office_id": office_id, "permissions": ["scan_qr", "register_documents"],
    })
    assert refused.status_code == 400 and "office permissions" in refused.json()["detail"]
