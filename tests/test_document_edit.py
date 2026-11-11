import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
import Backends.backend.routes.documents as documents_routes
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine
from tests.registration_fields import FILLED

models.Base.metadata.create_all(bind=engine)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(documents_routes, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(documents_routes, "QR_IMAGE_DIR", str(tmp_path / "qr"))
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        records = models.Office(name="Records Office", is_main=True)
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
        **FILLED, "title": "Ordinance No. 7", "series_year": "2025", "category": "Old Category", "document_type": "Ordinance",
    }, headers=headers_for(client))
    assert response.status_code == 200, response.text
    return response.json()


def edit(client, document, **payload):
    return client.put(f"/documents/{document['id']}", json=payload, headers=headers_for(client))


def counts():
    with SessionLocal() as db:
        return db.query(models.Office).count(), db.query(models.Category).count(), db.query(models.DocumentType).count()


def test_edit_saves_a_typed_category_tidied(client, document):
    before = counts()

    response = edit(client, document, category="  Public  Works")

    assert response.status_code == 200, response.text
    assert response.json()["category"] == "Public Works"
    assert counts() == before


@pytest.mark.parametrize("document_type", ["memorandum", "", None])
def test_edit_refuses_a_type_other_than_the_three(client, document, document_type):
    response = edit(client, document, document_type=document_type)

    assert response.status_code == 400
    assert response.json()["detail"] == "Choose the document type: Ordinance, Resolution or Letter Request."


def test_edit_keeps_the_standard_spelling_and_can_clear_a_category(client, document):
    response = edit(client, document, category="", document_type="RESOLUTION")

    assert response.status_code == 200, response.text
    assert (response.json()["category"], response.json()["document_type"]) == (None, "Resolution")


def test_a_new_type_gives_the_next_number_in_its_series_and_the_old_one_still_finds_it(client, document):
    assert document["tracking_number"] == "ORD-000001"

    response = edit(client, document, document_type="Resolution")

    assert response.status_code == 200, response.text
    assert response.json()["tracking_number"] == "RES-000001"
    found = client.get("/documents", params={"search": "ORD-000001"}, headers=headers_for(client)).json()["items"]
    assert [item["id"] for item in found] == [document["id"]]
    with SessionLocal() as db:
        assert documents_routes._find_document_by_qr_or_tracking(db, "ORD-000001").id == document["id"]
        logged = db.query(models.AuditLog).filter(models.AuditLog.action == "TRACKING_NUMBER_CHANGED").one()
        assert logged.details == "ORD-000001 is now RES-000001 after its type changed to Resolution"


def test_the_same_type_keeps_its_number(client, document):
    response = edit(client, document, document_type="ordinance", title="Renamed")

    assert response.status_code == 200, response.text
    assert response.json()["tracking_number"] == "ORD-000001"


def test_edit_refuses_an_overlong_category(client, document):
    response = edit(client, document, category="x" * 121)

    assert response.status_code == 400
    assert "120" in response.json()["detail"]


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


def test_edit_options_suggest_what_documents_already_use(client, document):
    response = client.get("/documents/edit-options", headers=headers_for(client))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "document_types": ["Ordinance", "Resolution", "Letter Request"],
        "categories": ["Old Category"],
    }
    assert client.get("/documents/edit-options", headers=headers_for(client, "clerk")).status_code == 403


def test_edit_sets_status_and_action_required(client, document):
    assert (document["status"], document["action_required"]) == ("Approved", "For Agenda")

    response = edit(client, document, status="For information", action_required="Posting")

    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["action_required"]) == ("For information", "Posting")
    assert edit(client, document, status="").status_code == 400


def test_registration_records_the_action_required(client):
    response = client.post("/documents/register", data={
        **FILLED, "title": "Request letter", "series_year": "2026", "document_type": "Ordinance", "action_required": "Posting",
    }, headers=headers_for(client))

    assert response.status_code == 200, response.text
    assert response.json()["action_required"] == "Posting"


def test_each_remark_is_added_and_the_earlier_ones_are_kept(client, document):
    first = edit(client, document, new_remark="Received by SB Secretary")
    second = edit(client, document, new_remark="  Returned for signature ")

    assert first.status_code == 200 and second.status_code == 200, second.text
    body = second.json()
    assert body["remarks"] == "Returned for signature"
    assert [r["text"] for r in body["remark_history"]] == ["Returned for signature", "Received by SB Secretary"]
    assert {r["author"] for r in body["remark_history"]} == {"admin"}
    assert all(r["created_at"] for r in body["remark_history"])


def test_an_empty_or_unchanged_remark_adds_nothing_and_never_clears(client, document):
    edit(client, document, new_remark="Received by SB Secretary")

    for payload in ({"new_remark": ""}, {"new_remark": None}, {"remarks": None}, {"remarks": "Received by SB Secretary"}, {"title": "Renamed"}):
        response = edit(client, document, **payload)
        assert response.status_code == 200, response.text
        assert [r["text"] for r in response.json()["remark_history"]] == ["Received by SB Secretary"]
        assert response.json()["remarks"] == "Received by SB Secretary"


def test_a_changed_remarks_field_is_added_as_a_new_remark(client, document):
    edit(client, document, remarks="First")

    response = edit(client, document, remarks="Second")

    assert [r["text"] for r in response.json()["remark_history"]] == ["Second", "First"]


def test_a_remark_from_before_the_history_is_kept_when_a_new_one_is_added(client, document):
    with SessionLocal() as db:
        db.query(models.Document).filter(models.Document.id == document["id"]).update({"remarks": "Old note"})
        db.commit()
    assert [r["text"] for r in client.get(f"/documents/{document['id']}", headers=headers_for(client)).json()["remark_history"]] == ["Old note"]

    response = edit(client, document, new_remark="New note")

    assert [r["text"] for r in response.json()["remark_history"]] == ["New note", "Old note"]


def test_the_list_shows_the_newest_remark(client, document):
    edit(client, document, new_remark="First")
    edit(client, document, new_remark="Second")

    items = client.get("/documents", headers=headers_for(client)).json()["items"]

    assert [i["remarks"] for i in items if i["id"] == document["id"]] == ["Second"]


def test_saving_the_edit_form_keeps_the_number_category_priority_and_due_date(client, document):
    # The edit form no longer shows these four, so it leaves them out of what it saves.
    with SessionLocal() as db:
        doc = db.get(models.Document, document["id"])
        doc.document_number, doc.priority = "07-2025", "High"
        doc.due_date = documents_routes._parse_due_date("2026-12-01")
        db.commit()

    response = edit(client, document, title="Ordinance No. 7, amended", series_year="2025", description=None,
                    document_type="Ordinance", assigned_to=None, status="Approved", action_required=None,
                    author="Hon. Cruz", new_remark=None)

    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["title"] == "Ordinance No. 7, amended"
    assert (saved["document_number"], saved["category"], saved["priority"], saved["due_date"]) == (
        "07-2025", "Old Category", "High", "2026-12-01")
