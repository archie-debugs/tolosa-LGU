from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
import Backends.backend.routes.documents as documents_routes
import Backends.SBmem_backend.main as sb_member_main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine
from tests.registration_fields import FILLED

models.Base.metadata.create_all(bind=engine)

PDF = b"%PDF-1.4\n%document management test\n%%EOF\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Keep uploaded files out of the real document storage.
    monkeypatch.setattr(documents_routes, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(documents_routes, "QR_IMAGE_DIR", str(tmp_path / "qr"))
    monkeypatch.setattr(sb_member_main, "UPLOAD_DIR", str(tmp_path))
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.add_all([
            models.Category(name="Finance"),
            models.Category(name="Health"),
            models.DocumentType(name="Ordinance"),
            models.Office(name="Office A"),
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True),
            models.User(username="member", hashed_password=get_password_hash("pw123"), role="SB Member",
                        permissions="['view_documents', 'download_documents']", status="Active", is_active=True),
        ])
        db.commit()
    return TestClient(main.app)


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def register(client, headers, filename="ordinance.pdf", content=PDF, **fields):
    data = {"title": "Ordinance No. 7 Series 2025", "series_year": "2025", **FILLED, **fields}
    return client.post("/documents/register", data=data, files={"file": (filename, content, "application/pdf")}, headers=headers)


def path_of(url):
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def test_admin_download_is_a_browser_link_on_the_public_address(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://192.168.1.8:8001")
    headers = headers_for(client, "admin")
    document = register(client, headers).json()
    attachment_id = document["attachments"][0]["id"]

    response = client.post(f"/documents/{document['id']}/attachments/{attachment_id}/download-token", headers=headers)
    assert response.status_code == 200, response.text
    download_url = response.json()["download_url"]
    assert download_url.startswith("http://192.168.1.8:8001/")

    download = client.get(path_of(download_url))
    assert download.status_code == 200, download.text
    assert download.content == PDF
    assert download.headers["content-disposition"].startswith("attachment")

    preview = client.post(f"/documents/{document['id']}/attachments/{attachment_id}/preview-token", headers=headers)
    assert preview.json()["preview_url"].startswith("http://192.168.1.8:8001/")
    preview_token = preview.json()["preview_url"].split("preview_token=", 1)[1]
    as_download = client.get(f"/documents/{document['id']}/attachments/{attachment_id}/download?download_token={preview_token}")
    assert as_download.status_code == 401

    with SessionLocal() as db:
        db.query(models.User).filter(models.User.username == "admin").update({"is_active": False, "status": "Inactive"})
        db.commit()
    assert client.get(path_of(download_url)).status_code in (401, 403)


def test_download_link_only_opens_its_own_attachment(client):
    headers = headers_for(client, "admin")
    first = register(client, headers).json()
    second = register(client, headers, filename="other.pdf", content=PDF + b"%second\n").json()

    link = client.post(f"/documents/{first['id']}/attachments/{first['attachments'][0]['id']}/download-token", headers=headers).json()["download_url"]
    token = link.split("download_token=", 1)[1]
    response = client.get(f"/documents/{second['id']}/attachments/{second['attachments'][0]['id']}/download?download_token={token}")
    assert response.status_code == 403


def test_sb_member_download_is_a_browser_link_and_respects_archiving(client, monkeypatch):
    monkeypatch.setenv("SBMEM_PUBLIC_URL", "http://192.168.1.8:8002")
    document = register(client, headers_for(client, "admin")).json()
    attachment_id = document["attachments"][0]["id"]
    sb_client = TestClient(sb_member_main.app)
    member = headers_for(client, "member")

    response = sb_client.post(f"/documents/{document['id']}/attachments/{attachment_id}/download-token", headers=member)
    assert response.status_code == 200, response.text
    download_url = response.json()["download_url"]
    assert download_url.startswith("http://192.168.1.8:8002/")

    download = sb_client.get(path_of(download_url))
    assert download.status_code == 200, download.text
    assert download.content == PDF

    with SessionLocal() as db:
        db.query(models.Document).filter(models.Document.id == document["id"]).update({"archived": True})
        db.commit()
    assert sb_client.get(path_of(download_url)).status_code == 403


def test_editing_clears_optional_fields_but_keeps_required_ones(client):
    headers = headers_for(client, "admin")
    document = register(client, headers, category="Finance", document_type="Ordinance", current_office="Office A").json()

    cleared = client.put(f"/documents/{document['id']}", json={"category": None}, headers=headers)
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert (body["category"], body["category_id"]) == (None, None)
    assert body["document_type"] == "Ordinance"
    assert body["current_office"] == "Office A"

    for payload, message in [
        ({"series_year": None}, "Legislative Year is required."),
        ({"priority": None}, "Priority is required."),
        ({"document_type": None}, "Choose the document type: Ordinance, Resolution or Letter Request."),
        ({"title": "  "}, "Title is required."),
        ({"current_office": None}, "A document moves to another office only by passing it (Pass), so the trail records the move."),
    ]:
        response = client.put(f"/documents/{document['id']}", json=payload, headers=headers)
        assert response.status_code == 400, payload
        assert response.json()["detail"] == message

    with SessionLocal() as db:
        stored = db.get(models.Document, document["id"])
        assert (stored.series_year, stored.priority) == (2025, "Medium")


def test_editing_cannot_archive_or_restore(client):
    headers = headers_for(client, "admin")
    document = register(client, headers).json()

    response = client.put(f"/documents/{document['id']}", json={"title": "Renamed", "archived": True}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["archived"] is False


def test_permanent_delete_requires_the_document_to_be_archived(client):
    headers = headers_for(client, "admin")
    document = register(client, headers).json()

    refused = client.delete(f"/documents/{document['id']}/permanent", headers=headers)
    assert refused.status_code == 400
    assert client.get(f"/documents/{document['id']}", headers=headers).status_code == 200

    assert client.delete(f"/documents/{document['id']}", headers=headers).status_code == 200
    assert client.delete(f"/documents/{document['id']}/permanent", headers=headers).status_code == 200
    assert client.get(f"/documents/{document['id']}", headers=headers).status_code == 404


def test_registration_accepts_only_document_files_and_keeps_just_the_file_name(client):
    headers = headers_for(client, "admin")

    rejected = register(client, headers, filename="setup.exe", content=b"MZ not a document")
    assert rejected.status_code == 400
    assert "Unsupported file type" in rejected.json()["detail"]

    accepted = register(client, headers, filename="../../ordinance.pdf")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["attachments"][0]["original_filename"] == "ordinance.pdf"


def test_every_registration_path_saves_the_category(client):
    headers = headers_for(client, "admin")
    single = register(client, headers, category="Finance").json()
    assert single["category"] == "Finance"

    upload = client.post("/documents/uploads/create_tmp_uploads", json={"files": [{"filename": "Resolution No. 5.pdf"}]}, headers=headers).json()["files"][0]
    assert client.put(path_of(upload["upload_url"]), content=PDF + b"%tmp\n").status_code == 200
    confirmed = client.post(
        "/documents/bulk-register/confirm_tmp",
        json={**FILLED, "tmp_names": [upload["tmp_name"]], "series_year": 2024, "category": "Health"},
        headers=headers,
    ).json()
    assert confirmed["registered"] == 1, confirmed
    bulk = client.get(f"/documents/{confirmed['documents'][0]['id']}", headers=headers).json()
    assert bulk["category"] == "Health"
