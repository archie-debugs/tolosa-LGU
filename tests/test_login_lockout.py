from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import login_lockout, models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


def reset_db():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.add_all([
            models.User(
                username="admin",
                hashed_password=get_password_hash("pw123"),
                role="Super Administrator",
                permissions="['*']",
                status="Active",
                is_active=True,
            ),
            models.User(
                username="clerk",
                hashed_password=get_password_hash("clerk-pw"),
                role="Employee",
                permissions="['view_documents']",
                status="Active",
                is_active=True,
            ),
        ])
        db.commit()


def attempt(client, username, password):
    return client.post("/auth/login", data={"username": username, "password": password})


def fail_until_locked(client, username="clerk"):
    for _ in range(login_lockout.LOGIN_MAX_FAILURES):
        assert attempt(client, username, "wrong").status_code == 401


def audit_actions(username):
    with SessionLocal() as db:
        return [row.action for row in db.query(models.AuditLog).filter_by(target_id=username).order_by(models.AuditLog.id)]


def test_locked_username_is_refused_even_with_the_correct_password():
    reset_db()
    client = TestClient(main.app)
    fail_until_locked(client)

    response = attempt(client, "clerk", "clerk-pw")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(login_lockout.LOGIN_LOCKOUT_MINUTES * 60)
    assert "Too many failed login attempts" in response.json()["detail"]
    actions = audit_actions("clerk")
    assert actions.count("ACCOUNT_LOCKED") == 1
    assert actions[-1] == "LOGIN_BLOCKED"


def test_failures_below_the_limit_do_not_lock_and_a_success_resets_the_count():
    reset_db()
    client = TestClient(main.app)
    for _ in range(login_lockout.LOGIN_MAX_FAILURES - 1):
        assert attempt(client, "clerk", "wrong").status_code == 401
    assert attempt(client, "clerk", "clerk-pw").status_code == 200

    for _ in range(login_lockout.LOGIN_MAX_FAILURES - 1):
        assert attempt(client, "clerk", "wrong").status_code == 401
    assert attempt(client, "clerk", "clerk-pw").status_code == 200


def test_lockout_ends_when_the_failures_leave_the_window():
    reset_db()
    client = TestClient(main.app)
    fail_until_locked(client)
    with SessionLocal() as db:
        aged = datetime.now(timezone.utc) - timedelta(minutes=login_lockout.LOGIN_LOCKOUT_MINUTES + 1)
        db.query(models.AuditLog).filter_by(target_id="clerk", action="FAILED_LOGIN").update({"created_at": aged})
        db.commit()

    assert attempt(client, "clerk", "clerk-pw").status_code == 200


def test_unknown_usernames_lock_the_same_way():
    reset_db()
    client = TestClient(main.app)
    fail_until_locked(client, "nobody")

    assert attempt(client, "nobody", "anything").status_code == 429


def test_lockout_is_per_username():
    reset_db()
    client = TestClient(main.app)
    fail_until_locked(client, "clerk")

    assert attempt(client, "admin", "pw123").status_code == 200


def test_super_administrator_can_unlock_an_account():
    reset_db()
    client = TestClient(main.app)
    fail_until_locked(client)
    with SessionLocal() as db:
        clerk_id = db.query(models.User).filter_by(username="clerk").one().id
    admin_token = attempt(client, "admin", "pw123").json()["access_token"]

    response = client.post(f"/auth/users/{clerk_id}/unlock", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 200, response.text
    assert "ACCOUNT_UNLOCKED" in audit_actions("clerk")
    assert attempt(client, "clerk", "clerk-pw").status_code == 200


def test_only_super_administrators_can_unlock():
    reset_db()
    client = TestClient(main.app)
    with SessionLocal() as db:
        admin_id = db.query(models.User).filter_by(username="admin").one().id
    clerk_token = attempt(client, "clerk", "clerk-pw").json()["access_token"]

    response = client.post(f"/auth/users/{admin_id}/unlock", headers={"Authorization": f"Bearer {clerk_token}"})

    assert response.status_code == 403



def test_user_list_reports_which_accounts_are_locked():
    reset_db()
    client = TestClient(main.app)
    fail_until_locked(client)
    admin_token = attempt(client, "admin", "pw123").json()["access_token"]

    response = client.get("/auth/users", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 200, response.text
    assert {user["username"]: user["locked"] for user in response.json()} == {"admin": False, "clerk": True}


def _menu_labels(user, unlock_user):
    from frontend.admin.users_roles import _user_actions_menu

    noop = lambda item: None
    menu = _user_actions_menu(user, noop, noop, noop, noop, unlock_user)
    return [item.content.value for item in menu.items]


def test_unlock_menu_item_only_shows_for_locked_users_when_unlocking_is_allowed():
    unlock = lambda item: None

    assert "Unlock Login" in _menu_labels({"locked": True}, unlock)
    assert "Unlock Login" not in _menu_labels({"locked": False}, unlock)
    assert "Unlock Login" not in _menu_labels({"locked": True}, None)
