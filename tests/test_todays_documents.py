import os
from datetime import timedelta

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

import Backends.backend.database as database
import Backends.backend.main as main
import Backends.backend.schema as schema
from Backends.SBmem_backend.main import app as sb_member_app
from Backends.backend import models
from Backends.backend.core import DEFAULT_ROLE_PERMISSIONS, get_password_hash, lgu_today, validate_permissions
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


def reset_db():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.add_all([
            models.User(username="secretariat", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions="['view_documents', 'set_documents_for_sb_members']", status="Active", is_active=True),
            models.User(username="clerk", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions="['view_documents']", status="Active", is_active=True),
            models.User(username="member", hashed_password=get_password_hash("pw123"), role="SB Member",
                        permissions="['view_documents']", status="Active", is_active=True),
        ])
        docs = [
            models.Document(tracking_number=f"DOC-00000{index}", title=title, status="Approved", priority="Medium", qr_token=f"token-{index}")
            for index, title in enumerate(["Budget ordinance", "Road resolution", "Market ordinance"], start=1)
        ]
        docs.append(models.Document(tracking_number="DOC-000009", title="Old archived", status="Approved", priority="Medium", qr_token="token-9", archived=True))
        db.add_all(docs)
        db.commit()
        return {doc.title: doc.id for doc in docs}


def headers_for(username):
    response = TestClient(main.app).post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def add(client, headers, document_id, day=None, note=None):
    payload = {"scheduled_for": (day or lgu_today()).isoformat(), "document_id": document_id}
    if note is not None:
        payload["note"] = note
    return client.post("/todays-documents", json=payload, headers=headers)


