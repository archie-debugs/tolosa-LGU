import os
import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import UPLOAD_DIR, get_password_hash, verify_password
from Backends.backend.auth_jwt import create_access_token
from Backends.backend.database import SessionLocal, engine
from Backends.backend.core import get_default_permissions_for_role, require_permission
from Backends.backend.routes import documents as documents_routes
from fastapi import HTTPException

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
        db.query(models.Attachment).delete()
        db.query(models.Document).delete()
        db.query(models.UserSession).delete()
        db.query(models.AuditLog).delete()
        db.query(models.SystemSetting).delete()
        db.query(models.User).delete()
        db.query(models.Office).delete()
        db.query(models.RegistrationRequest).delete()
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


def test_ordinance_title_extraction_uses_actual_number_and_detects_conflicts():
    assert documents_routes._extract_ordinance_number("ORDINANCE NO. 32 Series 1993") == 32
    assert documents_routes._extract_ordinance_number("ORDINANCE NO. 07 Series 1993") == 7
    assert documents_routes._extract_ordinance_number("OR35DF~1") is None

    with SessionLocal() as db:
        db.query(models.Attachment).delete()
        db.query(models.Document).delete()
        db.add(models.Document(
            tracking_number="DOC-32",
            title="ORDINANCE NO. 32 Series 1993",
            status="Approved",
            priority="Medium",
        ))
        db.commit()
        try:
            documents_routes._next_tracking_number(db, title="ORDINANCE NO. 32 Series 1993")
            raise AssertionError("Expected duplicate ordinance assignment to raise a conflict")
        except ValueError:
            pass


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


