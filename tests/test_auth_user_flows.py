import os
import time
from datetime import timedelta

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash, verify_password
from Backends.backend.auth_jwt import create_access_token
from Backends.backend.database import SessionLocal, engine

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
        db.query(models.Office).delete()
        db.add_all([
            models.Office(name="SB Secretariat"),
            models.Office(name="Office of the Mayor"),
        ])
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


def bearer_headers(client, username="superuser", password="pw123"):
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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
        headers=bearer_headers(client),
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
        headers=bearer_headers(client),
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


def test_authorized_admin_can_reset_employee_password_and_audits_without_plaintext():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    with SessionLocal() as db:
        user_id = db.query(models.User.id).filter(models.User.username == "activeuser").scalar()

    response = client.post(
        f"/auth/users/{user_id}/reset-password",
        headers=admin_headers,
        json={"new_password": "newsecurepass", "confirm_password": "newsecurepass"},
    )
    assert response.status_code == 200, response.text
    assert "newsecurepass" not in response.text

    old_login = client.post("/auth/login", data={"username": "activeuser", "password": "pw123"})
    new_login = client.post("/auth/login", data={"username": "activeuser", "password": "newsecurepass"})
    assert old_login.status_code == 401
    assert new_login.status_code == 200

    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.username == "activeuser").one()
        assert user.hashed_password != "newsecurepass"
        assert verify_password("newsecurepass", user.hashed_password)
        audit = db.query(models.AuditLog).filter(models.AuditLog.action == "USER_PASSWORD_RESET").order_by(models.AuditLog.id.desc()).first()
        assert audit is not None
        assert "newsecurepass" not in (audit.details or "")


def test_password_reset_validates_confirmation_and_target():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    with SessionLocal() as db:
        user_id = db.query(models.User.id).filter(models.User.username == "activeuser").scalar()

    mismatch = client.post(
        f"/auth/users/{user_id}/reset-password",
        headers=admin_headers,
        json={"new_password": "newsecurepass", "confirm_password": "differentpass"},
    )
    assert mismatch.status_code == 400

    too_short = client.post(
        f"/auth/users/{user_id}/reset-password",
        headers=admin_headers,
        json={"new_password": "short", "confirm_password": "short"},
    )
    assert too_short.status_code == 400

    missing = client.post(
        "/auth/users/999/reset-password",
        headers=admin_headers,
        json={"new_password": "newsecurepass", "confirm_password": "newsecurepass"},
    )
    assert missing.status_code == 404


def test_unauthorized_user_cannot_reset_password():
    reset_db()
    client = TestClient(main.app)
    with SessionLocal() as db:
        user_id = db.query(models.User.id).filter(models.User.username == "activeuser").scalar()
    response = client.post(
        f"/auth/users/{user_id}/reset-password",
        headers={"X-Admin-Username": "activeuser", "X-Admin-Role": "Employee"},
        json={"new_password": "newsecurepass", "confirm_password": "newsecurepass"},
    )
    assert response.status_code == 403


def test_reset_keeps_inactive_user_inactive():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    with SessionLocal() as db:
        user_id = db.query(models.User.id).filter(models.User.username == "inactiveuser").scalar()
    response = client.post(
        f"/auth/users/{user_id}/reset-password",
        headers=admin_headers,
        json={"new_password": "newsecurepass", "confirm_password": "newsecurepass"},
    )
    assert response.status_code == 200, response.text
    login = client.post("/auth/login", data={"username": "inactiveuser", "password": "newsecurepass"})
    assert login.status_code == 403
    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.username == "inactiveuser").one()
        assert user.status == "Inactive"
        assert user.is_active is False


def test_user_offices_support_assignment_update_and_unassigned_users():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)

    offices = client.get("/auth/offices", headers=admin_headers)
    assert offices.status_code == 200, offices.text
    office_id = next(item["id"] for item in offices.json() if item["name"] == "SB Secretariat")
    mayor_id = next(item["id"] for item in offices.json() if item["name"] == "Office of the Mayor")

    users = client.get("/auth/users", headers=admin_headers)
    assert users.status_code == 200, users.text
    assert next(item for item in users.json() if item["username"] == "activeuser")["department"] is None

    created = client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "username": "officeuser",
            "password": "securepass",
            "full_name": "Office User",
            "email": "office@example.com",
            "role": "Employee",
            "office_id": office_id,
        },
    )
    assert created.status_code == 200, created.text

    office_user = next(item for item in client.get("/auth/users", headers=admin_headers).json() if item["username"] == "officeuser")
    assert office_user["office_id"] == office_id
    assert office_user["department"] == "SB Secretariat"

    updated = client.put(
        f"/auth/users/{office_user['id']}",
        headers=admin_headers,
        json={
            "full_name": "Office User",
            "username": "officeuser",
            "email": "office@example.com",
            "role": "Employee",
            "status": "Active",
            "permissions": [],
            "office_id": mayor_id,
        },
    )
    assert updated.status_code == 200, updated.text
    updated_user = next(item for item in client.get("/auth/users", headers=admin_headers).json() if item["username"] == "officeuser")
    assert updated_user["department"] == "Office of the Mayor"


