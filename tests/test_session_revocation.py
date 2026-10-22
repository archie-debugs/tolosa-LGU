from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.SBmem_backend.main import app as sb_member_app
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

import frontend.admin.app as admin_app  # also applies the flet compatibility shims
import flet as ft

from tests.test_account_menu_ui import DummyPage, click, clickable, texts, walk

models.Base.metadata.create_all(bind=engine)


def reset_db():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        for username, role, permissions in (
            ("admin", "Super Administrator", ["*"]),
            ("admin2", "Super Administrator", ["*"]),
            ("clerk", "Employee", ["view_documents", "search_documents"]),
            ("member", "SB Member", ["view_documents"]),
        ):
            db.add(models.User(username=username, hashed_password=get_password_hash("pw123"), role=role,
                               permissions=str(permissions), status="Active", is_active=True))
        db.commit()


def login(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return response.json()


def bearer(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def session_of(client, admin_headers, username):
    sessions = client.get("/auth/sessions", headers=admin_headers).json()
    return next(item for item in sessions if item["username"] == username)


def test_super_administrator_sessions_cannot_be_revoked():
    reset_db()
    client = TestClient(main.app)
    admin = bearer(login(client, "admin"))
    other_admin = bearer(login(client, "admin2"))

    for username in ("admin", "admin2"):
        target = session_of(client, admin, username)
        assert target["role"] == "Super Administrator"
        response = client.post(f"/auth/sessions/{target['session_id']}/revoke", headers=admin)
        assert response.status_code == 403
        assert response.json()["detail"] == "Super Administrator sessions cannot be revoked."

    assert client.get("/auth/me", headers=admin).status_code == 200
    assert client.get("/auth/me", headers=other_admin).status_code == 200
    with SessionLocal() as db:
        assert db.query(models.UserSession).filter(models.UserSession.revoked_at.isnot(None)).count() == 0
        assert db.query(models.AuditLog).filter_by(action="SESSION_REVOKED").count() == 0


def test_a_revoked_employee_session_is_refused_on_its_next_call():
    reset_db()
    client = TestClient(main.app)
    admin = bearer(login(client, "admin"))
    clerk_tokens = login(client, "clerk")
    target = session_of(client, admin, "clerk")
    assert target["role"] == "Employee"

    assert client.post(f"/auth/sessions/{target['session_id']}/revoke", headers=admin).status_code == 200

    assert client.get("/auth/me", headers=bearer(clerk_tokens)).status_code == 401
    assert client.post("/auth/refresh", data={"refresh_token": clerk_tokens["refresh_token"]}).status_code == 401


class BackendSession:
    """Stands in for requests.Session: sends calls to the backend app and runs the response hooks."""

    def __init__(self):
        self.client = TestClient(main.app)
        self.hooks = {"response": []}

    def request(self, method, url, headers=None, verify=None, timeout=None, **kwargs):
        response = self.client.request(method, url.replace(admin_app.BACKEND_URL, ""), headers=headers, **kwargs)
        for hook in self.hooks["response"]:
            hook(response)
        return response

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)


class Storage:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.values.pop(key, None)


class AppPage(DummyPage):
    def __init__(self):
        super().__init__()
        self.client_storage = Storage()
        self.data = None
        self.route = "/"

    def go(self, route):
        self.route = route


def on_login_screen(page):
    fields = [c for control in page.controls for c in walk(control) if isinstance(c, ft.TextField)]
    names = {getattr(c, "label", None) for c in fields} | {getattr(c, "hint_text", None) for c in fields}
    return {"Enter your username", "Enter your password"} <= names


def sidebar_tile(page, label):
    return next(c for control in page.controls for c in walk(control)
                if isinstance(c, ft.Container) and clickable(c) and texts(c) == [label])


def test_an_employee_whose_session_is_revoked_lands_on_login_at_the_next_click(monkeypatch):
    reset_db()
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    client = TestClient(main.app)
    admin = bearer(login(client, "admin"))
    clerk = login(client, "clerk")
    page = AppPage()

    admin_app.main(page, session=clerk)
    assert not on_login_screen(page)
    sidebar_tile(page, "Documents")

    target = session_of(client, admin, "clerk")
    assert client.post(f"/auth/sessions/{target['session_id']}/revoke", headers=admin).status_code == 200

    click(sidebar_tile(page, "Documents"))

    assert on_login_screen(page)
    assert page.client_storage.get("sb_access_token") is None


def test_an_employee_with_a_live_session_stays_signed_in_after_a_click(monkeypatch):
    reset_db()
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    page = AppPage()

    admin_app.main(page, session=login(TestClient(main.app), "clerk"))
    click(sidebar_tile(page, "Documents"))

    assert not on_login_screen(page)


def test_a_revoked_sb_member_is_sent_back_to_the_homepage(monkeypatch):
    import frontend.sb_member.app as sb_app

    reset_db()
    client = TestClient(main.app)
    admin = bearer(login(client, "admin"))
    member = login(client, "member")
    sb_client = TestClient(sb_member_app)
    monkeypatch.setattr(sb_app.requests, "request", lambda method, url, **kwargs: sb_client.request(
        method, url.replace(sb_app.API_URL, ""), headers=kwargs.get("headers"), params=kwargs.get("params")))
    monkeypatch.setattr(sb_app, "TODAYS_DOCUMENTS_REFRESH_SECONDS", 3600)
    page = AppPage()

    sb_app.main(page, session={"access_token": member["access_token"], "username": "member", "permissions": ["view_documents"]})
    assert "Member Workspace" in [t for control in page.controls for t in texts(control)]

    target = session_of(client, admin, "member")
    assert client.post(f"/auth/sessions/{target['session_id']}/revoke", headers=admin).status_code == 200
    click(sidebar_tile(page, "Documents"))

    shown = [t for control in page.controls for t in texts(control)]
    assert "Member Workspace" not in shown
    assert "SANGGUNIANG BAYAN" in shown