def test_documents_set_by_an_employee_appear_for_sb_members_in_order():
    ids = reset_db()
    client = TestClient(main.app)
    employee = headers_for("secretariat")
    assert add(client, employee, ids["Road resolution"], note="For second reading").status_code == 200
    assert add(client, employee, ids["Budget ordinance"]).status_code == 200
    assert add(client, employee, ids["Market ordinance"], day=lgu_today() + timedelta(days=1)).status_code == 200

    response = TestClient(sb_member_app).get("/todays-documents", headers=headers_for("member"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date"] == lgu_today().isoformat()
    assert [item["title"] for item in body["items"]] == ["Road resolution", "Budget ordinance"]
    assert body["items"][0]["note"] == "For second reading"


def test_employees_can_reorder_and_remove_entries():
    ids = reset_db()
    client = TestClient(main.app)
    employee = headers_for("secretariat")
    first = add(client, employee, ids["Budget ordinance"]).json()
    second = add(client, employee, ids["Road resolution"]).json()

    reordered = client.put("/todays-documents/order", json={"scheduled_for": lgu_today().isoformat(), "entry_ids": [second["id"], first["id"]]}, headers=employee)
    assert reordered.status_code == 200, reordered.text
    assert [item["document"]["title"] for item in reordered.json()["items"]] == ["Road resolution", "Budget ordinance"]

    assert client.delete(f"/todays-documents/{second['id']}", headers=employee).status_code == 200
    listing = client.get("/todays-documents", headers=employee).json()
    assert [item["document"]["title"] for item in listing["items"]] == ["Budget ordinance"]
    with SessionLocal() as db:
        actions = {row.action for row in db.query(models.AuditLog).filter(models.AuditLog.action.like("TODAYS_DOCUMENT_%"))}
    assert actions == {"TODAYS_DOCUMENT_ADDED", "TODAYS_DOCUMENT_REMOVED"}


def test_invalid_entries_are_rejected():
    ids = reset_db()
    client = TestClient(main.app)
    employee = headers_for("secretariat")
    assert add(client, employee, ids["Budget ordinance"]).status_code == 200

    assert add(client, employee, ids["Budget ordinance"]).status_code == 409
    assert add(client, employee, ids["Old archived"]).status_code == 400
    assert add(client, employee, ids["Road resolution"], day=lgu_today() - timedelta(days=1)).status_code == 400
    assert add(client, employee, 999999).status_code == 404
    partial_order = client.put("/todays-documents/order", json={"scheduled_for": lgu_today().isoformat(), "entry_ids": []}, headers=employee)
    assert partial_order.status_code == 400


def test_archiving_a_set_document_hides_it_from_sb_members():
    ids = reset_db()
    assert add(TestClient(main.app), headers_for("secretariat"), ids["Budget ordinance"]).status_code == 200
    with SessionLocal() as db:
        db.query(models.Document).filter_by(id=ids["Budget ordinance"]).update({"archived": True})
        db.commit()

    response = TestClient(sb_member_app).get("/todays-documents", headers=headers_for("member"))

    assert response.json()["items"] == []


def test_only_permitted_employees_manage_the_list():
    ids = reset_db()
    client = TestClient(main.app)

    assert add(client, headers_for("clerk"), ids["Budget ordinance"]).status_code == 403
    assert add(client, headers_for("member"), ids["Budget ordinance"]).status_code == 403
    assert client.get("/todays-documents", headers=headers_for("clerk")).status_code == 403


def test_sb_members_cannot_manage_the_list_even_if_granted_the_permission():
    ids = reset_db()
    with SessionLocal() as db:
        db.query(models.User).filter_by(username="member").update(
            {"permissions": "['view_documents', 'set_documents_for_sb_members', '*']"}
        )
        db.commit()
    client = TestClient(main.app)
    member = headers_for("member")
    entry = add(client, headers_for("secretariat"), ids["Budget ordinance"]).json()

    assert add(client, member, ids["Road resolution"]).status_code == 403
    assert client.get("/todays-documents", headers=member).status_code == 403
    assert client.get("/todays-documents/upcoming", headers=member).status_code == 403
    assert client.patch(f"/todays-documents/{entry['id']}", json={"note": "x"}, headers=member).status_code == 403
    assert client.delete(f"/todays-documents/{entry['id']}", headers=member).status_code == 403
    order = {"scheduled_for": lgu_today().isoformat(), "entry_ids": [entry["id"]]}
    assert client.put("/todays-documents/order", json=order, headers=member).status_code == 403
    # They still read the list through the SB Member service.
    assert TestClient(sb_member_app).get("/todays-documents", headers=member).status_code == 200


def test_request_permissions_are_retired():
    retired = {"view_document_requests", "approve_document_requests", "reject_document_requests",
               "fulfill_document_requests", "request_documents", "view_own_document_requests", "cancel_own_pending_requests"}
    all_defaults = {permission for permissions in DEFAULT_ROLE_PERMISSIONS.values() for permission in permissions}

    assert not retired & all_defaults
    assert "set_documents_for_sb_members" in DEFAULT_ROLE_PERMISSIONS["Employee"]
    assert validate_permissions(["set_documents_for_sb_members"]) == ["set_documents_for_sb_members"]


def test_migration_swaps_request_permissions_for_set_documents_for_sb_members(tmp_path, monkeypatch):
    migration_engine = create_engine(f"sqlite:///{tmp_path / 'migration.sqlite'}")
    monkeypatch.setattr(database, "engine", migration_engine)
    monkeypatch.setattr(schema, "engine", migration_engine)
    cfg = Config(os.path.join(schema.PROJECT_ROOT, "alembic.ini"))
    models.Base.metadata.create_all(bind=migration_engine)
    with migration_engine.begin() as connection:
        connection.execute(text("DROP TABLE todays_documents"))
        connection.execute(text(
            "INSERT INTO users (username, hashed_password, role, status, is_active, permissions) VALUES "
            "('employee', 'x', 'Employee', 'Active', 1, \"['view_documents', 'approve_document_requests', 'fulfill_document_requests']\"), "
            "('member', 'x', 'SB Member', 'Active', 1, \"['view_documents', 'request_documents', 'cancel_own_pending_requests']\"), "
            "('admin', 'x', 'Super Administrator', 'Active', 1, \"['*']\")"
        ))
    command.stamp(cfg, "0020_legacy_base_columns")

    schema.run_database_migrations()

    with migration_engine.connect() as connection:
        permissions = dict(connection.execute(text("SELECT username, permissions FROM users")).fetchall())
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
    migration_engine.dispose()
    assert permissions == {
        "employee": "['view_documents', 'set_documents_for_sb_members']",
        "member": "['view_documents']",
        "admin": "['*']",
    }
    assert "todays_documents" in tables


class DummyPage:
    def __init__(self):
        self.controls = []
        self.overlay = []
        self.theme_mode = None
        self.client_storage = type("Storage", (), {"get": lambda *a: None, "set": lambda *a: None, "remove": lambda *a: None})()

    def add(self, *controls):
        self.controls.extend(controls)

    def clean(self):
        self.controls.clear()

    def update(self, *args):
        pass


def visible_texts(control, seen=None):
    seen = seen if seen is not None else set()
    if control is None or id(control) in seen:
        return []
    seen.add(id(control))
    texts = []
    value = getattr(control, "value", None)
    if type(control).__name__ == "Text" and isinstance(value, str):
        texts.append(value)
    for attribute in ("controls", "content", "actions", "cells", "rows", "title", "subtitle", "leading"):
        child = getattr(control, attribute, None)
        for item in child if isinstance(child, list) else [child]:
            if item is not None and hasattr(item, "_get_control_name"):
                texts.extend(visible_texts(item, seen))
    return texts


def page_texts(page):
    return [text for control in page.controls for text in visible_texts(control)]


def test_sb_member_app_opens_on_todays_documents_and_picks_up_new_ones(monkeypatch):
    import time

    import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
    import frontend.sb_member.app as sb_app

    ids = reset_db()
    employee = headers_for("secretariat")
    main_client = TestClient(main.app)
    assert add(main_client, employee, ids["Budget ordinance"], note="For first reading").status_code == 200

    sb_client = TestClient(sb_member_app)
    monkeypatch.setattr(sb_app.requests, "request", lambda method, url, **kwargs: sb_client.request(method, url.replace(sb_app.API_URL, ""), headers=kwargs.get("headers"), params=kwargs.get("params")))
    monkeypatch.setattr(sb_app, "TODAYS_DOCUMENTS_REFRESH_SECONDS", 0.2)
    member_token = headers_for("member")["Authorization"].split(" ", 1)[1]
    page = DummyPage()

    sb_app.main(page, session={"access_token": member_token, "username": "member", "permissions": ["view_documents"]})

    texts = page_texts(page)
    assert "Today's Documents" in texts
    assert "Budget ordinance" in texts and "For first reading" in texts
    assert "Road resolution" not in texts

    assert add(main_client, employee, ids["Road resolution"]).status_code == 200
    deadline = time.time() + 5
    while "Road resolution" not in page_texts(page) and time.time() < deadline:
        time.sleep(0.1)
    assert "Road resolution" in page_texts(page)


def test_employee_screen_adds_a_document_then_its_note():
    import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
    import flet as ft
    from frontend.admin.todays_documents import build_todays_documents_view

    calls = []
    entries = []

    def fake_api(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET" and path == "/todays-documents":
            return {"date": kwargs["params"]["date"], "today": "2026-10-18", "items": list(entries)}
        if method == "GET" and path == "/todays-documents/upcoming":
            return {"items": [{"date": "2026-10-18", "count": len(entries), "hidden": 0}] if entries else []}
        if method == "GET" and path == "/documents":
            return {"items": [{"id": 7, "title": "Budget ordinance", "tracking_number": "DOC-000007", "document_number": "12", "series_year": 2026, "attachments": []}],
                    "total": 1, "page": 1, "total_pages": 1}
        if method == "POST":
            entries.append({"id": 1, "note": None, "document": {"id": 7, "title": "Budget ordinance", "tracking_number": "DOC-000007", "has_attachment": False}})
            return entries[-1]
        if method == "PATCH":
            entries[0]["note"] = kwargs["json"]["note"]
            return entries[0]
        raise AssertionError((method, path))

    def button(view, kind, label):
        return next(c for c in _walk(view) if type(c).__name__ == kind and (getattr(c, "text", None) or getattr(c, "content", None)) == label)

    from datetime import date as _date
    page = DummyPage()
    view = build_todays_documents_view(page, fake_api, lambda content, **k: ft.Container(content=content), today=_date(2026, 10, 18))
    page.add(view)
    assert any(text.startswith("No documents set for this day yet.") for text in page_texts(page))
    # Every non-archived document is listed before anything is searched.
    listing = next(call for call in calls if call[1] == "/documents")
    assert listing[2]["params"] == {"archived": "false", "page": 1, "page_size": 10, "sort_by": "created_at", "sort_order": "desc"}
    assert "Budget ordinance" in page_texts(page) and "No file" in page_texts(page)
    assert "1 document · page 1 of 1" in page_texts(page)

    search_field = next(c for c in _walk(view) if type(c).__name__ == "TextField" and "Search" in (c.hint_text or ""))
    search_field.value = "budget"
    search_field.on_submit(None)
    assert [call for call in calls if call[1] == "/documents"][-1][2]["params"]["search"] == "budget"
    assert "1 document match · page 1 of 1" in page_texts(page)
    button(view, "OutlinedButton", "Add").on_click(None)

    post = next(call for call in calls if call[0] == "POST")
    assert post[2]["json"] == {"scheduled_for": "2026-10-18", "document_id": 7}
    assert "On this list" in page_texts(page), "the search result shows it was added"
    assert "1 document · 1 without a file" in page_texts(page)

    next(c for c in _walk(view) if type(c).__name__ == "IconButton" and c.tooltip == "Add note").on_click(None)
    note_field = next(c for c in _walk(view) if type(c).__name__ == "TextField" and "Note" in (c.hint_text or ""))
    note_field.value = "For second reading"
    button(view, "FilledButton", "Save note").on_click(None)
    patch = next(call for call in calls if call[0] == "PATCH")
    assert patch[1] == "/todays-documents/1" and patch[2]["json"] == {"note": "For second reading"}
    assert "For second reading" in page_texts(page)


def _walk(control, seen=None):
    seen = seen if seen is not None else set()
    if control is None or id(control) in seen:
        return
    seen.add(id(control))
    yield control
    for attribute in ("controls", "content"):
        child = getattr(control, attribute, None)
        for item in child if isinstance(child, list) else [child]:
            if item is not None and hasattr(item, "_get_control_name"):
                yield from _walk(item, seen)


def test_entries_say_whether_members_can_see_and_open_them():
    ids = reset_db()
    client = TestClient(main.app)
    employee = headers_for("secretariat")
    with SessionLocal() as db:
        db.add(models.Attachment(document_id=ids["Budget ordinance"], original_filename="budget.pdf", mime_type="application/pdf", size=10, stored_path="x"))
        db.commit()
    assert add(client, employee, ids["Budget ordinance"]).status_code == 200
    assert add(client, employee, ids["Road resolution"]).status_code == 200
    with SessionLocal() as db:
        db.query(models.Document).filter_by(id=ids["Road resolution"]).update({"archived": True})
        db.commit()

    items = client.get("/todays-documents", headers=employee).json()["items"]
    assert [(item["document"]["title"], item["document"]["has_attachment"], item["document"]["archived"]) for item in items] == [
        ("Budget ordinance", True, False),
        ("Road resolution", False, True),
    ]


def test_notes_can_be_changed_until_the_day_has_passed():
    ids = reset_db()
    client = TestClient(main.app)
    employee = headers_for("secretariat")
    entry = add(client, employee, ids["Budget ordinance"], note="For first reading").json()

    changed = client.patch(f"/todays-documents/{entry['id']}", json={"note": "  For second reading "}, headers=employee)
    assert changed.status_code == 200, changed.text
    assert changed.json()["note"] == "For second reading"
    assert client.patch(f"/todays-documents/{entry['id']}", json={"note": "  "}, headers=employee).json()["note"] is None
    assert client.patch(f"/todays-documents/{entry['id']}", json={"note": "x"}, headers=headers_for("clerk")).status_code == 403
    assert client.patch("/todays-documents/999999", json={"note": "x"}, headers=employee).status_code == 404

    with SessionLocal() as db:
        db.query(models.TodaysDocument).filter_by(id=entry["id"]).update({"scheduled_for": lgu_today() - timedelta(days=1)})
        assert db.query(models.AuditLog).filter_by(action="TODAYS_DOCUMENT_NOTE_CHANGED").count() == 2
        db.commit()
    assert client.patch(f"/todays-documents/{entry['id']}", json={"note": "late"}, headers=employee).status_code == 400


def test_a_removed_entry_can_be_put_back_where_it_was():
    ids = reset_db()
    client = TestClient(main.app)
    employee = headers_for("secretariat")
    first, second, third = (add(client, employee, ids[title]).json() for title in ("Budget ordinance", "Road resolution", "Market ordinance"))
    assert client.delete(f"/todays-documents/{second['id']}", headers=employee).status_code == 200

    restored = client.post("/todays-documents", json={"scheduled_for": lgu_today().isoformat(), "document_id": ids["Road resolution"], "position": 1}, headers=employee)
    assert restored.status_code == 200, restored.text
    listing = client.get("/todays-documents", headers=employee).json()["items"]
    assert [item["document"]["title"] for item in listing] == ["Budget ordinance", "Road resolution", "Market ordinance"]


def test_upcoming_days_with_lists_are_summarised():
    ids = reset_db()
    client = TestClient(main.app)
    employee = headers_for("secretariat")
    today, later = lgu_today(), lgu_today() + timedelta(days=3)
    assert add(client, employee, ids["Budget ordinance"], day=today).status_code == 200
    assert add(client, employee, ids["Road resolution"], day=later).status_code == 200
    assert add(client, employee, ids["Market ordinance"], day=later).status_code == 200
    with SessionLocal() as db:
        db.add(models.TodaysDocument(scheduled_for=today - timedelta(days=1), document_id=ids["Budget ordinance"], position=0))
        db.query(models.Document).filter_by(id=ids["Market ordinance"]).update({"archived": True})
        db.commit()

    response = client.get("/todays-documents/upcoming", headers=employee)
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {"date": today.isoformat(), "count": 1, "hidden": 0},
        {"date": later.isoformat(), "count": 2, "hidden": 1},
    ]
    assert client.get("/todays-documents/upcoming", headers=headers_for("clerk")).status_code == 403