def test_user_office_id_must_reference_an_existing_office():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    response = client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "username": "invalidofficeuser",
            "password": "securepass",
            "full_name": "Invalid Office User",
            "email": "invalid-office@example.com",
            "role": "Employee",
            "office_id": 999999,
        },
    )
    assert response.status_code == 400


def test_super_admin_can_edit_identity_and_office_but_keeps_full_access():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    with SessionLocal() as db:
        super_id = db.query(models.User.id).filter(models.User.username == "superuser").scalar()
        office_id = db.query(models.Office.id).filter(models.Office.name == "SB Secretariat").scalar()

    response = client.put(
        f"/auth/users/{super_id}",
        headers=admin_headers,
        json={
            "full_name": "Updated Super Administrator",
            "username": "superuser",
            "email": "super@example.com",
            "office_id": office_id,
            "role": "Super Administrator",
            "status": "Active",
            "permissions": [],
        },
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.id == super_id).one()
        assert user.full_name == "Updated Super Administrator"
        assert user.office_id == office_id
        assert user.role == "Super Administrator"
        assert "*" in user.permissions
        audit = db.query(models.AuditLog).filter(
            models.AuditLog.action == "USER_UPDATED",
            models.AuditLog.target_id == str(super_id),
        ).order_by(models.AuditLog.id.desc()).first()
        assert audit is not None


def test_super_admin_can_be_deactivated_or_deleted_when_another_active_admin_remains():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    with SessionLocal() as db:
        second_admin = models.User(
            username="secondadmin",
            hashed_password=get_password_hash("adminpass"),
            role="Super Administrator",
            permissions="['*']",
            status="Active",
            is_active=True,
        )
        db.add(second_admin)
        db.commit()
        second_id = second_admin.id
        first_id = db.query(models.User.id).filter(models.User.username == "superuser").scalar()

    status_response = client.post(
        f"/auth/users/{first_id}/status",
        headers=admin_headers,
        data={"status": "Inactive"},
    )
    assert status_response.status_code == 200, status_response.text

    delete_response = client.delete(
        f"/auth/users/{first_id}",
        headers=bearer_headers(client, "secondadmin", "adminpass"),
    )
    assert delete_response.status_code == 200, delete_response.text
    with SessionLocal() as db:
        assert db.query(models.User).filter(models.User.id == second_id).count() == 1


def test_final_active_super_admin_cannot_be_deactivated_or_deleted():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    with SessionLocal() as db:
        super_id = db.query(models.User.id).filter(models.User.username == "superuser").scalar()

    status_response = client.post(
        f"/auth/users/{super_id}/status",
        headers=admin_headers,
        data={"status": "Inactive"},
    )
    assert status_response.status_code == 400
    assert "final active" in status_response.json()["detail"].lower()

    delete_response = client.delete(f"/auth/users/{super_id}", headers=admin_headers)
    assert delete_response.status_code == 400
    assert "final active" in delete_response.json()["detail"].lower()


def test_super_admin_role_cannot_be_removed_during_edit():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    with SessionLocal() as db:
        super_id = db.query(models.User.id).filter(models.User.username == "superuser").scalar()

    response = client.put(
        f"/auth/users/{super_id}",
        headers=admin_headers,
        json={
            "full_name": "Super User",
            "username": "superuser",
            "email": "super@example.com",
            "role": "Employee",
            "status": "Active",
            "permissions": [],
        },
    )
    assert response.status_code == 400


def test_admin_registration_defaults_to_employee():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    response = client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "username": "safe-default-user",
            "password": "securepass",
            "full_name": "Safe Default User",
            "email": "safe-default@example.com",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "Employee"


def test_super_admin_creation_requires_authenticated_super_admin():
    reset_db()
    client = TestClient(main.app)
    payload = {
        "username": "privileged-user",
        "password": "securepass",
        "full_name": "Privileged User",
        "email": "privileged@example.com",
        "role": "Super Administrator",
    }

    unauthorized = client.post(
        "/auth/register",
        headers=bearer_headers(client, "activeuser"),
        json=payload,
    )
    assert unauthorized.status_code == 403

    authorized = client.post(
        "/auth/register",
        headers=bearer_headers(client),
        json=payload,
    )
    assert authorized.status_code == 200, authorized.text
    assert authorized.json()["role"] == "Super Administrator"
    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.username == "privileged-user").one()
        assert user.role == "Super Administrator"
        audit = db.query(models.AuditLog).filter(
            models.AuditLog.action == "USER_REGISTERED",
            models.AuditLog.target_id == str(user.id),
        ).order_by(models.AuditLog.id.desc()).first()
        assert audit is not None


