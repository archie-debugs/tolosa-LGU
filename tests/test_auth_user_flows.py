import os
import time

from fastapi.testclient import TestClient

import backend.main as main
from backend import models
from backend.core import get_password_hash
from backend.database import SessionLocal, engine

os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///./test_auth_user_flows.sqlite"

for db_path in ["test_auth_user_flows.sqlite"]:
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError:
        pass

models.Base.metadata.create_all(bind=engine)


def reset_db():
    with SessionLocal() as db:
        db.query(models.User).delete()
        db.add_all([
            models.User(
                username="activeuser",
                hashed_password=get_password_hash("pw123"),
                role="Employee",
                permissions="['view_documents']",
                status="Active",
                is_active=True,
            ),
            models.User(
                username="inactiveuser",
                hashed_password=get_password_hash("pw123"),
                role="Employee",
                permissions="['view_documents']",
                status="Inactive",
                is_active=False,
            ),
            models.User(
                username="superuser",
                hashed_password=get_password_hash("pw123"),
                role="Super Administrator",
                permissions="['*']",
                status="Active",
                is_active=True,
            ),
        ])
        db.commit()


def test_inactive_user_login_is_rejected():
    reset_db()
    client = TestClient(main.app)
    response = client.post("/auth/login", data={"username": "inactiveuser", "password": "pw123"})
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"].lower()


def test_expired_refresh_token_is_rejected():
    reset_db()
    client = TestClient(main.app)
    response = client.post("/auth/refresh", data={"refresh_token": "not-a-valid-token"})
    assert response.status_code == 401


def test_user_listing_and_permissions_are_exposed():
    reset_db()
    client = TestClient(main.app)
    login = client.post("/auth/login", data={"username": "superuser", "password": "pw123"})
    assert login.status_code == 200, login.text

    users = client.get(
        "/auth/users",
        headers={"X-Admin-Username": "superuser", "X-Admin-Role": "Super Administrator"},
    )
    assert users.status_code == 200, users.text
    payload = users.json()
    assert any(u["username"] == "activeuser" for u in payload)
    assert any(u["username"] == "superuser" for u in payload)
    assert all("permissions" in u for u in payload)


def test_register_user_success_and_login_workflow():
    reset_db()
    client = TestClient(main.app)
    register = client.post(
        "/auth/register",
        headers={"X-Admin-Username": "superuser", "X-Admin-Role": "Super Administrator"},
        json={
            "username": "newuser",
            "password": "securepass",
            "full_name": "New User",
            "email": "new@example.com",
            "role": "Employee",
            "permissions": ["view_documents"],
        },
    )
    assert register.status_code == 200, register.text

    login = client.post("/auth/login", data={"username": "newuser", "password": "securepass"})
    assert login.status_code == 200, login.text
    assert login.json()["username"] == "newuser"
