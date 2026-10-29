import json
import os
import time
from datetime import datetime, timedelta, timezone
import pytest

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import UPLOAD_DIR, get_password_hash, verify_password
from Backends.backend.auth_jwt import create_access_token
from Backends.backend.database import SessionLocal, engine
from Backends.backend.core import OFFICE_WORKFLOW_PERMISSIONS, get_default_permissions_for_role, require_permission
from Backends.backend.routes import documents as documents_routes
from fastapi import HTTPException
from tests.registration_fields import FILLED

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
        db.query(models.DocumentTrackingNumberAlias).delete()
        db.query(models.DocumentAction).delete()
        db.query(models.DocumentHandoff).delete()
        db.query(models.DocumentOffice).delete()
        db.query(models.DocumentReceipt).delete()
        db.query(models.Attachment).delete()
        db.query(models.Document).delete()
        db.query(models.UserSession).delete()
        db.query(models.AuditLog).delete()
        db.query(models.SystemSetting).delete()
        db.query(models.User).delete()
        db.query(models.Office).delete()
        db.query(models.DocumentType).delete()
        db.query(models.RegistrationRequest).delete()
        db.add_all([
            models.Office(name="SB Secretariat"),
            models.Office(name="Office of the Mayor"),
            models.DocumentType(name="Ordinance"),
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


def test_each_type_counts_its_own_tracking_numbers_and_legacy_ids_are_kept():
    reset_db()
    with SessionLocal() as db:
        legacy = models.Document(
            tracking_number="DOC-32",
            title="ORDINANCE NO. 32 Series 1993",
            status="Approved",
            priority="Medium",
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id

        generated = []
        for document_type, year in (("Ordinance", 1994), ("Resolution", 1994), ("Ordinance", 1995), ("Letter Request", 1995)):
            document = models.Document(
                tracking_number="PENDING-test",
                title=f"{document_type} of {year}",
                document_type=document_type,
                status="Approved",
                priority="Medium",
            )
            generated.append(documents_routes._assign_system_tracking_number(db, document))
            db.commit()

        db.refresh(legacy)
        assert legacy.id == legacy_id
        assert legacy.tracking_number == "DOC-32"
        assert generated == ["ORD-000001", "RES-000001", "ORD-000002", "LTR-000001"]


def test_individual_registration_allows_repeated_number_across_series_years(monkeypatch):
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)

    with SessionLocal() as db:
        db.add(models.Document(
            tracking_number="DOC-4",
            title="ORDINANCE NO. 04 Series 1993",
            document_number="04",
            series_year=1993,
            status="Approved",
            priority="Medium",
        ))
        db.commit()

    registered = []
    for year in (1993, 1994, 1995):
        response = client.post(
            "/documents/register",
            headers=admin_headers,
            data={
                **FILLED,
                "title": f"ORDINANCE NO. 04 Series {year}",
                "document_number": "04",
                "series_year": str(year),
                "document_type": "Ordinance",
            },
        )
        assert response.status_code == 200, response.text
        registered.append(response.json())

    assert len({item["tracking_number"] for item in registered}) == 3
    assert [item["tracking_number"] for item in registered] == ["ORD-000001", "ORD-000002", "ORD-000003"]
    assert [(item["document_number"], item["series_year"]) for item in registered] == [
        ("04", 1993),
        ("04", 1994),
        ("04", 1995),
    ]
    with SessionLocal() as db:
        public_document = db.query(models.Document).filter(models.Document.id == registered[1]["id"]).one()
        public_document.is_public = True
        db.commit()

        qr_match = documents_routes._find_document_by_qr_or_tracking(db, registered[1]["tracking_number"])
        assert qr_match is not None
        assert qr_match.id == registered[1]["id"]

    admin_search = client.get("/documents", params={"search": "04", "year": "1994"}, headers=admin_headers)
    assert admin_search.status_code == 200, admin_search.text
    assert any(item["id"] == registered[1]["id"] for item in admin_search.json()["items"])

    public_search = client.get("/public/documents", params={"search": "04", "year": "1994"})
    assert public_search.status_code == 200, public_search.text
    assert [item["tracking_number"] for item in public_search.json()["items"]] == [registered[1]["tracking_number"]]
    year_search = client.get("/public/documents", params={"search": "1994"})
    assert any(item["tracking_number"] == registered[1]["tracking_number"] for item in year_search.json()["items"])

    with SessionLocal() as db:
        legacy = db.query(models.Document).filter(models.Document.tracking_number == "DOC-4").one()
        assert legacy.tracking_number == "DOC-4"


def test_qr_lookup_prefers_current_tracking_id_then_historical_alias():
    reset_db()
    with SessionLocal() as db:
        current_document = models.Document(
            tracking_number="ORD-000001",
            title="Current first record",
            status="Approved",
            priority="Medium",
        )
        historical_document = models.Document(
            tracking_number="ORD-000002",
            title="Historical alias target",
            status="Approved",
            priority="Medium",
        )
        resolution = models.Document(
            tracking_number="RES-000001",
            title="First resolution",
            status="Approved",
            priority="Medium",
        )
        db.add_all([current_document, historical_document, resolution])
        db.flush()
        db.add_all([
            models.DocumentTrackingNumberAlias(document_id=current_document.id, tracking_number="DOC-32"),
            models.DocumentTrackingNumberAlias(document_id=historical_document.id, tracking_number="RES-000506"),
        ])
        db.commit()

        find = documents_routes._find_document_by_qr_or_tracking
        assert find(db, "ORD-000001").id == current_document.id
        assert find(db, "ord 1").id == current_document.id
        assert find(db, "RES-1").id == resolution.id
        assert find(db, "2").id == historical_document.id
        assert find(db, "1") is None, "a bare number in two series names no single document"
        assert find(db, "DOC-32").id == current_document.id
        assert find(db, "res-506").id == historical_document.id


def test_document_registration_creates_stable_qr_token_and_public_qr_lookup(monkeypatch):
    reset_db()
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://192.168.1.8:8001")
    client = TestClient(main.app)
    headers = bearer_headers(client)
    response = client.post(
        "/documents/register",
        headers=headers,
        data={
            **FILLED,
            "title": "Stable QR document",
            "document_number": "07",
            "series_year": "2026",
            "document_type": "Ordinance",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["qr_token"]
    assert len(body["qr_token"]) >= 20
    assert body["canonical_qr_url"] == f"http://192.168.1.8:8001/qr/{body['qr_token']}"
    assert body["qr_code_value"] == body["canonical_qr_url"]

    public_lookup = client.get(f"/qr/{body['qr_token']}")
    assert public_lookup.status_code == 200, public_lookup.text
    assert public_lookup.json()["document_id"] == body["id"]
    assert public_lookup.json()["tracking_number"] == body["tracking_number"]
    assert set(public_lookup.json()) == {
        "document_id",
        "tracking_number",
        "title",
        "document_type",
        "current_office",
        "stage",
        "qr_token",
        "qr_payload",
    }

    monkeypatch.setenv("FRONTEND_PUBLIC_URL", "http://192.168.1.8:8550")
    browser_entry = client.get(
        f"/qr/{body['qr_token']}",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert browser_entry.status_code == 307
    assert browser_entry.headers["location"] == f"http://192.168.1.8:8550/qr/{body['qr_token']}"


def test_qr_png_cache_tracks_payload_and_explicit_regeneration_rewrites(tmp_path, monkeypatch):
    qr_dir = tmp_path / "qr"
    monkeypatch.setattr(documents_routes, "QR_IMAGE_DIR", str(qr_dir))
    document = models.Document(
        id=15,
        tracking_number="DOC-000015",
        title="QR Cache Test",
        qr_token="stable-qr-cache-token",
    )
    old_payload = "http://127.0.0.1:8001/qr/stable-qr-cache-token"
    current_payload = "http://192.168.1.8:8001/qr/stable-qr-cache-token"

    old_path = documents_routes._ensure_qr_png(document, old_payload)
    current_path = documents_routes._ensure_qr_png(document, current_payload)

    assert old_path != current_path
    assert os.path.exists(old_path)
    assert os.path.exists(current_path)

    import qrcode

    with open(current_path, "rb") as generated_file:
        correct_png = generated_file.read()
    qrcode.make(old_payload).save(current_path, format="PNG")
    with open(current_path, "rb") as stale_file:
        before_regeneration = stale_file.read()
    assert before_regeneration != correct_png

    documents_routes._ensure_qr_png(document, current_payload, force=True)
    with open(current_path, "rb") as regenerated_file:
        after_regeneration = regenerated_file.read()
    assert after_regeneration == correct_png


def test_bulk_registration_creates_original_1994_batch_with_separate_metadata(tmp_path, monkeypatch):
    reset_db()
    temp_upload_dir = tmp_path / "temporary"
    upload_dir = tmp_path / "uploads"
    qr_dir = tmp_path / "qr"
    temp_upload_dir.mkdir()
    monkeypatch.setattr(documents_routes, "TEMP_UPLOAD_DIR", str(temp_upload_dir))
    monkeypatch.setattr(documents_routes, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(documents_routes, "QR_IMAGE_DIR", str(qr_dir))

    legacy_numbers = (1, 2, 4, 5)
    with SessionLocal() as db:
        db.add_all([
            models.Document(
                tracking_number=f"DOC-{number}",
                title=f"ORDINANCE NO. {number:02d} Series 1993",
                document_number=f"{number:02d}",
                series_year=1993,
                status="Approved",
                priority="Medium",
            )
            for number in legacy_numbers
        ])
        db.commit()

    filenames = [
        "ORDINANCE No.01 Series 1994 AN ORDINANCE NAMING THE UNNAME HIGHSCHOOL SPORTS COMPLEX OF TOLOSA.pdf",
        "ORDINANCE No.02 Series 1994 AN ORDINANCE APPROPRIATING AN AMOUNT OF FIFTY THOUSAND PESOS.pdf",
        "ORDINANCE No.04 Series 1994 AN ORDINANCE RE-ROUTING THE TRAFFIC FOR PEDICAB.pdf",
        "ORDINANCE No.05 Series 1994 AN ORDINANCE APPROPRIATING AN AMOUNT OF TWENTY FIVE THOUSAND PESOS.pdf",
    ]
    tmp_names = []
    first_content = b""
    for index, filename in enumerate(filenames, start=1):
        tmp_name = f"batch-{index}.pdf"
        content = f"%PDF-1.4\nUnique test content {index}\n%%EOF".encode()
        (temp_upload_dir / tmp_name).write_bytes(content)
        if index == 1:
            first_content = content
        (temp_upload_dir / f"{tmp_name}.meta.json").write_text(
            json.dumps({"original_filename": filename}),
            encoding="utf-8",
        )
        tmp_names.append(tmp_name)

    client = TestClient(main.app)
    response = client.post(
        "/documents/bulk-register/confirm_tmp",
        headers=bearer_headers(client),
        json={
            **FILLED,
            "tmp_names": tmp_names,
            "documents": [
                {"tmp_name": tmp_name, "series_year": 1994}
                for tmp_name in tmp_names
            ],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["registered"] == 4, result.get("errors")
    assert result["failed"] == 0

    with SessionLocal() as db:
        created = db.query(models.Document).filter(models.Document.series_year == 1994).order_by(models.Document.document_number).all()
        assert [document.document_number for document in created] == ["01", "02", "04", "05"]
        assert [document.tracking_number for document in created] == [
            "ORD-000001",
            "ORD-000002",
            "ORD-000003",
            "ORD-000004",
        ]
        assert len({document.tracking_number for document in created}) == 4
        assert db.query(models.Document).filter(models.Document.tracking_number.in_(["DOC-1", "DOC-2", "DOC-4", "DOC-5"])).count() == 4

    duplicate_name = "duplicate.pdf"
    (temp_upload_dir / duplicate_name).write_bytes(first_content)
    (temp_upload_dir / f"{duplicate_name}.meta.json").write_text(
        json.dumps({"original_filename": "ORDINANCE No.01 Series 1994 DUPLICATE.pdf"}),
        encoding="utf-8",
    )
    duplicate_response = client.post(
        "/documents/bulk-register/confirm_tmp",
        headers=bearer_headers(client),
        json={
            **FILLED,
            "tmp_names": [duplicate_name],
            "documents": [{"tmp_name": duplicate_name, "series_year": 1994}],
        },
    )
    assert duplicate_response.status_code == 200, duplicate_response.text
    duplicate_result = duplicate_response.json()
    assert duplicate_result["registered"] == 0
    assert duplicate_result["failed"] == 1
    assert duplicate_result["errors"][0]["duplicate"] is True


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


def test_uploaded_documents_are_created_as_approved(monkeypatch):
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)

    response = client.post(
        "/documents/register",
        headers=admin_headers,
        data={**FILLED, "title": "Approved upload", "description": "test", "series_year": "1994"},
        files={"file": ("sample.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Approved"
    assert response.json()["series_year"] == 1994


def test_single_pdf_registration_rejects_missing_legislative_year():
    reset_db()
    client = TestClient(main.app)
    headers = bearer_headers(client)
    with SessionLocal() as db:
        documents_before = db.query(models.Document).count()
        attachments_before = db.query(models.Attachment).count()

    response = client.post(
        "/documents/register",
        headers=headers,
        data={"title": "ORDINANCE NO. 04 Series 1994"},
        files={"file": ("ORDINANCE NO. 04 Series 1994.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Legislative Year is required."
    with SessionLocal() as db:
        assert db.query(models.Document).count() == documents_before
        assert db.query(models.Attachment).count() == attachments_before


@pytest.mark.parametrize("file_count", [2, 5, 10])
def test_bulk_registration_requires_explicit_per_file_years(tmp_path, monkeypatch, file_count):
    reset_db()
    temp_upload_dir = tmp_path / "temporary"
    upload_dir = tmp_path / "uploads"
    qr_dir = tmp_path / "qr"
    temp_upload_dir.mkdir()
    monkeypatch.setattr(documents_routes, "TEMP_UPLOAD_DIR", str(temp_upload_dir))
    monkeypatch.setattr(documents_routes, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(documents_routes, "QR_IMAGE_DIR", str(qr_dir))

    years = [1993 + index % 3 for index in range(file_count)]
    tmp_names = []
    for index, year in enumerate(years, start=1):
        tmp_name = f"bulk-{file_count}-{index}.pdf"
        (temp_upload_dir / tmp_name).write_bytes(f"%PDF-1.4\nunique-{file_count}-{index}\n%%EOF".encode())
        (temp_upload_dir / f"{tmp_name}.meta.json").write_text(
            json.dumps({"original_filename": f"ORDINANCE No.{index:02d} Series 2026.pdf"}),
            encoding="utf-8",
        )
        tmp_names.append(tmp_name)

    client = TestClient(main.app)
    documents = [
        {"tmp_name": tmp_name, "series_year": year}
        for tmp_name, year in zip(tmp_names, years)
    ]
    response = client.post(
        "/documents/bulk-register/confirm_tmp",
        headers=bearer_headers(client),
        json={**FILLED, "tmp_names": tmp_names, "documents": documents},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["registered"] == file_count
    assert result["failed"] == 0

    with SessionLocal() as db:
        created = db.query(models.Document).order_by(models.Document.id).all()
        assert [document.series_year for document in created] == years
        assert [document.tracking_number for document in created] == [
            f"ORD-{index:06d}" for index in range(1, file_count + 1)
        ]


def test_bulk_registration_rejects_any_missing_legislative_year(tmp_path, monkeypatch):
    reset_db()
    temp_upload_dir = tmp_path / "temporary"
    temp_upload_dir.mkdir()
    monkeypatch.setattr(documents_routes, "TEMP_UPLOAD_DIR", str(temp_upload_dir))
    sequence_calls = []
    monkeypatch.setattr(documents_routes, "next_tracking_number", lambda db, document_type: sequence_calls.append(1) or "ORD-000001")

    tmp_names = ["has-year.pdf", "missing-year.pdf"]
    for tmp_name in tmp_names:
        (temp_upload_dir / tmp_name).write_bytes(b"%PDF-1.4 unique")
        (temp_upload_dir / f"{tmp_name}.meta.json").write_text(
            json.dumps({"original_filename": tmp_name}),
            encoding="utf-8",
        )

    client = TestClient(main.app)
    response = client.post(
        "/documents/bulk-register/confirm_tmp",
        headers=bearer_headers(client),
        json={
            "tmp_names": tmp_names,
            "documents": [
                {"tmp_name": tmp_names[0], "series_year": 1994},
                {"tmp_name": tmp_names[1], "series_year": None},
            ],
        },
    )
    assert response.status_code == 400
    assert "missing-year.pdf" in response.json()["detail"]
    assert sequence_calls == []
    with SessionLocal() as db:
        assert db.query(models.Document).count() == 0


def test_multipart_bulk_registration_requires_and_stores_each_year(tmp_path, monkeypatch):
    reset_db()
    upload_dir = tmp_path / "uploads"
    qr_dir = tmp_path / "qr"
    monkeypatch.setattr(documents_routes, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(documents_routes, "QR_IMAGE_DIR", str(qr_dir))
    client = TestClient(main.app)
    headers = bearer_headers(client)
    files = [
        ("files", ("first.pdf", b"%PDF-1.4 first", "application/pdf")),
        ("files", ("second.pdf", b"%PDF-1.4 second", "application/pdf")),
    ]

    missing_year = client.post(
        "/documents/bulk-register/confirm",
        headers=headers,
        files=files,
    )
    assert missing_year.status_code == 422
    with SessionLocal() as db:
        assert db.query(models.Document).count() == 0

    response = client.post(
        "/documents/bulk-register/confirm",
        headers=headers,
        data={**FILLED, "series_years": ["1993", "1995"]},
        files=files,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["registered"] == 2
    with SessionLocal() as db:
        created = db.query(models.Document).order_by(models.Document.tracking_number).all()
        assert [document.series_year for document in created] == [1993, 1995]
        assert [document.tracking_number for document in created] == ["ORD-000001", "ORD-000002"]


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
            "permissions": ["register_documents", "manage_permissions", "view_office_documents"],
        },
    )
    assert created.status_code == 200, created.text

    office_user = next(item for item in client.get("/auth/users", headers=admin_headers).json() if item["username"] == "officeuser")
    assert office_user["office_id"] == office_id
    assert office_user["department"] == "SB Secretariat"
    office_permissions = office_user["permissions"]
    # Only the office-workflow permissions the admin selected are kept.
    assert set(office_permissions) == {"view_office_documents"}

    updated = client.put(
        f"/auth/users/{office_user['id']}",
        headers=admin_headers,
        json={
            "full_name": "Office User",
            "username": "officeuser",
            "email": "office@example.com",
            "role": "Employee",
            "status": "Active",
            "permissions": office_permissions,
            "office_id": mayor_id,
        },
    )
    assert updated.status_code == 200, updated.text
    updated_user = next(item for item in client.get("/auth/users", headers=admin_headers).json() if item["username"] == "officeuser")
    assert updated_user["department"] == "Office of the Mayor"
    assert updated_user["permissions"] == office_permissions
    with SessionLocal() as db:
        assert db.query(models.AuditLog).filter(
            models.AuditLog.action == "USER_OFFICE_CHANGED",
            models.AuditLog.target_id == str(office_user["id"]),
        ).count() == 1


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


def test_office_workflow_permissions_require_employee_and_office_assignment():
    office_permissions = [
        "view_office_documents",
        "search_office_documents",
        "view_office_document_details",
        "scan_qr",
        "confirm_document_receipt",
        "view_office_history",
    ]
    from Backends.backend.core import validate_permissions

    assert set(validate_permissions(office_permissions)) == set(office_permissions)
    assert not set(office_permissions) & set(get_default_permissions_for_role("Employee"))
    assert not set(office_permissions) & set(get_default_permissions_for_role("SB Member"))
    assigned_employee = models.User(role="Employee", office_id=12, permissions=str(office_permissions))
    unassigned_employee = models.User(role="Employee", office_id=None, permissions=str(office_permissions))
    office_assigned_sb_member = models.User(role="SB Member", office_id=12, permissions=str(office_permissions))
    super_admin = models.User(role="Super Administrator", office_id=None, permissions="['*']")

    for permission in office_permissions:
        require_permission(assigned_employee, permission)
        require_permission(super_admin, permission)
        for user in (unassigned_employee, office_assigned_sb_member):
            with pytest.raises(HTTPException) as denied:
                require_permission(user, permission)
            assert denied.value.status_code == 403

    with pytest.raises(HTTPException) as unknown:
        validate_permissions(["office_admin_all"])
    assert unknown.value.status_code == 400


def test_employee_office_document_list_is_scoped_by_office_and_permission():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)

    with SessionLocal() as db:
        office_a = models.Office(name="Office of the Mayor - Office List", office_code="MAYLIST")
        office_b = models.Office(name="Treasury Office - Office List", office_code="TRSLIST")
        db.add_all([office_a, office_b])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)

        doc_a_1 = models.Document(
            tracking_number="DOC-000901",
            title="Office List Document A1",
            status="Approved",
            priority="Medium",
            current_office_id=office_a.id,
            current_office="Office of the Mayor - Office List",
            qr_token="office-list-a-1",
            qr_code_value="https://example.test/qr/office-list-a-1",
        )
        doc_a_2 = models.Document(
            tracking_number="DOC-000902",
            title="Office List Document A2",
            status="Pending",
            priority="High",
            current_office_id=office_a.id,
            current_office="Office of the Mayor - Office List",
            qr_token="office-list-a-2",
            qr_code_value="https://example.test/qr/office-list-a-2",
        )
        doc_b = models.Document(
            tracking_number="DOC-000903",
            title="Treasury Office Document B",
            status="Approved",
            priority="Medium",
            current_office_id=office_b.id,
            current_office="Treasury Office - Office List",
            qr_token="office-list-b-1",
            qr_code_value="https://example.test/qr/office-list-b-1",
        )
        db.add_all([doc_a_1, doc_a_2, doc_b])
        db.commit()
        db.refresh(doc_a_1)
        db.refresh(doc_a_2)
        db.refresh(doc_b)
        office_a_id = office_a.id
        office_b_id = office_b.id
        office_a_doc_ids = {doc_a_1.id, doc_a_2.id}
        for document_id, office_id in (
            (doc_a_1.id, office_a.id),
            (doc_a_2.id, office_a.id),
            (doc_b.id, office_b.id),
        ):
            existing_link = db.query(models.DocumentOffice).filter(
                models.DocumentOffice.document_id == document_id,
                models.DocumentOffice.office_id == office_id,
            ).first()
            if existing_link is None:
                db.add(models.DocumentOffice(document_id=document_id, office_id=office_id))
        db.commit()

        office_user = models.User(
            username="officelister",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=office_a.id,
            permissions="['view_office_documents', 'search_office_documents', 'view_office_document_details']",
            status="Active",
            is_active=True,
        )
        unassigned_user = models.User(
            username="unassignedofficelister",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=None,
            permissions="['view_office_documents', 'search_office_documents', 'view_office_document_details']",
            status="Active",
            is_active=True,
        )
        office_readonly_user = models.User(
            username="officereadonly",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=office_a.id,
            permissions="['view_office_documents']",
            status="Active",
            is_active=True,
        )
        office_denied_user = models.User(
            username="officedenied",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=office_a.id,
            permissions="[]",
            status="Active",
            is_active=True,
        )
        db.add_all([office_user, unassigned_user, office_readonly_user, office_denied_user])
        db.commit()

    office_headers = bearer_headers(client, "officelister", "pw123")
    response = client.get("/documents/office", headers=office_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 2
    ids = {item["id"] for item in payload["items"]}
    assert office_a_doc_ids == ids
    assert all(item["office_receipt_status"] == "Not Yet Received" for item in payload["items"])
    assert all(item.get("current_office") is None and item.get("priority") is None and not item.get("history_rows") for item in payload["items"])
    assert payload["total_pages"] == 1
    supplied_office = client.get(f"/documents/office?office_id={office_b_id}", headers=office_headers)
    assert {item["id"] for item in supplied_office.json()["items"]} == office_a_doc_ids
    page_one = client.get("/documents/office?page=1&page_size=1", headers=office_headers).json()
    page_two = client.get("/documents/office?page=2&page_size=1", headers=office_headers).json()
    assert page_one["total"] == 2 and page_one["total_pages"] == 2 and len(page_one["items"]) == 1
    assert page_two["page"] == 2 and page_two["items"][0]["id"] != page_one["items"][0]["id"]
    searched = client.get("/documents/office?search=A1", headers=office_headers)
    assert searched.status_code == 200 and searched.json()["total"] == 1
    assert client.get(f"/documents/office/{next(iter({item['id'] for item in payload['items']}))}", headers=office_headers).status_code == 200
    assert client.get(f"/documents/office/{max(office_a_doc_ids) + 1}", headers=office_headers).status_code in {403, 404}

    denied = client.get("/documents/office", headers=bearer_headers(client, "unassignedofficelister", "pw123"))
    assert denied.status_code == 403, denied.text
    assert client.get("/documents/office?search=Ordinance", headers=bearer_headers(client, "officereadonly", "pw123")).status_code == 403
    assert client.get("/documents/office", headers=bearer_headers(client, "officedenied", "pw123")).status_code == 403
    assert client.get(
        f"/documents/{next(iter(office_a_doc_ids))}/receipts",
        headers=bearer_headers(client, "officereadonly", "pw123"),
    ).status_code == 403


def test_office_qr_lookup_requires_matching_office_assignment():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)

    with SessionLocal() as db:
        office_a = models.Office(name="Office of the Mayor - QR Test", office_code="MAYQR")
        office_b = models.Office(name="Treasury Office - QR Test", office_code="TRSQR")
        db.add_all([office_a, office_b])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)

        doc = models.Document(
            tracking_number="DOC-000900",
            title="City Budget Ordinance",
            status="Approved",
            priority="Medium",
            current_office_id=office_b.id,
            current_office="Treasury Office - QR Test",
            qr_token="office-access-token-123",
            qr_code_value="https://example.test/qr/office-access-token-123",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        if not db.query(models.DocumentOffice).filter(
            models.DocumentOffice.document_id == doc.id,
            models.DocumentOffice.office_id == office_b.id,
        ).first():
            db.add(models.DocumentOffice(document_id=doc.id, office_id=office_b.id))
            db.commit()
        document_id = doc.id
        qr_token = doc.qr_token

        office_user = models.User(
            username="mayorstaff",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=office_a.id,
            permissions="['scan_qr', 'view_office_documents', 'view_office_document_details']",
            status="Active",
            is_active=True,
        )
        other_user = models.User(
            username="treasurystaff",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=office_b.id,
            permissions="['scan_qr', 'view_office_documents', 'view_office_document_details']",
            status="Active",
            is_active=True,
        )
        no_office_user = models.User(
            username="unassignedstaff",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=None,
            permissions="['scan_qr', 'view_office_document_details']",
            status="Active",
            is_active=True,
        )
        missing_permission_user = models.User(
            username="limitedstaff",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=office_a.id,
            permissions="[]",
            status="Active",
            is_active=True,
        )
        db.add_all([office_user, other_user, no_office_user, missing_permission_user])
        db.commit()
        db.refresh(office_user)
        db.refresh(other_user)
        db.add(models.DocumentHandoff(
            document_id=document_id,
            sending_office_id=office_b.id,
            receiving_office_id=office_a.id,
            sending_employee_id=other_user.id,
            status="Pending Receipt",
        ))
        db.commit()

    office_headers = bearer_headers(client, "mayorstaff", "pw123")
    allowed = client.get(f"/documents/qr/{qr_token}/office", headers=office_headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["document_id"] == document_id

    other_headers = bearer_headers(client, "treasurystaff", "pw123")
    denied = client.get(f"/documents/qr/{qr_token}/office", headers=other_headers)
    assert denied.status_code == 403, denied.text
    assert "not pending receipt at your office" in denied.json()["detail"].lower()

    no_office_headers = bearer_headers(client, "unassignedstaff", "pw123")
    no_office = client.get(f"/documents/qr/{qr_token}/office", headers=no_office_headers)
    assert no_office.status_code == 403, no_office.text
    assert no_office.json()["detail"] == "Office assignment required for QR access"

    missing_permission_headers = bearer_headers(client, "limitedstaff", "pw123")
    missing_permission = client.get(f"/documents/qr/{qr_token}/office", headers=missing_permission_headers)
    assert missing_permission.status_code == 403, missing_permission.text
    assert missing_permission.json()["detail"] == "Permission denied"

    not_found = client.get("/documents/qr/unknown-office-qr-token/office", headers=office_headers)
    assert not_found.status_code == 404, not_found.text
    assert not_found.json()["detail"] == "QR code not recognized"


def test_document_receipt_confirmation_and_history_are_office_scoped():
    reset_db()
    client = TestClient(main.app)

    with SessionLocal() as db:
        office_a = db.query(models.Office).filter(models.Office.name == "SB Secretariat").first()
        office_b = db.query(models.Office).filter(models.Office.name == "Office of the Mayor").first()
        office_a_id = office_a.id
        office_b_id = office_b.id

        doc = models.Document(
            tracking_number="DOC-000700",
            title="Receipt Test Ordinance",
            status="Approved",
            priority="Medium",
            current_office_id=office_b_id,
            current_office="Office of the Mayor",
            qr_token="receipt-confirmation-token-001",
            qr_code_value="https://example.test/qr/receipt-confirmation-token-001",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        if not db.query(models.DocumentOffice).filter(
            models.DocumentOffice.document_id == doc.id,
            models.DocumentOffice.office_id == office_b_id,
        ).first():
            db.add(models.DocumentOffice(document_id=doc.id, office_id=office_b_id))
            db.commit()
        qr_token = doc.qr_token
        document_id = doc.id
        office_c = models.Office(name="Unrelated Office - Receipt Test", office_code="UNRREC")
        db.add(office_c)
        db.commit()
        office_c_id = office_c.id

        employee_a = models.User(
            username="receiptusera",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=office_a_id,
            permissions="['scan_qr', 'confirm_document_receipt', 'pass_office_documents', 'view_office_documents', 'view_office_document_details', 'view_office_history']",
            status="Active",
            is_active=True,
        )
        employee_b = models.User(
            username="receiptuserb",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=office_b_id,
            permissions="['scan_qr', 'confirm_document_receipt', 'view_office_documents', 'view_office_document_details', 'view_office_history']",
            status="Active",
            is_active=True,
        )
        employee_c = models.User(
            username="receiptuserc",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            office_id=office_c_id,
            permissions="['scan_qr', 'confirm_document_receipt', 'view_office_documents', 'view_office_document_details', 'view_office_history']",
            status="Active",
            is_active=True,
        )
        db.add_all([employee_a, employee_b, employee_c])
        db.commit()
        db.add(models.DocumentHandoff(
            document_id=document_id,
            sending_office_id=office_b_id,
            receiving_office_id=office_a_id,
            sending_employee_id=employee_b.id,
            status="Pending Receipt",
        ))
        db.commit()

    office_a_headers = bearer_headers(client, "receiptusera", "pw123")
    confirm = client.post(f"/documents/qr/{qr_token}/receipt", headers=office_a_headers)
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "confirmed"
    assert confirm.json()["receipt"]["office_id"] == office_a_id
    assert confirm.json()["receipt"]["document_id"] == document_id

    repeat = client.post(f"/documents/qr/{qr_token}/receipt", headers=office_a_headers)
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["status"] == "already_confirmed"

    office_b_headers = bearer_headers(client, "receiptuserb", "pw123")
    deny = client.post(f"/documents/qr/{qr_token}/receipt", headers=office_b_headers)
    assert deny.status_code == 403, deny.text
    assert "not pending receipt at your office" in deny.json()["detail"].lower()

    history = client.get(f"/documents/{document_id}/receipts", headers=office_a_headers)
    assert history.status_code == 200, history.text
    assert len(history.json()["receipts"]) == 1
    assert history.json()["receipts"][0]["office_id"] == office_a_id
    office_history = client.get("/documents/office/history", headers=office_a_headers)
    assert office_history.status_code == 200 and office_history.json()["total"] == 1
    office_list_after_confirm = client.get("/documents/office", headers=office_a_headers).json()
    assert next(item for item in office_list_after_confirm["items"] if item["id"] == document_id)["office_receipt_status"] == "Received"
    received_filter = client.get("/documents/office?receipt_status=received", headers=office_a_headers).json()
    not_received_filter = client.get("/documents/office?receipt_status=not_yet_received", headers=office_a_headers).json()
    assert received_filter["total"] == 1 and received_filter["items"][0]["id"] == document_id
    assert not_received_filter["total"] == 0

    office_c_headers = bearer_headers(client, "receiptuserc", "pw123")
    forbidden_history = client.get(f"/documents/{document_id}/receipts", headers=office_c_headers)
    assert forbidden_history.status_code == 403, forbidden_history.text

    # Receipt made office A the holder, so A (not the original sender) can pass it back to B.
    returned = client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": office_b_id}, headers=office_a_headers)
    assert returned.status_code == 200, returned.text
    office_b_confirm = client.post(f"/documents/qr/{qr_token}/receipt", headers=office_b_headers)
    assert office_b_confirm.status_code == 200, office_b_confirm.text
    assert office_b_confirm.json()["receipt"]["office_id"] == office_b_id
    office_b_history = client.get(f"/documents/{document_id}/receipts", headers=office_b_headers)
    assert office_b_history.status_code == 200
    assert [row["office_id"] for row in office_b_history.json()["receipts"]] == [office_b_id]
    office_b_documents = client.get("/documents/office", headers=office_b_headers).json()
    assert office_b_documents["items"][0]["office_receipt_status"] == "Received"


def test_super_admin_office_management_and_inactive_assignment_retention():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)

    created_office = client.post(
        "/offices",
        headers=admin_headers,
        json={"name": "Municipal Planning Office", "office_code": "mpo"},
    )
    assert created_office.status_code == 200, created_office.text
    office = created_office.json()
    assert office["office_code"] == "MPO"
    assert office["is_active"] is True

    duplicate_code = client.post(
        "/offices",
        headers=admin_headers,
        json={"name": "Planning and Development Office", "office_code": "MPO"},
    )
    assert duplicate_code.status_code == 409
    duplicate_name = client.post(
        "/offices",
        headers=admin_headers,
        json={"name": "Municipal Planning Office", "office_code": "MPO-2"},
    )
    assert duplicate_name.status_code == 409

    created_user = client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "username": "mpoemployee",
            "password": "securepass",
            "full_name": "MPO Employee",
            "email": "mpo@example.com",
            "role": "Employee",
            "office_id": office["id"],
        },
    )
    assert created_user.status_code == 200, created_user.text
    assert created_user.json()["office_id"] == office["id"]
    assert created_user.json()["permissions"] == sorted(OFFICE_WORKFLOW_PERMISSIONS)

    internal_user = client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "username": "internalemployee",
            "password": "securepass",
            "full_name": "Internal Employee",
            "email": "internal@example.com",
            "role": "Employee",
        },
    )
    assert internal_user.status_code == 200, internal_user.text
    assert internal_user.json()["office_id"] is None
    assert "edit_documents" in internal_user.json()["permissions"]

    permission_account = client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "username": "officepermissionuser",
            "password": "securepass",
            "full_name": "Office Permission User",
            "email": "office-permissions@example.com",
            "role": "Employee",
            "office_id": office["id"],
            "permissions": ["view_office_documents", "scan_qr"],
        },
    )
    assert permission_account.status_code == 200, permission_account.text
    assert permission_account.json()["permissions"] == ["scan_qr", "view_office_documents"]
    assert "edit_documents" not in permission_account.json()["permissions"]

    listed_offices = client.get("/offices", headers=admin_headers)
    assert listed_offices.status_code == 200, listed_offices.text
    assert next(item for item in listed_offices.json() if item["id"] == office["id"])["user_count"] == 2

    renamed_office = client.put(
        f"/offices/{office['id']}",
        headers=admin_headers,
        json={"name": "Municipal Planning and Development Office", "office_code": "MPDO", "is_active": True},
    )
    assert renamed_office.status_code == 200, renamed_office.text
    assert renamed_office.json()["name"] == "Municipal Planning and Development Office"
    assert renamed_office.json()["office_code"] == "MPDO"

    updated_office = client.put(
        f"/offices/{office['id']}",
        headers=admin_headers,
        json={"name": "Municipal Planning and Development Office", "office_code": "MPDO", "is_active": False},
    )
    assert updated_office.status_code == 200, updated_office.text
    assert updated_office.json()["is_active"] is False
    assert office["id"] not in [item["id"] for item in client.get("/auth/offices", headers=admin_headers).json()]

    office_users = client.get(f"/offices/{office['id']}/users", headers=admin_headers)
    assert office_users.status_code == 200, office_users.text
    assert [item["username"] for item in office_users.json()] == ["mpoemployee", "officepermissionuser"]

    inactive_assignment = client.post(
        "/auth/register",
        headers=admin_headers,
        json={
            "username": "inactiveofficeemployee",
            "password": "securepass",
            "full_name": "Inactive Office Employee",
            "email": "inactive-office@example.com",
            "role": "Employee",
            "office_id": office["id"],
        },
    )
    assert inactive_assignment.status_code == 400

    updated_user = client.put(
        f"/auth/users/{created_user.json()['id']}",
        headers=admin_headers,
        json={
            "full_name": "MPO Employee Updated",
            "username": "mpoemployee",
            "email": "mpo@example.com",
            "role": "Employee",
            "status": "Active",
            "permissions": ["view_office_documents", "scan_qr"],
        },
    )
    assert updated_user.status_code == 200, updated_user.text
    saved_user = next(item for item in client.get("/auth/users", headers=admin_headers).json() if item["username"] == "mpoemployee")
    assert saved_user["office_id"] == office["id"]
    assert saved_user["permissions"] == ["scan_qr", "view_office_documents"]

    removed_permissions = client.put(
        f"/auth/users/{created_user.json()['id']}",
        headers=admin_headers,
        json={
            "full_name": "MPO Employee Updated",
            "username": "mpoemployee",
            "email": "mpo@example.com",
            "role": "Employee",
            "status": "Active",
            "permissions": [],
        },
    )
    assert removed_permissions.status_code == 200, removed_permissions.text
    saved_user = next(item for item in client.get("/auth/users", headers=admin_headers).json() if item["username"] == "mpoemployee")
    assert saved_user["office_id"] == office["id"]
    assert saved_user["permissions"] == []

    with SessionLocal() as db:
        assert db.query(models.AuditLog).filter(models.AuditLog.action == "OFFICE_CREATED").count() == 1
        assert db.query(models.AuditLog).filter(models.AuditLog.action == "OFFICE_UPDATED").count() == 2
        assert db.query(models.AuditLog).filter(models.AuditLog.action == "USER_OFFICE_ASSIGNED").count() == 2
        assert db.query(models.AuditLog).filter(models.AuditLog.action == "USER_PERMISSIONS_CHANGED").count() == 2


def test_non_super_admin_cannot_manage_offices_or_assign_office():
    reset_db()
    client = TestClient(main.app)
    admin_headers = bearer_headers(client)
    with SessionLocal() as db:
        office = models.Office(name="Planning Office", office_code="PLAN")
        manager = models.User(
            username="officemanager",
            hashed_password=get_password_hash("managerpass"),
            role="Employee",
            permissions="['view_users', 'create_users', 'edit_users']",
            status="Active",
            is_active=True,
        )
        target = models.User(
            username="office-target",
            hashed_password=get_password_hash("targetpass"),
            role="Employee",
            permissions="['view_documents']",
            status="Active",
            is_active=True,
        )
        db.add_all([office, manager, target])
        db.commit()
        office_id = office.id
        manager_id = manager.id
        target_id = target.id

    manager_headers = bearer_headers(client, "officemanager", "managerpass")
    assert client.get("/offices", headers=manager_headers).status_code == 403
    assert client.post(
        "/offices",
        headers=manager_headers,
        json={"name": "Unauthorized Office", "office_code": "NOPE"},
    ).status_code == 403

    self_assignment = client.put(
        f"/auth/users/{manager_id}",
        headers=manager_headers,
        json={
            "full_name": "Office Manager",
            "username": "officemanager",
            "email": "manager@example.com",
            "role": "Employee",
            "status": "Active",
            "permissions": ["view_users", "create_users", "edit_users"],
            "office_id": office_id,
        },
    )
    assert self_assignment.status_code == 403, self_assignment.text

    assignment = client.put(
        f"/auth/users/{target_id}",
        headers=manager_headers,
        json={
            "full_name": "Office Target",
            "username": "office-target",
            "email": "target@example.com",
            "role": "Employee",
            "status": "Active",
            "permissions": ["view_documents"],
            "office_id": office_id,
        },
    )
    assert assignment.status_code == 403, assignment.text

    account_assignment = client.post(
        "/auth/register",
        headers=manager_headers,
        json={
            "username": "managed-office-target",
            "password": "securepass",
            "full_name": "Managed Office Target",
            "email": "managed-target@example.com",
            "role": "Employee",
            "office_id": office_id,
        },
    )
    assert account_assignment.status_code == 403, account_assignment.text


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


def test_unauthenticated_registration_cannot_create_an_account_or_assign_super_admin():
    reset_db()
    client = TestClient(main.app)
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Public Applicant",
            "email": "public@example.com",
            "username": "public-admin",
            "password": "securepass",
            "role": "Super Administrator",
        },
    )
    assert response.status_code == 403
    with SessionLocal() as db:
        assert db.query(models.User).filter(models.User.username == "public-admin").first() is None


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


def test_role_definitions_are_served_from_the_server():
    reset_db()
    client = TestClient(main.app)
    with SessionLocal() as db:
        manager = models.User(
            username="user-manager",
            hashed_password=get_password_hash("managerpass"),
            role="Employee",
            permissions="['view_users']",
            status="Active",
            is_active=True,
        )
        db.add(manager)
        db.commit()
    manager_headers = bearer_headers(client, "user-manager", "managerpass")

    roles = client.get("/auth/roles", headers=manager_headers)
    assert roles.status_code == 200, roles.text
    role_map = {item["name"]: item["permissions"] for item in roles.json()}
    assert set(role_map["SB Member"]) >= {"view_documents", "download_documents"}
    assert role_map["Super Administrator"] == ["*"]


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
            document_number="04",
            series_year=1994,
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
    assert "document_number" in export.text.lower()
    assert "series_year" in export.text.lower()
    assert "DOC-REPORT-001,04,1994" in export.text

    employee_headers = bearer_headers(client, "activeuser", "pw123")
    blocked = client.get("/analytics/reports", headers=employee_headers)
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
    assert client.post("/auth/login", data={"username": "activeuser", "password": "pw123"}).status_code == 200
    with SessionLocal() as db:
        employee = db.query(models.User).filter(models.User.username == "activeuser").one()
        session_id = db.query(models.UserSession).filter(models.UserSession.user_id == employee.id).one().session_id
    response = client.post(
        f"/auth/sessions/{session_id}/revoke",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        session = db.query(models.UserSession).filter(models.UserSession.session_id == session_id).one()
        assert session.revoked_at is not None