def test_public_registration_cannot_create_an_account_or_assign_super_admin():
    reset_db()
    client = TestClient(main.app)
    response = client.post(
        "/registration/requests",
        json={
            "first_name": "Public",
            "last_name": "Applicant",
            "email": "public@example.com",
            "username": "public-admin",
            "password": "securepass",
            "requested_access": "Super Administrator",
        },
    )
    assert response.status_code == 403


def test_unknown_permissions_are_rejected_and_valid_permissions_are_stored():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    invalid = client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "username": "invalid-permission-user",
            "password": "securepass",
            "full_name": "Invalid Permission User",
            "email": "invalid-permission@example.com",
            "role": "Employee",
            "permissions": ["invented_permission"],
        },
    )
    assert invalid.status_code == 400
    assert "unknown permission" in invalid.json()["detail"].lower()

    valid = client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "username": "valid-permission-user",
            "password": "securepass",
            "full_name": "Valid Permission User",
            "email": "valid-permission@example.com",
            "role": "Employee",
            "permissions": ["view_users", "create_users"],
        },
    )
    assert valid.status_code == 200, valid.text
    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.username == "valid-permission-user").one()
        assert "view_users" in user.permissions
        assert "create_users" in user.permissions


def test_employee_user_management_permissions_are_enforced_server_side():
    reset_db()
    client = TestClient(main.app)
    with SessionLocal() as db:
        manager = models.User(
            username="manager",
            hashed_password=get_password_hash("managerpass"),
            role="Employee",
            permissions="['view_users', 'create_users', 'edit_users', 'manage_permissions', 'reset_passwords', 'activate_users', 'deactivate_users', 'delete_users', 'assign_roles']",
            status="Active",
            is_active=True,
        )
        db.add(manager)
        db.commit()

    unauthorized_headers = {"X-Admin-Username": "activeuser", "X-Admin-Role": "Super Administrator"}
    blocked = client.get("/auth/users", headers=unauthorized_headers)
    assert blocked.status_code == 403

    manager_headers = bearer_headers(client, "manager", "managerpass")
    listed = client.get("/auth/users", headers=manager_headers)
    assert listed.status_code == 200, listed.text

    created = client.post(
        "/auth/register",
        headers=manager_headers,
        json={
            "username": "managed-user",
            "password": "securepass",
            "full_name": "Managed User",
            "email": "managed@example.com",
            "role": "Employee",
            "permissions": ["view_documents"],
        },
    )
    assert created.status_code == 200, created.text

    managed_id = created.json()["id"]
    updated = client.put(
        f"/auth/users/{managed_id}",
        headers=manager_headers,
        json={
            "full_name": "Managed User Updated",
            "username": "managed-user",
            "email": "managed@example.com",
            "role": "Employee",
            "status": "Active",
            "permissions": ["view_documents", "view_users"],
        },
    )
    assert updated.status_code == 200, updated.text
    with SessionLocal() as db:
        audit = db.query(models.AuditLog).filter(
            models.AuditLog.action == "USER_UPDATED",
            models.AuditLog.target_id == str(managed_id),
        ).order_by(models.AuditLog.id.desc()).first()
        assert audit is not None

    reset = client.post(
        f"/auth/users/{managed_id}/reset-password",
        headers=manager_headers,
        json={"new_password": "newsecurepass", "confirm_password": "newsecurepass"},
    )
    assert reset.status_code == 200, reset.text

    with SessionLocal() as db:
        super_id = db.query(models.User.id).filter(models.User.username == "superuser").scalar()
    protected_edit = client.put(
        f"/auth/users/{super_id}",
        headers=manager_headers,
        json={
            "full_name": "Attempted Change",
            "username": "superuser",
            "email": "super@example.com",
            "role": "Super Administrator",
            "status": "Active",
            "permissions": ["*"],
        },
    )
    assert protected_edit.status_code == 403


def test_protected_user_management_requires_valid_jwt_and_rejects_forged_headers():
    reset_db()
    client = TestClient(main.app)

    missing = client.get("/auth/users")
    assert missing.status_code == 403

    forged = client.get(
        "/auth/users",
        headers={"X-Admin-Username": "superuser", "X-Admin-Role": "Super Administrator"},
    )
    assert forged.status_code == 403

    invalid = client.get("/auth/users", headers={"Authorization": "Bearer not-a-valid-token"})
    assert invalid.status_code == 403

    employee = client.get("/auth/users", headers=bearer_headers(client, "activeuser"))
    assert employee.status_code == 403

    admin = client.get("/auth/users", headers=bearer_headers(client))
    assert admin.status_code == 200, admin.text


def test_expired_or_inactive_admin_jwt_is_rejected():
    reset_db()
    client = TestClient(main.app)
    expired_token = create_access_token({"sub": "superuser"}, expires_delta=timedelta(seconds=-1))
    expired = client.get("/auth/users", headers={"Authorization": f"Bearer {expired_token}"})
    assert expired.status_code == 403

    login = client.post("/auth/login", data={"username": "superuser", "password": "pw123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.username == "superuser").one()
        user.status = "Inactive"
        user.is_active = False
        db.commit()
    inactive = client.get("/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert inactive.status_code == 403
