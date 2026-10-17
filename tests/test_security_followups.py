from pathlib import Path

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.auth_jwt import create_access_token, create_refresh_token
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine
from Backends.backend.routes import documents as documents_routes

models.Base.metadata.create_all(bind=engine)


def reset_db():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


def seed_admin():
    with SessionLocal() as db:
        db.add(models.User(
            username="admin",
            hashed_password=get_password_hash("pw123"),
            role="Super Administrator",
            permissions="['*']",
            status="Active",
            is_active=True,
        ))
        db.commit()


def login(client, username="admin", password="pw123"):
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def test_access_token_without_a_session_is_rejected():
    reset_db()
    seed_admin()
    client = TestClient(main.app)
    bare_token = create_access_token({"sub": "admin"})
    assert client.get("/documents", headers={"Authorization": f"Bearer {bare_token}"}).status_code == 401
    assert client.get("/auth/users", headers={"Authorization": f"Bearer {bare_token}"}).status_code in (401, 403)

    session_token = login(client)["access_token"]
    assert client.get("/documents", headers={"Authorization": f"Bearer {session_token}"}).status_code == 200


def test_refresh_token_without_a_session_is_rejected():
    reset_db()
    seed_admin()
    client = TestClient(main.app)
    response = client.post("/auth/refresh", data={"refresh_token": create_refresh_token({"sub": "admin"})})
    assert response.status_code == 401

    tokens = login(client)
    refreshed = client.post("/auth/refresh", data={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text


def test_settings_update_is_all_or_nothing():
    reset_db()
    seed_admin()
    client = TestClient(main.app)
    headers = {"Authorization": f"Bearer {login(client)['access_token']}"}

    response = client.put(
        "/system-settings",
        json={"settings": {"organization_name": "Changed Name", "not_a_real_setting": True}},
        headers=headers,
    )
    assert response.status_code == 400, response.text

    with SessionLocal() as db:
        assert db.query(models.SystemSetting).filter_by(key="organization_name").first() is None
        assert db.query(models.AuditLog).filter_by(action="SYSTEM_SETTINGS_UPDATED").count() == 0


def test_login_records_audit_session_and_last_login_together():
    reset_db()
    seed_admin()
    login(TestClient(main.app))
    with SessionLocal() as db:
        assert db.query(models.AuditLog).filter_by(action="USER_LOGIN").count() == 1
        assert db.query(models.UserSession).count() == 1
        assert db.query(models.User).filter_by(username="admin").one().last_login is not None


def test_anonymous_qr_lookups_are_rate_limited(monkeypatch):
    reset_db()
    monkeypatch.setattr(documents_routes, "PUBLIC_QR_RATE_LIMIT_PER_MINUTE", 3)
    documents_routes._public_qr_lookups.clear()
    client = TestClient(main.app)
    accept_json = {"accept": "application/json"}

    statuses = [client.get(f"/qr/unknown-token-{attempt}", headers=accept_json).status_code for attempt in range(5)]
    assert statuses == [404, 404, 404, 429, 429]
    with SessionLocal() as db:
        assert db.query(models.AuditLog).filter_by(action="QR_SCAN_UNRECOGNIZED").count() == 3
    documents_routes._public_qr_lookups.clear()


def test_python_jose_is_no_longer_a_dependency():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert "python-jose" not in requirements
    assert "PyJWT" in requirements
