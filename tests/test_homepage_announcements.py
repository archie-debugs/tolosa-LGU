from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import DEFAULT_HOMEPAGE_ANNOUNCEMENTS, get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


def reset_db():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


def seed_user(username, role):
    with SessionLocal() as db:
        db.add(models.User(
            username=username,
            hashed_password=get_password_hash("pw123"),
            role=role,
            permissions="['*']" if role == "Super Administrator" else "[]",
            status="Active",
            is_active=True,
        ))
        db.commit()


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def save_announcements(client, headers, announcements):
    return client.put("/system-settings", headers=headers, json={"settings": {"homepage_announcements": announcements}})


def test_public_announcements_start_with_the_defaults():
    reset_db()
    client = TestClient(main.app)
    response = client.get("/public/announcements")
    assert response.status_code == 200, response.text
    assert response.json()["announcements"] == DEFAULT_HOMEPAGE_ANNOUNCEMENTS


def test_super_admin_updates_announcements_and_the_public_sees_them():
    reset_db()
    seed_user("admin", "Super Administrator")
    client = TestClient(main.app)
    headers = headers_for(client, "admin")

    response = save_announcements(client, headers, [
        {"category": " Public Notice ", "title": " Regular session on Monday ", "date": "Oct 27, 2026", "details": "Session hall, 9:00 AM"},
    ])
    assert response.status_code == 200, response.text

    public = client.get("/public/announcements").json()["announcements"]
    assert public == [{"category": "Public Notice", "title": "Regular session on Monday", "date": "Oct 27, 2026", "details": "Session hall, 9:00 AM"}]
    with SessionLocal() as db:
        assert db.query(models.AuditLog).filter_by(action="SYSTEM_SETTINGS_UPDATED", target_id="homepage_announcements").count() == 1


def test_announcements_can_be_cleared():
    reset_db()
    seed_user("admin", "Super Administrator")
    client = TestClient(main.app)
    assert save_announcements(client, headers_for(client, "admin"), []).status_code == 200
    assert client.get("/public/announcements").json()["announcements"] == []


def test_invalid_announcements_are_rejected():
    reset_db()
    seed_user("admin", "Super Administrator")
    client = TestClient(main.app)
    headers = headers_for(client, "admin")

    assert save_announcements(client, headers, [{"category": "Notice", "title": "  "}]).status_code == 400
    assert save_announcements(client, headers, ["just text"]).status_code == 400
    assert save_announcements(client, headers, [{"title": "x" * 121}]).status_code == 400
    assert save_announcements(client, headers, [{"title": f"Item {n}"} for n in range(11)]).status_code == 400
    assert client.get("/public/announcements").json()["announcements"] == DEFAULT_HOMEPAGE_ANNOUNCEMENTS


def test_only_super_admins_can_update_announcements():
    reset_db()
    seed_user("employee", "Employee")
    client = TestClient(main.app)
    response = save_announcements(client, headers_for(client, "employee"), [{"title": "Not allowed"}])
    assert response.status_code == 403
    assert client.get("/public/announcements").json()["announcements"] == DEFAULT_HOMEPAGE_ANNOUNCEMENTS


def test_homepage_fallback_matches_the_backend_defaults():
    from frontend.Frontend_Homepage.page import DEFAULT_ANNOUNCEMENTS

    assert DEFAULT_ANNOUNCEMENTS == DEFAULT_HOMEPAGE_ANNOUNCEMENTS
