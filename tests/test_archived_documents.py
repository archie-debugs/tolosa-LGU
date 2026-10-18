from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

PERMISSIONS = ["view_documents", "archive_documents", "restore_documents", "pass_office_documents", "view_office_documents"]


def setup_documents():
    """Office A holds three documents; 1 and 2 are archived (2 by beth, 40 days ago), 3 is active."""
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        offices = {code: models.Office(name=f"Office {code}", office_code=f"OFF{code}") for code in "AB"}
        db.add_all(offices.values())
        db.commit()
        db.add(models.User(username="emp_a", hashed_password=get_password_hash("pw123"), role="Employee",
                           permissions=str(PERMISSIONS), office_id=offices["A"].id, status="Active", is_active=True))
        now = datetime.now(timezone.utc)
        archive_stamps = {1: (now - timedelta(days=2), "joel"), 2: (now - timedelta(days=40), "beth")}
        documents = [
            models.Document(tracking_number=f"DOC-00000{index}", title=f"Document {index}", status="Approved", priority="Medium",
                            qr_token=f"archived-list-{index}", current_office="Office A", current_office_id=offices["A"].id,
                            archived=index in archive_stamps,
                            archived_at=archive_stamps.get(index, (None, None))[0], archived_by=archive_stamps.get(index, (None, None))[1])
            for index in range(1, 4)
        ]
        db.add_all(documents)
        db.commit()
        return {code: office.id for code, office in offices.items()}, {doc.tracking_number: doc.id for doc in documents}


def headers_for(client):
    response = client.post("/auth/login", data={"username": "emp_a", "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def numbers(payload):
    return [item["tracking_number"] for item in payload["items"]]


def test_archived_list_sorts_and_filters_by_when_and_who_archived():
    setup_documents()
    client = TestClient(main.app)
    headers = headers_for(client)

    payload = client.get("/documents", params={"archived": "true", "sort_by": "archived_at", "sort_order": "desc"}, headers=headers).json()
    assert numbers(payload) == ["DOC-000001", "DOC-000002"]
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["archived_last_30_days"] == 1
    assert payload["available_archivers"] == ["beth", "joel"]

    oldest_first = client.get("/documents", params={"archived": "true", "sort_by": "archived_at", "sort_order": "asc"}, headers=headers).json()
    assert numbers(oldest_first) == ["DOC-000002", "DOC-000001"]
    assert numbers(client.get("/documents", params={"archived": "true", "archived_by": "beth"}, headers=headers).json()) == ["DOC-000002"]
    assert numbers(client.get("/documents", params={"archived": "true", "archived_within_days": 30}, headers=headers).json()) == ["DOC-000001"]

    active = client.get("/documents", headers=headers).json()
    assert "archived_last_30_days" not in active["summary"]
    assert active["available_archivers"] == []


def test_archiving_twice_keeps_the_first_archive_stamp():
    _, documents = setup_documents()
    client = TestClient(main.app)
    headers = headers_for(client)
    with SessionLocal() as db:
        before = db.get(models.Document, documents["DOC-000001"])
        stamp = (before.archived_at, before.archived_by)

    response = client.delete(f"/documents/{documents['DOC-000001']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Document is already archived"
    with SessionLocal() as db:
        after = db.get(models.Document, documents["DOC-000001"])
        assert (after.archived_at, after.archived_by) == stamp


def test_a_document_in_transit_cannot_be_archived_until_received():
    offices, documents = setup_documents()
    client = TestClient(main.app)
    headers = headers_for(client)
    document_id = documents["DOC-000003"]
    assert client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": offices["B"]}, headers=headers).status_code == 200

    response = client.delete(f"/documents/{document_id}", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "DOC-000003 is in transit to Office B. Archive it after it is received."
    with SessionLocal() as db:
        assert db.get(models.Document, document_id).archived is False
