from urllib.parse import urlparse

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.auth_jwt import create_download_token
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

EMPLOYEE_PERMISSIONS = ["view_documents", "pass_office_documents", "view_office_documents", "print_qr_codes"]


def setup_documents():
    """Office A holds four documents: 1 is public with a file, 2 has a file and is
    sent to Office B, 3 has nothing, 4 is archived."""
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        offices = {code: models.Office(name=f"Office {code}", office_code=f"OFF{code}") for code in "AB"}
        db.add_all(offices.values())
        db.commit()
        db.add_all([
            models.User(username="emp_a", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions=str(EMPLOYEE_PERMISSIONS), office_id=offices["A"].id, status="Active", is_active=True),
            models.User(username="viewer", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions=str(["view_documents"]), office_id=offices["A"].id, status="Active", is_active=True),
        ])
        documents = [
            models.Document(tracking_number=f"DOC-00000{index}", title=f"Document {index}", status="Approved", priority="Medium",
                            qr_token=f"documents-list-{index}", current_office="Office A", current_office_id=offices["A"].id,
                            is_public=index == 1, archived=index == 4)
            for index in range(1, 5)
        ]
        db.add_all(documents)
        db.commit()
        db.add_all([
            models.Attachment(document_id=documents[index].id, original_filename="file.pdf", stored_path="missing.pdf", mime_type="application/pdf")
            for index in (0, 1)
        ])
        db.commit()
        return {code: office.id for code, office in offices.items()}, {doc.tracking_number: doc.id for doc in documents}


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def numbers(payload):
    return sorted(item["tracking_number"] for item in payload["items"])


def test_list_shows_documents_in_transit_and_counts_the_whole_list():
    offices, documents = setup_documents()
    client = TestClient(main.app)
    headers = headers_for(client, "emp_a")
    response = client.post(f"/documents/{documents['DOC-000002']}/handoffs", json={"receiving_office_id": offices["B"]}, headers=headers)
    assert response.status_code == 200, response.text

    payload = client.get("/documents", params={"search": "Document 1"}, headers=headers).json()
    assert payload["summary"] == {"total": 3, "in_transit": 1, "public": 1, "without_attachment": 1}
    assert payload["available_statuses"] == ["Approved"]

    payload = client.get("/documents", params={"location": "in_transit"}, headers=headers).json()
    assert numbers(payload) == ["DOC-000002"]
    assert payload["items"][0]["in_transit_to"] == "Office B"
    assert payload["items"][0]["in_transit_since"] is not None
    payload = client.get("/documents", params={"location": "at_office"}, headers=headers).json()
    assert numbers(payload) == ["DOC-000001", "DOC-000003"]
    assert all(item["in_transit_to"] is None for item in payload["items"])
    assert client.get("/documents", params={"location": "elsewhere"}, headers=headers).status_code == 400


def test_list_filters_by_visibility_and_attachment():
    setup_documents()
    client = TestClient(main.app)
    headers = headers_for(client, "emp_a")
    assert numbers(client.get("/documents", params={"visibility": "public"}, headers=headers).json()) == ["DOC-000001"]
    assert numbers(client.get("/documents", params={"visibility": "private"}, headers=headers).json()) == ["DOC-000002", "DOC-000003"]
    assert numbers(client.get("/documents", params={"has_attachment": "false"}, headers=headers).json()) == ["DOC-000003"]
    assert numbers(client.get("/documents", params={"has_attachment": "true"}, headers=headers).json()) == ["DOC-000001", "DOC-000002"]


def test_qr_labels_download_through_a_short_lived_link():
    _, documents = setup_documents()
    client = TestClient(main.app)
    headers = headers_for(client, "emp_a")

    assert client.post("/documents/qr/labels/download-token", json={"ids": []}, headers=headers).status_code == 400
    assert client.post("/documents/qr/labels/download-token", json={"ids": [documents["DOC-000001"]]}, headers=headers_for(client, "viewer")).status_code == 403

    response = client.post("/documents/qr/labels/download-token", json={"ids": [documents["DOC-000001"], documents["DOC-000003"]]}, headers=headers)
    assert response.status_code == 200, response.text
    link = urlparse(response.json()["download_url"])
    assert link.path == "/documents/qr/labels/file"
    labels = client.get(f"{link.path}?{link.query}")
    assert labels.status_code == 200
    assert labels.headers["content-type"] == "application/pdf"
    assert labels.content.startswith(b"%PDF")

    attachment_token = create_download_token({"sub": "emp_a", "document_id": documents["DOC-000001"], "attachment_id": 1})
    assert client.get("/documents/qr/labels/file", params={"download_token": attachment_token}).status_code == 403
    assert client.get("/documents/qr/labels/file", params={"download_token": "not-a-token"}).status_code == 401
