"""Profile picture, temporary emails verified with Google, and the System Configuration settings that now take effect."""

import io
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import Backends.backend.main as main
import Backends.backend.routes.profile as profile
from Backends.backend import models
from Backends.backend.core import get_password_hash, temporary_email
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


@pytest.fixture
def client(monkeypatch):
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.add_all([
            models.User(username="ana", full_name="Ana Bautista", email=temporary_email("ana"),
                        hashed_password=get_password_hash("pw123456"), role="Employee",
                        permissions="['view_documents', 'register_documents']", status="Active", is_active=True),
            models.User(username="admin", full_name="Admin", email="admin@example.com", hashed_password=get_password_hash("pw123456"),
                        role="Super Administrator", permissions="['*']", status="Active", is_active=True),
        ])
        db.commit()
    return TestClient(main.app)


def headers_for(client, username="ana"):
    response = client.post("/auth/login", data={"username": username, "password": "pw123456"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def stage(client, headers, filename, content, purpose=None):
    payload = {"files": [{"filename": filename, "size": len(content)}], **({"purpose": purpose} if purpose else {})}
    response = client.post("/documents/uploads/create_tmp_uploads", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    entry = response.json()["files"][0]
    assert entry["ok"], entry
    url = urlparse(entry["upload_url"])
    return entry["tmp_name"], client.put(f"{url.path}?{url.query}", content=content)


def png(size=(400, 300)):
    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, "PNG")
    return out.getvalue()


def set_settings(client, **settings):
    response = client.put("/system-settings", headers=headers_for(client, "admin"), json={"settings": settings})
    assert response.status_code == 200, response.text


# ---------- profile picture ----------

def test_anyone_can_set_and_remove_their_profile_picture(client):
    headers = headers_for(client)  # ana has no right to upload documents for SB Members, only to register
    with SessionLocal() as db:
        db.query(models.User).filter_by(username="ana").update({"permissions": "['view_documents']"})
        db.commit()
    tmp_name, put = stage(client, headers, "me.png", png(), purpose="avatar")
    assert put.status_code == 200, put.text

    response = client.post("/auth/me/avatar", headers=headers, json={"tmp_name": tmp_name})
    assert response.status_code == 200, response.text
    picture = Image.open(io.BytesIO(__import__("base64").b64decode(response.json()["avatar"])))
    assert picture.size == (256, 256) and picture.format == "JPEG"
    assert client.get("/auth/me", headers=headers).json()["avatar"] == response.json()["avatar"]

    assert client.delete("/auth/me/avatar", headers=headers).json()["avatar"] is None
    with SessionLocal() as db:
        actions = {row.action for row in db.query(models.AuditLog)}
    assert {"PROFILE_PICTURE_CHANGED", "PROFILE_PICTURE_REMOVED"} <= actions


def test_a_profile_picture_must_be_one_jpg_or_png_staged_by_you(client):
    headers = headers_for(client)
    response = client.post("/documents/uploads/create_tmp_uploads", headers=headers,
                           json={"purpose": "avatar", "files": [{"filename": "me.pdf", "size": 10}]})
    assert response.json()["files"][0]["ok"] is False
    two = [{"filename": "a.png", "size": 10}, {"filename": "b.png", "size": 10}]
    assert client.post("/documents/uploads/create_tmp_uploads", headers=headers, json={"purpose": "avatar", "files": two}).status_code == 400

    tmp_name, _ = stage(client, headers, "me.png", png(), purpose="avatar")
    assert client.post("/auth/me/avatar", headers=headers_for(client, "admin"), json={"tmp_name": tmp_name}).status_code == 404

    tmp_name, _ = stage(client, headers, "fake.png", b"not a picture", purpose="avatar")
    assert client.post("/auth/me/avatar", headers=headers, json={"tmp_name": tmp_name}).status_code == 400


# ---------- temporary emails ----------

def test_new_accounts_get_a_temporary_email_and_must_replace_it(client):
    admin = headers_for(client, "admin")
    response = client.post("/auth/register", headers=admin, json={"username": "ben", "password": "pw123456", "full_name": "Ben Cruz"})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert db.query(models.User).filter_by(username="ben").one().email == temporary_email("ben")

    ben = headers_for(client, "ben")
    me = client.get("/auth/me", headers=ben).json()
    assert me["email_temporary"] is True and me["email_verified"] is False

    refused = client.put("/auth/me", headers=ben, json={"full_name": "Ben Cruz", "email": temporary_email("someone")})
    assert refused.status_code == 400 and refused.json()["detail"] == "Enter your own email address."


def test_changing_your_email_makes_it_unverified_again(client):
    with SessionLocal() as db:
        db.query(models.User).filter_by(username="ana").update({"email": "ana@gmail.com", "email_verified_at": datetime.now(timezone.utc)})
        db.commit()
    headers = headers_for(client)
    assert client.get("/auth/me", headers=headers).json()["email_verified"] is True

    response = client.put("/auth/me", headers=headers, json={"full_name": "Ana Bautista", "email": "ana.b@gmail.com"})
    assert response.status_code == 200, response.text
    me = client.get("/auth/me", headers=headers).json()
    assert me["email"] == "ana.b@gmail.com" and me["email_verified"] is False and me["email_temporary"] is False


# ---------- verifying with Google ----------

def google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://example.test/auth/google/callback")


class TokenAnswer:
    def __init__(self, claims):
        self.claims = claims

    def raise_for_status(self):
        pass

    def json(self):
        return {"id_token": jwt.encode(self.claims, "google-key", algorithm="HS256")}


def google_answers(monkeypatch, **claims):
    claims = {"aud": "client-123", "iss": "https://accounts.google.com", "email_verified": True,
              "exp": (datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp(), **claims}
    sent = []
    monkeypatch.setattr(profile.requests, "post", lambda url, **kwargs: sent.append(kwargs["data"]) or TokenAnswer(claims))
    return sent


def test_verifying_with_google_needs_setup_and_a_real_email(client, monkeypatch):
    headers = headers_for(client)
    assert client.post("/auth/me/email/google", headers=headers).status_code == 503
    google_env(monkeypatch)
    response = client.post("/auth/me/email/google", headers=headers)
    assert response.status_code == 400 and "temporary email" in response.json()["detail"]


def test_signing_in_to_google_with_the_same_email_verifies_it(client, monkeypatch):
    google_env(monkeypatch)
    with SessionLocal() as db:
        db.query(models.User).filter_by(username="ana").update({"email": "ana@gmail.com"})
        db.commit()
    headers = headers_for(client)
    link = urlparse(client.post("/auth/me/email/google", headers=headers).json()["url"])
    query = parse_qs(link.query)
    assert link.netloc == "accounts.google.com" and query["login_hint"] == ["ana@gmail.com"]
    sent = google_answers(monkeypatch, email="ANA@gmail.com")

    page = client.get("/auth/google/callback", params={"code": "abc", "state": query["state"][0]})
    assert page.status_code == 200 and "Email verified" in page.text
    assert sent[0]["code"] == "abc" and sent[0]["client_secret"] == "secret"
    assert client.get("/auth/me", headers=headers).json()["email_verified"] is True
    assert client.post("/auth/me/email/google", headers=headers).status_code == 400  # already verified


def test_a_different_google_account_or_a_bad_state_does_not_verify(client, monkeypatch):
    google_env(monkeypatch)
    with SessionLocal() as db:
        db.query(models.User).filter_by(username="ana").update({"email": "ana@gmail.com"})
        db.commit()
    headers = headers_for(client)
    state = parse_qs(urlparse(client.post("/auth/me/email/google", headers=headers).json()["url"]).query)["state"][0]

    google_answers(monkeypatch, email="someone@gmail.com")
    assert "Not verified" in client.get("/auth/google/callback", params={"code": "abc", "state": state}).text
    google_answers(monkeypatch, email="ana@gmail.com", aud="another-client")
    assert "Not verified" in client.get("/auth/google/callback", params={"code": "abc", "state": state}).text
    assert "expired" in client.get("/auth/google/callback", params={"code": "abc", "state": "forged"}).text
    assert client.get("/auth/me", headers=headers).json()["email_verified"] is False


def test_the_privacy_policy_google_links_to_is_public(client):
    page = client.get("/privacy")
    assert page.status_code == 200 and "Privacy Policy" in page.text and "Verify with Google" in page.text


# ---------- System Configuration ----------

def test_session_timeout_signs_out_an_idle_session(client):
    set_settings(client, session_timeout_minutes=15)
    headers = headers_for(client)
    assert client.get("/auth/me", headers=headers).status_code == 200
    with SessionLocal() as db:
        db.query(models.UserSession).update({"last_activity": datetime.now(timezone.utc) - timedelta(minutes=16)})
        db.commit()

    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401 and "15 minutes" in response.json()["detail"]
    with SessionLocal() as db:
        session = db.query(models.UserSession).join(models.User).filter(models.User.username == "ana").one()
        assert session.revoke_reason == "idle timeout"


def test_settings_ranges_are_checked(client):
    admin = headers_for(client, "admin")
    for settings in ({"session_timeout_minutes": 2}, {"upload_max_size_mb": 500}):
        assert client.put("/system-settings", headers=admin, json={"settings": settings}).status_code == 400


def test_closing_the_public_portal_closes_its_data_but_not_the_site_names(client):
    set_settings(client, public_portal_enabled=False, system_name="Records System")
    assert client.get("/public/documents").status_code == 503
    assert client.get("/public/announcements").status_code == 503
    site = client.get("/public/site").json()
    assert site == {"organization_name": "Municipality of Tolosa", "system_name": "Records System", "public_portal_enabled": False}

    set_settings(client, public_portal_enabled=True)
    assert client.get("/public/documents").status_code == 200


def test_max_upload_size_limits_staged_files(client):
    set_settings(client, upload_max_size_mb=1)
    _, put = stage(client, headers_for(client), "big.pdf", b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10))
    assert put.status_code >= 400 and "1 MB" in put.json()["detail"]


# ---------- the Settings card and the reminder above every page ----------

import frontend.admin.app  # noqa: E402,F401  (applies the flet compatibility shims)
import flet as ft  # noqa: E402

from frontend.admin.admin_shell import render_shell  # noqa: E402
from frontend.admin.settings import build_employee_settings_view  # noqa: E402
from tests.test_account_menu_ui import DummyPage, click, clickable, texts, walk  # noqa: E402

ACCOUNT = {"username": "ana", "full_name": "Ana Bautista", "role": "Employee", "office": None, "status": "Active"}


class FakeFiles:
    def __init__(self):
        self.uploads = []

    def pick(self, multiple, on_result, extensions=None):
        self.extensions = extensions
        on_result([{"name": "me.png", "size": 1234}])

    def upload(self, items, on_progress):
        self.uploads.append(items)
        on_progress(items[0][0], 1.0, None)


def settings_view(**profile):
    calls, reloads, page = [], [], DummyPage()
    page.launch_url = lambda url: calls.append(("OPEN", url))

    def api(method, path, **kwargs):
        if path != "/system-link":  # the share card's own call
            calls.append((method, path, kwargs.get("json")))
        if path == "/documents/uploads/create_tmp_uploads":
            return {"files": [{"ok": True, "tmp_name": "tmp_1_me.png", "upload_url": "https://x/up"}]}
        if path == "/auth/me/email/google":
            return {"url": "https://accounts.google.com/o/oauth2/v2/auth?x=1"}
        return {}

    files = FakeFiles()
    view = build_employee_settings_view(page, profile={**ACCOUNT, **profile}, change_password=lambda: None,
                                        edit_profile=lambda: None, api=api, files=files, reload=lambda: reloads.append(True))
    return view, calls, reloads, files


def button(view, label):
    return next(c for c in walk(view) if getattr(c, "text", None) == label)


def test_a_temporary_email_shows_why_it_cannot_be_verified_yet():
    view, *_ = settings_view(email=temporary_email("ana"), email_temporary=True, email_verified=False)
    assert "Temporary" in texts(view)
    assert button(view, "Verify with Google").disabled
    assert any("temporary email" in text for text in texts(view))


def test_verify_with_google_opens_google_and_a_verified_email_has_no_buttons():
    view, calls, _, _ = settings_view(email="ana@gmail.com", email_temporary=False, email_verified=False)
    assert "Not verified" in texts(view)
    click(button(view, "Verify with Google"))
    assert ("OPEN", "https://accounts.google.com/o/oauth2/v2/auth?x=1") in calls

    view, *_ = settings_view(email="ana@gmail.com", email_temporary=False, email_verified=True)
    assert "Verified" in texts(view)
    assert not any(getattr(c, "text", None) == "Verify with Google" for c in walk(view))


def test_change_picture_stages_uploads_saves_and_reloads():
    view, calls, reloads, files = settings_view(email="ana@gmail.com", email_verified=True)
    assert not any(getattr(c, "text", None) == "Remove" for c in walk(view))  # no picture yet
    click(button(view, "Change picture"))
    assert files.extensions == ["jpg", "jpeg", "png"]
    assert calls[0] == ("POST", "/documents/uploads/create_tmp_uploads",
                        {"purpose": "avatar", "files": [{"filename": "me.png", "size": 1234}]})
    assert files.uploads == [[("me.png", "https://x/up")]]
    assert calls[1] == ("POST", "/auth/me/avatar", {"tmp_name": "tmp_1_me.png"}) and reloads == [True]

    view, calls, reloads, _ = settings_view(email="ana@gmail.com", email_verified=True, avatar="iVBORw0KGgo=")
    assert any(isinstance(c, ft.Image) for c in walk(view))
    click(button(view, "Remove"))
    assert calls == [("DELETE", "/auth/me/avatar", None)] and reloads == [True]


def test_the_reminder_and_picture_show_in_the_shell_on_every_page():
    page = DummyPage()
    nav = [(ft.Icons.DESCRIPTION_OUTLINED, "Documents", lambda: ft.Text("Documents screen"), "Documents"),
           (ft.Icons.SETTINGS_OUTLINED, "Settings", lambda: ft.Text("Settings screen"), "Account")]
    render_shell(page, "ana", lambda: None, nav, ft.Text("Documents screen"), account={
        "name": "Ana Bautista", "role": "Employee", "avatar": "iVBORw0KGgo=", "notice": ft.Text("Verify your email"),
    })
    root = page.controls[0]
    assert "Verify your email" in texts(root)
    assert any(isinstance(c, ft.Image) and c.src_base64 == "iVBORw0KGgo=" for c in walk(root))
    settings = next(c for c in walk(root) if isinstance(c, ft.Container) and clickable(c) and "Settings" in texts(c))
    click(settings)
    assert "Settings screen" in texts(page.controls[0]) and "Verify your email" in texts(page.controls[0])
