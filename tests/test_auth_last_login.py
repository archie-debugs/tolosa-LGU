import os
import time

os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///./test_last_login.sqlite"

for db_path in ["test_last_login.sqlite"]:
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError:
        pass

from fastapi.testclient import TestClient

from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine
from Backends.backend.main import app

models.Base.metadata.create_all(bind=engine)


def seed_users():
    db = SessionLocal()
    try:
        db.query(models.User).delete()
        admin = models.User(
            username="adminuser",
            hashed_password=get_password_hash("adminpass"),
            role="Super Administrator",
            permissions="['*']",
            status="Active",
            is_active=True,
        )
        user = models.User(
            username="lastloginuser",
            hashed_password=get_password_hash("pass123"),
            role="Employee",
            permissions="['view_documents']",
            status="Active",
            is_active=True,
        )
        db.add_all([admin, user])
        db.commit()
    finally:
        db.close()


def test_login_and_refresh_update_last_login():
    seed_users()
    client = TestClient(app)

    login_response = client.post("/auth/login", data={"username": "lastloginuser", "password": "pass123"})
    assert login_response.status_code == 200, login_response.text
    login_payload = login_response.json()

    admin_headers = {"X-Admin-Username": "adminuser", "X-Admin-Role": "Super Administrator"}
    users_response = client.get("/auth/users", headers=admin_headers)
    assert users_response.status_code == 200, users_response.text
    users_payload = users_response.json()
    user_entry = next(u for u in users_payload if u["username"] == "lastloginuser")
    assert user_entry["last_login"] is not None

    with SessionLocal() as db:
        stored = db.query(models.User).filter(models.User.username == "lastloginuser").one()
        assert stored.last_login is not None
        login_timestamp = stored.last_login

    time.sleep(0.05)
    refresh_response = client.post("/auth/refresh", data={"refresh_token": login_payload["refresh_token"]})
    assert refresh_response.status_code == 200, refresh_response.text
    refresh_payload = refresh_response.json()
    assert refresh_payload["refresh_token"]

    with SessionLocal() as db:
        refreshed = db.query(models.User).filter(models.User.username == "lastloginuser").one()
        assert refreshed.last_login is not None
        assert refreshed.last_login >= login_timestamp

    users_after_refresh = client.get("/auth/users", headers=admin_headers)
    assert users_after_refresh.status_code == 200, users_after_refresh.text
    user_entry_after_refresh = next(u for u in users_after_refresh.json() if u["username"] == "lastloginuser")
    assert user_entry_after_refresh["last_login"] is not None
    assert user_entry_after_refresh["last_login"] == refreshed.last_login.isoformat()
