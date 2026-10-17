import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.SBmem_backend.main import app as sb_member_app
from Backends.backend import models
from Backends.backend.core import (
    ensure_default_super_admin_account,
    get_password_hash,
    normalize_user_role,
    user_has_permission,
    verify_password,
)
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

ROOT = Path(__file__).resolve().parents[1]
OFFICE_PERMISSIONS = [
    "pass_office_documents",
    "view_office_documents",
    "scan_qr",
    "confirm_document_receipt",
    "view_office_document_details",
    "view_office_history",
    "view_documents",
    "print_qr_codes",
]


def reset_db():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


def login(client, username, password="pw123"):
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def seed_three_offices(*, archived=False):
    """Office A holds DOC-000001; one employee per office."""
    with SessionLocal() as db:
        offices = [models.Office(name=f"Office {code}", office_code=code) for code in ("A", "B", "C")]
        db.add_all(offices)
        db.commit()
        doc = models.Document(
            tracking_number="DOC-000001",
            title="Private draft ordinance",
            is_public=False,
            archived=archived,
            qr_token="MixedCaseToken-AbC123",
            current_office_id=offices[0].id,
        )
        db.add(doc)
        db.commit()
        db.add(models.DocumentOffice(document_id=doc.id, office_id=offices[0].id))
        for index, office in enumerate(offices):
            db.add(models.User(
                username=f"employee{'abc'[index]}",
                hashed_password=get_password_hash("pw123"),
                role="Employee",
                office_id=office.id,
                permissions=str(OFFICE_PERMISSIONS),
                status="Active",
                is_active=True,
            ))
        db.commit()
        return doc.id, [office.id for office in offices]


def test_receipt_transfers_custody_so_documents_can_travel_several_offices():
    reset_db()
    client = TestClient(main.app)
    document_id, (office_a, office_b, office_c) = seed_three_offices()
    headers_a, headers_b = login(client, "employeea"), login(client, "employeeb")

    assert client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": office_b}, headers=headers_a).status_code == 200
    assert client.post("/documents/qr/MixedCaseToken-AbC123/receipt", headers=headers_b).json()["status"] == "confirmed"

    repeat = client.post("/documents/qr/MixedCaseToken-AbC123/receipt", headers=headers_b)
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["status"] == "already_confirmed"

    stale_sender = client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": office_c}, headers=headers_a)
    assert stale_sender.status_code == 403, stale_sender.text

    onward = client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": office_c}, headers=headers_b)
    assert onward.status_code == 200, onward.text

    with SessionLocal() as db:
        doc = db.get(models.Document, document_id)
        assert doc.current_office_id == office_b
        linked_offices = {row.office_id for row in db.query(models.DocumentOffice).filter_by(document_id=document_id)}
        assert linked_offices == {office_a, office_b}

    sender_history = client.get(f"/documents/{document_id}/handoffs", headers=headers_a)
    assert sender_history.status_code == 200, sender_history.text


def test_archived_documents_cannot_be_handed_off():
    reset_db()
    client = TestClient(main.app)
    document_id, (_, office_b, _) = seed_three_offices(archived=True)
    response = client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": office_b}, headers=login(client, "employeea"))
    assert response.status_code == 400, response.text


def test_qr_labels_route_is_not_captured_by_qr_lookup():
    reset_db()
    client = TestClient(main.app)
    seed_three_offices()
    response = client.get("/documents/qr/labels", headers=login(client, "employeea"))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"


def test_public_qr_lookup_requires_the_qr_token():
    reset_db()
    client = TestClient(main.app)
    seed_three_offices()
    accept_json = {"accept": "application/json"}

    for guess in ("DOC-000001", "1", "000001"):
        response = client.get(f"/qr/{guess}", headers=accept_json)
        assert response.status_code == 404, (guess, response.text)

    assert client.get("/qr/MixedCaseToken-AbC123", headers=accept_json).status_code == 200
    full_url = "https%3A%2F%2Fexample.test%2Fqr%2FMixedCaseToken-AbC123"
    assert client.get(f"/qr/{full_url}", headers=accept_json).status_code == 200


def test_deactivation_revokes_existing_sessions_and_tokens():
    reset_db()
    client = TestClient(main.app)
    seed_three_offices()
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
        employee_id = db.query(models.User).filter_by(username="employeea").one().id
    employee_headers = login(client, "employeea")
    assert client.get("/documents", headers=employee_headers).status_code == 200

    deactivated = client.post(f"/auth/users/{employee_id}/status", data={"status": "Inactive"}, headers=login(client, "admin"))
    assert deactivated.status_code == 200, deactivated.text

    assert client.get("/documents", headers=employee_headers).status_code == 401
    with SessionLocal() as db:
        sessions = db.query(models.UserSession).filter_by(user_id=employee_id).all()
        assert sessions and all(session.revoked_at is not None for session in sessions)


def test_sb_member_service_rejects_revoked_sessions():
    reset_db()
    with SessionLocal() as db:
        db.add(models.User(
            username="member",
            hashed_password=get_password_hash("pw123"),
            role="SB Member",
            permissions="['view_documents']",
            status="Active",
            is_active=True,
        ))
        db.commit()
    headers = login(TestClient(main.app), "member")
    sb_client = TestClient(sb_member_app)
    assert sb_client.get("/me", headers=headers).status_code == 200

    with SessionLocal() as db:
        for session in db.query(models.UserSession).all():
            session.revoke_reason = "logout"
            session.revoked_at = session.created_at
        db.commit()
    assert sb_client.get("/me", headers=headers).status_code == 401


def test_missing_role_grants_nothing():
    assert normalize_user_role(None) == ""
    assert normalize_user_role("  ") == ""
    blank_role_user = models.User(role="", office_id=1, permissions="['*']")
    assert not user_has_permission(blank_role_user, "view_documents")
    assert models.User.__table__.c.role.default.arg == "Employee"


def test_initial_admin_is_created_once_from_environment_and_never_reset(monkeypatch):
    reset_db()
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "first-admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "first-admin-pass")
    ensure_default_super_admin_account()
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(username="first-admin").one()
        assert normalize_user_role(admin.role) == "Super Administrator"
        admin.hashed_password = get_password_hash("changed-by-admin")
        db.commit()
        assert db.query(models.User).filter_by(username="a").first() is None

    ensure_default_super_admin_account()
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(username="first-admin").one()
        assert verify_password("changed-by-admin", admin.hashed_password)
        assert db.query(models.User).count() == 1


def test_initial_admin_is_skipped_without_configuration(monkeypatch):
    reset_db()
    monkeypatch.delenv("INITIAL_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)
    ensure_default_super_admin_account()
    with SessionLocal() as db:
        assert db.query(models.User).count() == 0


def test_health_does_not_expose_database_location():
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert "url" not in response.json()["database"]


def test_backend_refuses_to_start_without_jwt_secret():
    env = {**os.environ, "JWT_SECRET_KEY": "", "DATABASE_URL": "sqlite://"}
    # python-dotenv does not override variables that are already set, even to "".
    result = subprocess.run(
        [sys.executable, "-c", "import Backends.backend.auth_jwt"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "JWT_SECRET_KEY is required" in result.stderr
