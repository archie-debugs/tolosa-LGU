from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
import Backends.backend.routes.documents as documents_routes
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

PDF = b"%PDF-1.4\n%due date test\n%%EOF\n"
BAD_DATE = "Due date must be a date like 2026-11-05."


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(documents_routes, "UPLOAD_DIR", str(tmp_path / "stored"))
    monkeypatch.setattr(documents_routes, "TEMP_UPLOAD_DIR", str(tmp_path / "tmp"))
    monkeypatch.setattr(documents_routes, "QR_IMAGE_DIR", str(tmp_path / "qr"))
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        records = models.Office(name="Records Office")
        db.add_all([records, models.DocumentType(name="Ordinance")])
        db.flush()
        db.add_all([
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True, office_id=records.id),
            models.User(username="clerk", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions="['register_documents', 'view_office_documents', 'view_office_document_details']",
                        status="Active", is_active=True, office_id=records.id),
        ])
        db.commit()
    return TestClient(main.app)


def headers_for(client, username="admin"):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def register(client, headers, **fields):
    return client.post("/documents/register", data={"title": "Ordinance No. 7", "series_year": "2025", **fields}, headers=headers)


def stored_due(document_id):
    with SessionLocal() as db:
        value = db.get(models.Document, document_id).due_date
        return value.isoformat() if value else None


def upload(client, headers, filename):
    created = client.post("/documents/uploads/create_tmp_uploads", json={"files": [{"filename": filename}]}, headers=headers)
    item = created.json()["files"][0]
    parts = urlsplit(item["upload_url"])
    assert client.put(f"{parts.path}?{parts.query}", content=PDF + filename.encode()).status_code == 200
    return item["tmp_name"]


def test_registering_with_a_due_date_stores_and_returns_it(client):
    response = register(client, headers_for(client), due_date="2026-11-05")

    assert response.status_code == 200, response.text
    assert response.json()["due_date"] == "2026-11-05"
    assert stored_due(response.json()["id"]) == "2026-11-05"


def test_due_date_is_optional(client):
    response = register(client, headers_for(client))

    assert response.status_code == 200, response.text
    assert response.json()["due_date"] is None


@pytest.mark.parametrize("value", ["05/11/2026", "2026-13-01", "soon"])
def test_registering_with_a_malformed_due_date_is_refused_before_anything_is_written(client, value):
    response = register(client, headers_for(client), due_date=value)

    assert response.status_code == 400
    assert response.json()["detail"] == BAD_DATE
    with SessionLocal() as db:
        assert db.query(models.Document).count() == 0


def test_multiple_registration_shares_the_due_date(client):
    headers = headers_for(client)
    names = [upload(client, headers, "a.pdf"), upload(client, headers, "b.pdf")]

    response = client.post("/documents/bulk-register/confirm_tmp", headers=headers, json={
        "tmp_names": names,
        "documents": [{"tmp_name": name, "series_year": 2025, "title": name} for name in names],
        "due_date": "2026-12-01",
    })

    assert response.status_code == 200, response.text
    documents = response.json()["documents"]
    assert len(documents) == 2
    assert [stored_due(doc["id"]) for doc in documents] == ["2026-12-01", "2026-12-01"]


def test_multiple_registration_refuses_a_malformed_due_date(client):
    headers = headers_for(client)
    name = upload(client, headers, "a.pdf")

    response = client.post("/documents/bulk-register/confirm_tmp", headers=headers, json={
        "tmp_names": [name], "documents": [{"tmp_name": name, "series_year": 2025, "title": "A"}], "due_date": "tomorrow",
    })

    assert response.status_code == 400
    assert response.json()["detail"] == BAD_DATE


def test_multipart_bulk_registration_accepts_a_due_date(client):
    response = client.post("/documents/bulk-register/confirm", headers=headers_for(client),
                           data={"series_years": ["2025"], "due_date": "2026-11-20"},
                           files=[("files", ("c.pdf", PDF + b"c", "application/pdf"))])

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert [d.due_date.isoformat() for d in db.query(models.Document)] == ["2026-11-20"]


def test_edit_sets_changes_and_clears_the_due_date(client):
    headers = headers_for(client)
    document = register(client, headers).json()

    assert client.put(f"/documents/{document['id']}", json={"due_date": "2026-11-30"}, headers=headers).json()["due_date"] == "2026-11-30"
    assert stored_due(document["id"]) == "2026-11-30"
    assert client.put(f"/documents/{document['id']}", json={"due_date": None}, headers=headers).json()["due_date"] is None
    refused = client.put(f"/documents/{document['id']}", json={"due_date": "30 Nov"}, headers=headers)
    assert refused.status_code == 400
    assert refused.json()["detail"] == BAD_DATE


def test_details_show_the_due_date_for_full_and_office_access(client):
    document = register(client, headers_for(client), due_date="2026-11-05").json()

    for username in ("admin", "clerk"):
        overview = client.get(f"/documents/{document['id']}/overview", headers=headers_for(client, username))
        assert overview.status_code == 200, overview.text
        assert overview.json()["document"]["due_date"] == "2026-11-05", username