def test_uploaded_documents_are_created_as_approved():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)

    response = client.post(
        "/documents/register",
        headers=admin_headers,
        data={"title": "Approved upload", "description": "test"},
        files={"file": ("sample.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Approved"


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
    assert invalid.status_code == 401

    employee = client.get("/auth/users", headers=bearer_headers(client, "activeuser"))
    assert employee.status_code == 403

    admin = client.get("/auth/users", headers=bearer_headers(client))
    assert admin.status_code == 200, admin.text


def test_expired_or_inactive_admin_jwt_is_rejected():
    reset_db()
    client = TestClient(main.app)
    expired_token = create_access_token({"sub": "superuser"}, expires_delta=timedelta(seconds=-1))
    expired = client.get("/auth/users", headers={"Authorization": f"Bearer {expired_token}"})
    assert expired.status_code == 401

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


def _seed_registration_request(username, email, status="Pending"):
    with SessionLocal() as db:
        request = models.RegistrationRequest(
            registration_reference=f"REG-TEST-{username}",
            first_name="Registered",
            middle_name="Test",
            last_name="Applicant",
            email=email,
            username=username,
            office="SB Secretariat",
            position="Staff",
            requested_access="Employee",
            hashed_password=get_password_hash("registration-pass"),
            status=status,
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        return request.id


def test_registration_requests_accept_case_insensitive_pending_statuses():
    reset_db()
    client = TestClient(main.app)
    request_id = _seed_registration_request("pending-lowercase", "pending-lowercase@example.com", status="pending")
    admin_headers = bearer_headers(client)

    pending = client.get("/registration/requests", params={"status": "pending"}, headers=admin_headers)
    assert pending.status_code == 200, pending.text
    assert any(item["id"] == request_id for item in pending.json()["items"])

    default_pending = client.get("/registration/requests", headers=admin_headers)
    assert default_pending.status_code == 200, default_pending.text
    assert any(item["id"] == request_id for item in default_pending.json()["items"])


def test_registration_approval_creates_active_user_with_audit_and_login():
    reset_db()
    client = TestClient(main.app)
    request_id = _seed_registration_request("approved-registration", "approved@example.com")
    admin_headers = bearer_headers(client)

    pending = client.get("/registration/requests", headers=admin_headers)
    assert pending.status_code == 200, pending.text
    item = next(item for item in pending.json()["items"] if item["id"] == request_id)
    assert item["status"] == "Pending"

    approved = client.put(
        f"/registration/requests/{request_id}/approve",
        headers=admin_headers,
        json={"final_role": "Employee"},
    )
    assert approved.status_code == 200, approved.text

    login = client.post("/auth/login", data={"username": "approved-registration", "password": "registration-pass"})
    assert login.status_code == 200, login.text
    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.username == "approved-registration").one()
        request = db.query(models.RegistrationRequest).filter(models.RegistrationRequest.id == request_id).one()
        assert user.full_name == "Registered Test Applicant"
        assert user.email == "approved@example.com"
        assert user.status == "Active"
        assert user.is_active is True
        assert request.status == "Approved"
        assert request.assigned_role == "Employee"
        assert db.query(models.AuditLog).filter(
            models.AuditLog.target_id == request.registration_reference,
            models.AuditLog.action == "Approved Registration",
        ).count() >= 1
        registration_audit = db.query(models.AuditLog).filter(
            models.AuditLog.action == "USER_REGISTERED",
            models.AuditLog.details.ilike("%approved-registration%"),
        ).order_by(models.AuditLog.id.desc()).first()
        assert registration_audit is not None


def test_registration_rejection_cannot_create_or_activate_user():
    reset_db()
    client = TestClient(main.app)
    request_id = _seed_registration_request("rejected-registration", "rejected@example.com")
    admin_headers = bearer_headers(client)

    rejected = client.put(
        f"/registration/requests/{request_id}/reject",
        headers=admin_headers,
        json={"reason": "Invalid Information"},
    )
    assert rejected.status_code == 200, rejected.text
    with SessionLocal() as db:
        request = db.query(models.RegistrationRequest).filter(models.RegistrationRequest.id == request_id).one()
        assert request.status == "Rejected"
        assert db.query(models.User).filter(models.User.username == "rejected-registration").count() == 0
        assert db.query(models.AuditLog).filter(
            models.AuditLog.target_id == request.registration_reference,
            models.AuditLog.action == "Rejected Registration",
        ).count() >= 1


def test_registration_approval_rejects_duplicate_and_unauthorized_requests():
    reset_db()
    client = TestClient(main.app)
    request_id = _seed_registration_request("activeuser", "duplicate@example.com")
    duplicate = client.put(
        f"/registration/requests/{request_id}/approve",
        headers=bearer_headers(client),
        json={"final_role": "Employee"},
    )
    assert duplicate.status_code == 409

    other_request_id = _seed_registration_request("unauthorized-registration", "unauthorized@example.com")
    unauthorized = client.put(
        f"/registration/requests/{other_request_id}/approve",
        headers=bearer_headers(client, "activeuser"),
        json={"final_role": "Employee"},
    )
    assert unauthorized.status_code == 403


def test_role_definitions_and_registration_permissions_are_server_enforced():
    reset_db()
    client = TestClient(main.app)
    with SessionLocal() as db:
        manager = models.User(
            username="registration-manager",
            hashed_password=get_password_hash("managerpass"),
            role="Employee",
            permissions="['view_users', 'view_registration_requests', 'approve_registrations', 'reject_registrations']",
            status="Active",
            is_active=True,
        )
        db.add(manager)
        db.commit()
    manager_headers = bearer_headers(client, "registration-manager", "managerpass")

    roles = client.get("/auth/roles", headers=manager_headers)
    assert roles.status_code == 200, roles.text
    role_map = {item["name"]: item["permissions"] for item in roles.json()}
    assert set(role_map["SB Member"]) >= {"view_documents", "download_documents"}
    assert role_map["Super Administrator"] == ["*"]

    request_id = _seed_registration_request("employee-approved", "employee-approved@example.com")
    approved = client.put(
        f"/registration/requests/{request_id}/approve",
        headers=manager_headers,
        json={"final_role": "Employee"},
    )
    assert approved.status_code == 200, approved.text

    with SessionLocal() as db:
        audit = db.query(models.AuditLog).filter(
            models.AuditLog.action == "Approved Registration",
            models.AuditLog.actor == "registration-manager",
        ).order_by(models.AuditLog.id.desc()).first()
        assert audit is not None


def test_employee_without_registration_permissions_is_blocked():
    reset_db()
    client = TestClient(main.app)
    request_id = _seed_registration_request("blocked-registration", "blocked@example.com")
    blocked = client.get("/registration/requests", headers=bearer_headers(client, "activeuser"))
    assert blocked.status_code == 403
    blocked_approval = client.put(
        f"/registration/requests/{request_id}/approve",
        headers=bearer_headers(client, "activeuser"),
        json={"final_role": "Employee"},
    )
    assert blocked_approval.status_code == 403


def test_role_and_permission_changes_have_dedicated_audit_events():
    reset_db()
    client = TestClient(main.app)
    with SessionLocal() as db:
        manager = models.User(
            username="permission-manager",
            hashed_password=get_password_hash("managerpass"),
            role="Employee",
            permissions="['edit_users', 'assign_roles', 'manage_permissions']",
            status="Active",
            is_active=True,
        )
        db.add(manager)
        db.commit()
        user_id = db.query(models.User.id).filter(models.User.username == "activeuser").scalar()
    headers = bearer_headers(client, "permission-manager", "managerpass")
    response = client.put(
        f"/auth/users/{user_id}",
        headers=headers,
        json={
            "full_name": "Active User",
            "username": "activeuser",
            "email": "active@example.com",
            "role": "SB Member",
            "status": "Active",
            "permissions": ["view_documents", "download_documents"],
        },
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        actions = {
            row.action
            for row in db.query(models.AuditLog).filter(models.AuditLog.target_id == str(user_id)).all()
        }
        assert "USER_ROLE_CHANGED" in actions
        assert "USER_PERMISSIONS_CHANGED" in actions


def test_system_settings_are_backend_persisted_and_super_admin_only():
    reset_db()
    client = TestClient(main.app)
    super_headers = bearer_headers(client, "superuser", "pw123")

    settings_response = client.get("/system-settings", headers=super_headers)
    assert settings_response.status_code == 200, settings_response.text
    payload = settings_response.json()
    assert "organization_name" in payload["settings"]
    assert isinstance(payload["settings"]["organization_name"], str)

    update_response = client.put(
        "/system-settings",
        headers=super_headers,
        json={
            "settings": {
                "organization_name": "LGU Tolosa",
                "maintenance_mode": True,
                "public_portal_enabled": True,
            }
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()["settings"]
    assert updated["organization_name"] == "LGU Tolosa"
    assert updated["maintenance_mode"] is True
    assert updated["public_portal_enabled"] is True

    with SessionLocal() as db:
        stored = {row.key: row.value for row in db.query(models.SystemSetting).all()}
        assert stored["organization_name"] == "LGU Tolosa"
        assert stored["maintenance_mode"] == "true"

    employee_headers = bearer_headers(client, "activeuser", "pw123")
    blocked = client.put(
        "/system-settings",
        headers=employee_headers,
        json={"settings": {"maintenance_mode": False}},
    )
    assert blocked.status_code == 403


def test_storage_diagnostics_reports_missing_and_orphan_files():
    reset_db()
    client = TestClient(main.app)
    super_headers = bearer_headers(client, "superuser", "pw123")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    missing_path = os.path.join(UPLOAD_DIR, "missing-attachment.pdf")
    orphan_path = os.path.join(UPLOAD_DIR, "orphan-file.pdf")
    with open(orphan_path, "wb") as handle:
        handle.write(b"orphan-data")

    with SessionLocal() as db:
        doc = models.Document(
            tracking_number="DOC-STORAGE-001",
            title="Storage Diagnostic Document",
            status="Approved",
            priority="Medium",
            is_public=False,
            archived=False,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        db.add(models.Attachment(
            document_id=doc.id,
            original_filename="missing-attachment.pdf",
            stored_path=missing_path,
            mime_type="application/pdf",
            size=12,
            checksum="missingchecksum",
        ))
        db.commit()

    response = client.get("/storage/diagnostics", headers=super_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["missing_files"]
    assert any(item["stored_path"] == missing_path for item in payload["missing_files"])
    assert payload["orphan_files"]
    assert any(item["path"] == orphan_path for item in payload["orphan_files"])

    cleanup = client.post("/storage/cleanup-temp", headers=super_headers, json={"confirm": True})
    assert cleanup.status_code == 200, cleanup.text


def test_system_health_report_is_admin_only_and_reports_components():
    reset_db()
    client = TestClient(main.app)
    super_headers = bearer_headers(client, "superuser", "pw123")

    response = client.get("/system-health", headers=super_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"]
    assert payload["components"]["database"]["status"]
    assert payload["components"]["storage"]["status"]
    assert payload["components"]["audit"]["status"]

    employee_headers = bearer_headers(client, "activeuser", "pw123")
    blocked = client.get("/system-health", headers=employee_headers)
    assert blocked.status_code == 403


def test_analytics_reports_support_filters_and_csv_export():
    reset_db()
    client = TestClient(main.app)
    super_headers = bearer_headers(client, "superuser", "pw123")

    with SessionLocal() as db:
        doc = models.Document(
            tracking_number="DOC-REPORT-001",
            title="Quarterly Report Document",
            status="Approved",
            priority="High",
            document_type="Ordinance",
            category="Legislation",
            current_office="Office of the Mayor",
            is_public=False,
            archived=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.commit()

    report = client.get(
        "/analytics/reports",
        headers=super_headers,
        params={"status": "Approved", "document_type": "Ordinance"},
    )
    assert report.status_code == 200, report.text
    payload = report.json()
    assert payload["documents"]["total"] >= 1
    assert payload["filters"]["status"] == "Approved"
    assert payload["filters"]["document_type"] == "Ordinance"

    export = client.get(
        "/analytics/reports/export",
        headers=super_headers,
        params={"status": "Approved", "document_type": "Ordinance"},
    )
    assert export.status_code == 200, export.text
    assert "text/csv" in export.headers.get("content-type", "")
    assert "tracking_number" in export.text.lower()

    employee_headers = bearer_headers(client, "activeuser", "pw123")
    blocked = client.get("/analytics/reports", headers=employee_headers)
    assert blocked.status_code == 403


def test_backup_creation_and_verification_are_admin_only():
    reset_db()
    client = TestClient(main.app)
    super_headers = bearer_headers(client, "superuser", "pw123")

    response = client.post(
        "/backup/create",
        headers=super_headers,
        json={"confirm": True, "include_documents": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["backup"]["status"] == "created"
    assert payload["backup"]["location"]
    assert os.path.exists(payload["backup"]["location"])

    verify = client.get("/backup/verify", headers=super_headers)
    assert verify.status_code == 200, verify.text
    assert verify.json()["verified"] in {True, False}

    employee_headers = bearer_headers(client, "activeuser", "pw123")
    blocked = client.post(
        "/backup/create",
        headers=employee_headers,
        json={"confirm": True},
    )
    assert blocked.status_code == 403


def test_sb_member_defaults_allow_read_access_only():
    permissions = set(get_default_permissions_for_role("SB Member"))
    assert {
        "view_documents",
        "search_documents",
        "filter_documents",
        "view_document_details",
        "download_documents",
        "print_documents",
    } <= permissions
    for denied_permission in {
        "register_documents",
        "edit_documents",
        "archive_documents",
        "restore_documents",
        "delete_documents",
        "view_qr_tracking",
        "view_users",
        "view_audit_logs",
        "modify_system_settings",
    }:
        assert denied_permission not in permissions


def test_sb_member_cannot_use_administrative_or_tracking_permissions_directly():
    reset_db()
    with SessionLocal() as db:
        member = models.User(
            username="sbmember",
            hashed_password=get_password_hash("memberpass"),
            role="SB Member",
            permissions=str(get_default_permissions_for_role("SB Member")),
            status="Active",
            is_active=True,
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        for denied_permission in ("edit_documents", "archive_documents", "delete_documents", "view_qr_tracking", "view_users"):
            try:
                require_permission(member, denied_permission)
            except HTTPException as exc:
                assert exc.status_code == 403
            else:
                raise AssertionError(f"SB Member unexpectedly allowed: {denied_permission}")


def test_public_documents_include_only_public_safe_fields():
    reset_db()
    client = TestClient(main.app)
    with SessionLocal() as db:
        public_document = models.Document(
            tracking_number="DOC-PUBLIC-PHASE4",
            title="Public Phase Four Document",
            document_type="Ordinance",
            category="Public",
            description="Public description",
            status="Approved",
            priority="Medium",
            is_public=True,
            archived=False,
            originating_office="Internal Office",
            current_office="Internal Destination",
            author="Internal Author",
            session="Internal Session",
        )
        private_document = models.Document(
            tracking_number="DOC-PRIVATE-PHASE4",
            title="Private Phase Four Document",
            document_type="Ordinance",
            status="Approved",
            priority="Medium",
            is_public=False,
            archived=False,
        )
        db.add_all([public_document, private_document])
        db.commit()
    response = client.get("/public/documents", params={"search": "Phase Four"})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["tracking_number"] for item in items] == ["DOC-PUBLIC-PHASE4"]
    assert "status" not in items[0]
    assert "originating_office" not in items[0]
    assert "current_office" not in items[0]
    assert "author" not in items[0]
    assert "session" not in items[0]


def test_employee_cannot_change_public_visibility_without_explicit_permission():
    reset_db()
    client = TestClient(main.app)
    with SessionLocal() as db:
        document = models.Document(
            tracking_number="DOC-VISIBILITY-PHASE4",
            title="Visibility Test Document",
            status="Pending",
            priority="Medium",
            is_public=False,
            archived=False,
        )
        db.add(document)
        db.commit()
        document_id = document.id
    response = client.put(
        f"/documents/{document_id}",
        headers=bearer_headers(client, "activeuser"),
        json={"is_public": True},
    )
    assert response.status_code == 403


def test_audit_logs_support_affected_target_filtering():
    reset_db()
    client = TestClient(main.app)
    with SessionLocal() as db:
        db.add_all([
            models.AuditLog(actor="superuser", action="DOCUMENT_UPDATED", target_type="document", target_id="doc-audit-target", details="updated"),
            models.AuditLog(actor="superuser", action="USER_PERMISSIONS_CHANGED", target_type="User", target_id="account-audit-target", details="permissions changed"),
        ])
        db.commit()
    headers = bearer_headers(client)
    document_logs = client.get(
        "/audit/logs",
        headers=headers,
        params={"date_range": "all_time", "affected_document": "doc-audit-target"},
    )
    assert document_logs.status_code == 200, document_logs.text
    assert document_logs.json()["total"] == 1
    assert document_logs.json()["items"][0]["action"] == "DOCUMENT_UPDATED"

    account_logs = client.get(
        "/audit/logs",
        headers=headers,
        params={"date_range": "all_time", "affected_account": "account-audit-target"},
    )
    assert account_logs.status_code == 200, account_logs.text
    assert account_logs.json()["total"] == 1
    assert account_logs.json()["items"][0]["action"] == "USER_PERMISSIONS_CHANGED"

    export = client.get(
        "/audit/logs/export",
        headers=headers,
        params={"target_id": "doc-audit-target"},
    )
    assert export.status_code == 200, export.text
    assert "DOCUMENT_UPDATED" in export.text
    assert "doc-audit-target" in export.text


def test_login_refresh_logout_and_session_revocation():
    reset_db()
    client = TestClient(main.app)
    login = client.post("/auth/login", data={"username": "superuser", "password": "pw123"})
    assert login.status_code == 200, login.text
    refresh = client.post("/auth/refresh", data={"refresh_token": login.json()["refresh_token"]})
    assert refresh.status_code == 200, refresh.text

    with SessionLocal() as db:
        session = db.query(models.UserSession).first()
        assert session is not None
        session_id = session.session_id

    listed = client.get("/auth/sessions", headers={"Authorization": f"Bearer {refresh.json()['access_token']}"})
    assert listed.status_code == 200, listed.text
    assert any(item["session_id"] == session_id for item in listed.json())

    logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert logout.status_code == 200, logout.text
    revoked = client.get("/auth/users", headers={"Authorization": f"Bearer {refresh.json()['access_token']}"})
    assert revoked.status_code == 401


def test_administrator_can_revoke_session():
    reset_db()
    client = TestClient(main.app)
    login = client.post("/auth/login", data={"username": "superuser", "password": "pw123"})
    assert login.status_code == 200
    with SessionLocal() as db:
        session_id = db.query(models.UserSession).first().session_id
    response = client.post(
        f"/auth/sessions/{session_id}/revoke",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        session = db.query(models.UserSession).filter(models.UserSession.session_id == session_id).one()
        assert session.revoked_at is not None
