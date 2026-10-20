import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
import Backends.backend.routes.documents as documents_routes
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(documents_routes, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(documents_routes, "QR_IMAGE_DIR", str(tmp_path / "qr"))
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        records = models.Office(name="Records Office")
        db.add_all([
            records,
            models.Office(name="Office of the Mayor"),
            models.Category(name="Finance"),
            models.Category(name="Health"),
            models.Category(name="Old Category"),
            models.DocumentType(name="Ordinance"),
            models.DocumentType(name="Resolution"),
            models.DocumentType(name="Retired Type", is_active=False),
        ])
        db.flush()
        db.add_all([
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True, office_id=records.id),
            models.User(username="clerk", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions="['view_documents']", status="Active", is_active=True, office_id=records.id),
        ])
        db.commit()
    return TestClient(main.app)


def headers_for(client, username="admin"):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def document(client):
    response = client.post("/documents/register", data={
        "title": "Ordinance No. 7", "series_year": "2025", "category": "Old Category", "document_type": "Ordinance",
    }, headers=headers_for(client))
    assert response.status_code == 200, response.text
    return response.json()


def edit(client, document, **payload):
    return client.put(f"/documents/{document['id']}", json=payload, headers=headers_for(client))


def counts():
    with SessionLocal() as db:
        return db.query(models.Office).count(), db.query(models.Category).count(), db.query(models.DocumentType).count()


def test_edit_links_existing_active_reference_data(client, document):
    response = edit(client, document, category="health", document_type="Resolution")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["category"], body["document_type"]) == ("Health", "Resolution")
    with SessionLocal() as db:
        stored = db.get(models.Document, document["id"])
        assert stored.category_rel.name == "Health"
        assert stored.document_type_rel.name == "Resolution"


@pytest.mark.parametrize("payload, message", [
    ({"category": "Made Up"}, "Category 'Made Up' is not an active entry in Reference Data."),
    ({"document_type": "Retired Type"}, "Document type 'Retired Type' is not an active entry in Reference Data."),
])
def test_edit_never_creates_or_revives_reference_data(client, document, payload, message):
    before = counts()

    response = edit(client, document, **payload)

    assert response.status_code == 400
    assert response.json()["detail"] == message
    assert counts() == before


def test_edit_keeps_a_value_that_was_retired_after_registration(client, document):
    with SessionLocal() as db:
        db.query(models.Category).filter_by(name="Old Category").update({"is_active": False})
        db.commit()

    response = edit(client, document, title="Renamed", category="Old Category", document_type="Ordinance")

    assert response.status_code == 200, response.text
    assert response.json()["category"] == "Old Category"


def test_edit_cannot_move_a_document_between_offices(client, document):
    before = counts()

    for payload in ({"current_office": "Office of the Mayor"}, {"current_office": "Brand New Office"},
                    {"current_office": None}, {"originating_office": "Office of the Mayor"}):
        response = edit(client, document, **payload)
        assert response.status_code == 400, payload
        assert "Pass" in response.json()["detail"] or "registration" in response.json()["detail"]

    assert counts() == before
    with SessionLocal() as db:
        assert db.get(models.Document, document["id"]).current_office == "Records Office"


def test_edit_accepts_the_unchanged_office_an_older_form_sends_back(client, document):
    response = edit(client, document, title="Renamed", current_office="Records Office")

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Renamed"


@pytest.mark.parametrize("field, value", [
    ("created_by", "someone-else"),
    ("qr_code_value", "forged"),
    ("attachment_name", "other.pdf"),
    ("date_registered", "1999-01-01"),
])
def test_edit_refuses_system_managed_fields(client, document, field, value):
    response = edit(client, document, **{field: value})

    assert response.status_code == 400
    assert response.json()["detail"] == "This field is managed by the system and cannot be edited."


def test_edit_options_list_active_reference_data_for_editors(client):
    response = client.get("/documents/edit-options", headers=headers_for(client))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "categories": ["Finance", "Health", "Old Category"],
        "document_types": ["Ordinance", "Resolution"],
    }
    assert client.get("/documents/edit-options", headers=headers_for(client, "clerk")).status_code == 403
