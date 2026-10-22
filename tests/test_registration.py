from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
import Backends.backend.routes.documents as documents_routes
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine
from tests.registration_fields import FILLED

models.Base.metadata.create_all(bind=engine)

PDF = b"%PDF-1.4\n%registration test\n%%EOF\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(documents_routes, "UPLOAD_DIR", str(tmp_path / "stored"))
    monkeypatch.setattr(documents_routes, "TEMP_UPLOAD_DIR", str(tmp_path / "tmp"))
    monkeypatch.setattr(documents_routes, "QR_IMAGE_DIR", str(tmp_path / "qr"))
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        records = models.Office(name="Records Office", office_code="REC")
        mayor = models.Office(name="Office of the Mayor", office_code="OM")
        closed = models.Office(name="Closed Office", office_code="CLO", is_active=False)
        db.add_all([records, mayor, closed])
        db.add_all([
            models.Category(name="Finance"),
            models.Category(name="Retired Category", is_active=False),
            models.DocumentType(name="Ordinance"),
            models.DocumentType(name="Resolution"),
            models.DocumentType(name="Retired Type", is_active=False),
        ])
        db.flush()
        employee_permissions = "['register_documents', 'view_documents']"
        db.add_all([
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True, office_id=records.id),
            models.User(username="loneadmin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True),
            models.User(username="clerk", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions=employee_permissions, status="Active", is_active=True, office_id=mayor.id),
            models.User(username="drifter", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions=employee_permissions, status="Active", is_active=True),
        ])
        db.commit()
    return TestClient(main.app)


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def office_id(name):
    with SessionLocal() as db:
        return db.query(models.Office).filter(models.Office.name == name).one().id


def register(client, headers, file=None, **fields):
    data = {"title": "Ordinance No. 7", "series_year": "2025", **FILLED, **fields}
    files = {"file": file} if file else None
    return client.post("/documents/register", data=data, files=files, headers=headers)


def upload(client, headers, filename, content):
    created = client.post("/documents/uploads/create_tmp_uploads", json={"files": [{"filename": filename}]}, headers=headers)
    item = created.json()["files"][0]
    parts = urlsplit(item["upload_url"])
    assert client.put(f"{parts.path}?{parts.query}", content=content).status_code == 200
    return item["tmp_name"]


def confirm(client, headers, specs, **shared):
    return client.post(
        "/documents/bulk-register/confirm_tmp",
        json={"tmp_names": [spec["tmp_name"] for spec in specs], "documents": specs, **FILLED, **shared},
        headers=headers,
    )


def stored(document_id):
    with SessionLocal() as db:
        doc = db.get(models.Document, document_id)
        offices = sorted(row.office_id for row in db.query(models.DocumentOffice).filter_by(document_id=document_id))
        return doc, offices


def office_count():
    with SessionLocal() as db:
        return db.query(models.Office).count()


# Where a new document starts

def test_an_employee_registers_into_their_own_office(client):
    response = register(client, headers_for(client, "clerk"))
    assert response.status_code == 200, response.text
    doc, offices = stored(response.json()["id"])
    mayor = office_id("Office of the Mayor")
    assert (doc.current_office_id, doc.current_office) == (mayor, "Office of the Mayor")
    assert (doc.originating_office_id, doc.originating_office) == (mayor, "Office of the Mayor")
    assert offices == [mayor]


def test_an_employee_cannot_register_for_another_office(client):
    headers = headers_for(client, "clerk")
    assert register(client, headers, office_id=str(office_id("Records Office"))).status_code == 403
    assert register(client, headers, current_office="Records Office").status_code == 403
    # Naming their own office is fine.
    assert register(client, headers, office_id=str(office_id("Office of the Mayor"))).status_code == 200, "own office"


def test_an_employee_without_an_office_cannot_register(client):
    response = register(client, headers_for(client, "drifter"))
    assert response.status_code == 403
    assert "office" in response.json()["detail"].lower()


def test_a_super_admin_registers_into_their_own_office_or_any_active_one(client):
    headers = headers_for(client, "admin")
    own = register(client, headers).json()
    assert stored(own["id"])[0].current_office == "Records Office"

    chosen = register(client, headers, title="Ordinance No. 8", office_id=str(office_id("Office of the Mayor")))
    assert chosen.status_code == 200, chosen.text
    doc, offices = stored(chosen.json()["id"])
    assert (doc.current_office, doc.originating_office) == ("Office of the Mayor", "Office of the Mayor")
    assert offices == [office_id("Office of the Mayor")]

    by_name = register(client, headers, title="Ordinance No. 9", current_office="Office of the Mayor")
    assert stored(by_name.json()["id"])[0].current_office_id == office_id("Office of the Mayor")


def test_registration_never_creates_or_uses_an_unknown_or_inactive_office(client):
    headers = headers_for(client, "admin")
    before = office_count()
    for fields in ({"current_office": "SB Secretariat"}, {"office_id": "999999"}, {"office_id": str(office_id("Closed Office"))}):
        response = register(client, headers, **fields)
        assert response.status_code == 400, fields
        assert "office" in response.json()["detail"].lower()
    assert office_count() == before
    with SessionLocal() as db:
        assert db.query(models.Document).count() == 0


def test_the_form_offers_each_user_only_what_they_may_choose(client):
    def options(username):
        response = client.get("/documents/registration/options", headers=headers_for(client, username))
        assert response.status_code == 200, response.text
        return response.json()

    clerk = options("clerk")
    assert [office["name"] for office in clerk["offices"]] == ["Office of the Mayor"]
    assert clerk["office_locked"] is True
    assert clerk["default_office_id"] == office_id("Office of the Mayor")
    assert clerk["document_types"] == ["Ordinance", "Resolution"]
    assert (clerk["other_document_types"], clerk["categories"]) == ([], [])

    admin = options("admin")
    assert [office["name"] for office in admin["offices"]] == ["Office of the Mayor", "Records Office"]
    assert admin["office_locked"] is False
    assert admin["default_office_id"] == office_id("Records Office")

    assert options("loneadmin")["default_office_id"] is None
    drifter = options("drifter")
    assert (drifter["offices"], drifter["default_office_id"]) == ([], None)


# Document type and category: typed freely

def test_a_typed_type_and_category_are_saved_tidied(client):
    headers = headers_for(client, "admin")
    body = register(client, headers, category="  Public   Works ", document_type="  executive  order").json()
    assert (body["category"], body["document_type"]) == ("Public Works", "executive order")
    assert body["category_id"] is None and body["document_type_id"] is None


def test_ordinance_and_resolution_keep_their_standard_spelling(client):
    body = register(client, headers_for(client, "admin"), document_type="ORDINANCE").json()
    assert body["document_type"] == "Ordinance"


# Everything but the description and due date is required

@pytest.mark.parametrize("blank", ["document_type", "assigned_to", "action_required", "author"])
def test_every_field_but_the_description_and_due_date_is_required(client, blank):
    response = register(client, headers_for(client, "admin"), **{blank: "  "})
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Fill in the required fields:")
    with SessionLocal() as db:
        assert db.query(models.Document).count() == 0


def test_the_description_due_date_and_category_are_optional(client):
    response = register(client, headers_for(client, "admin"), description="", due_date="", category="")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["description"], body["due_date"], body["category"]) == (None, None, None)


def test_a_document_needs_its_number_unless_it_is_a_measure_not_yet_enacted(client):
    headers = headers_for(client, "admin")
    memo = register(client, headers, title="Office memo", document_type="Memorandum")
    assert (memo.status_code, memo.json()["detail"]) == (400, "Number is required.")
    approved = register(client, headers, title="Market code", document_type="Ordinance", stage="Approved")
    assert (approved.status_code, approved.json()["detail"]) == (400, "Number is required.")

    assert register(client, headers, title="Market code", document_type="Ordinance", stage="Filed").status_code == 200
    assert register(client, headers, title="Office memo", document_type="Memorandum", document_number="3").status_code == 200


def test_multiple_registration_needs_the_same_fields_and_a_number_per_file(client):
    headers = headers_for(client, "admin")
    unnumbered = upload(client, headers, "memo.pdf", PDF)
    assert confirm(client, headers, [{"tmp_name": unnumbered, "series_year": 2025}], author="").status_code == 400

    result = confirm(client, headers, [{"tmp_name": unnumbered, "series_year": 2025}], document_type="Memorandum").json()
    assert result["registered"] == 0 and result["errors"][0]["reason"] == "Number is required."
    numbered = confirm(client, headers, [{"tmp_name": unnumbered, "series_year": 2025, "document_number": "4"}],
                       document_type="Memorandum").json()
    assert numbered["registered"] == 1, numbered


def test_an_overlong_type_or_category_is_refused(client):
    headers = headers_for(client, "admin")
    assert register(client, headers, category="x" * 121).status_code == 400
    assert register(client, headers, document_type="x" * 121).status_code == 400
    with SessionLocal() as db:
        assert db.query(models.Document).count() == 0


def test_the_form_suggests_types_and_categories_already_used(client):
    headers = headers_for(client, "admin")
    for title, category, document_type in [("A", "Finance", "Memorandum"), ("B", "Finance", "Ordinance"), ("C", "Health", "Memorandum")]:
        response = register(client, headers, title=title, category=category, document_type=document_type, document_number=title)
        assert response.status_code == 200, response.text
    options = client.get("/documents/registration/options", headers=headers).json()
    assert options["document_types"] == ["Ordinance", "Resolution"]
    assert options["other_document_types"] == ["Memorandum"]
    assert options["categories"] == ["Finance", "Health"]


# Audit

def audit_entries():
    with SessionLocal() as db:
        return [(row.actor, row.target_id) for row in db.query(models.AuditLog).filter_by(action="DOCUMENT_REGISTERED").order_by(models.AuditLog.id)]


def test_every_registration_path_writes_a_registered_entry_per_document(client):
    headers = headers_for(client, "clerk")
    without_file = register(client, headers, title="No file").json()
    with_file = register(client, headers, title="With file", file=("a.pdf", PDF, "application/pdf")).json()
    first = upload(client, headers, "first.pdf", PDF + b"%1\n")
    second = upload(client, headers, "second.pdf", PDF + b"%2\n")
    bulk = confirm(client, headers, [{"tmp_name": first, "series_year": 2025}, {"tmp_name": second, "series_year": 2025}]).json()
    assert bulk["registered"] == 2, bulk

    expected = [without_file["tracking_number"], with_file["tracking_number"]] + [item["tracking_number"] for item in bulk["documents"]]
    assert audit_entries() == [("clerk", number) for number in expected]


# Multiple registration

def test_each_uploaded_file_keeps_its_own_title_and_number(client):
    headers = headers_for(client, "clerk")
    first = upload(client, headers, "scan-001.pdf", PDF + b"%1\n")
    second = upload(client, headers, "scan-002.pdf", PDF + b"%2\n")
    result = confirm(client, headers, [
        {"tmp_name": first, "series_year": 2024, "title": "Ordinance on markets", "document_number": "12"},
        {"tmp_name": second, "series_year": 2025, "title": "Ordinance on parking", "document_number": "13"},
    ], document_type="Ordinance", category="Finance").json()
    assert result["registered"] == 2, result

    docs = [stored(item["id"])[0] for item in result["documents"]]
    assert [(d.title, d.document_number, d.series_year) for d in docs] == [
        ("Ordinance on markets", "12", 2024),
        ("Ordinance on parking", "13", 2025),
    ]
    assert {d.current_office for d in docs} == {"Office of the Mayor"}
    assert {d.originating_office for d in docs} == {"Office of the Mayor"}
    assert {d.document_type for d in docs} == {"Ordinance"}


def test_multiple_registration_applies_the_same_office_and_naming_rules(client):
    clerk = headers_for(client, "clerk")
    tmp = upload(client, clerk, "a.pdf", PDF)
    spec = [{"tmp_name": tmp, "series_year": 2025}]
    assert confirm(client, clerk, spec, office_id=office_id("Records Office")).status_code == 403
    assert confirm(client, clerk, spec, category="x" * 121).status_code == 400
    assert confirm(client, clerk, spec, current_office="SB Secretariat").status_code == 403

    admin = headers_for(client, "admin")
    assert confirm(client, admin, spec, current_office="SB Secretariat").status_code == 400
    chosen = confirm(client, admin, spec, office_id=office_id("Office of the Mayor")).json()
    assert stored(chosen["documents"][0]["id"])[0].current_office == "Office of the Mayor"


# Duplicate legislative numbers: a warning the user may override

def test_duplicate_numbers_are_reported_before_registering(client):
    headers = headers_for(client, "clerk")
    existing = register(client, headers, document_type="Ordinance", document_number="7", series_year="2025").json()

    def check(**params):
        response = client.get("/documents/registration/duplicates", params=params, headers=headers)
        assert response.status_code == 200, response.text
        return [item["tracking_number"] for item in response.json()["documents"]]

    assert check(document_type="Ordinance", document_number="007", series_year=2025) == [existing["tracking_number"]]
    assert check(document_type="ordinance", document_number="7", series_year=2025) == [existing["tracking_number"]]
    assert check(document_type="Ordinance", document_number="7", series_year=2024) == []
    assert check(document_type="Resolution", document_number="7", series_year=2025) == []
    assert check(document_type="Ordinance", document_number="", series_year=2025) == []


def test_a_duplicate_number_is_refused_unless_the_user_overrides(client):
    headers = headers_for(client, "clerk")
    fields = {"document_type": "Ordinance", "document_number": "7", "series_year": "2025"}
    first = register(client, headers, **fields).json()

    refused = register(client, headers, **fields)
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["duplicate_number"] is True
    assert detail["documents"] == [first["tracking_number"]]

    allowed = register(client, headers, allow_duplicate_number="true", **fields)
    assert allowed.status_code == 200, allowed.text


def test_multiple_registration_flags_duplicate_numbers_per_file(client):
    headers = headers_for(client, "clerk")
    register(client, headers, document_type="Ordinance", document_number="7", series_year="2025")
    dup = upload(client, headers, "dup.pdf", PDF + b"%dup\n")
    fresh = upload(client, headers, "fresh.pdf", PDF + b"%fresh\n")
    specs = [
        {"tmp_name": dup, "series_year": 2025, "document_number": "7"},
        {"tmp_name": fresh, "series_year": 2025, "document_number": "8"},
    ]
    result = confirm(client, headers, specs, document_type="Ordinance").json()
    assert result["registered"] == 1
    error = result["errors"][0]
    assert (error["filename"], error["duplicate_number"]) == ("dup.pdf", True)
    assert error["tmp_name"] == dup

    retried = confirm(client, headers, specs[:1], document_type="Ordinance", allow_duplicate_number=True).json()
    assert retried["registered"] == 1, retried


def test_identical_files_stay_blocked_even_when_overriding_numbers(client):
    headers = headers_for(client, "clerk")
    register(client, headers, title="Original", file=("a.pdf", PDF, "application/pdf"))
    again = register(client, headers, title="Copy", allow_duplicate_number="true", file=("b.pdf", PDF, "application/pdf"))
    assert again.status_code == 409
    assert "Duplicate PDF content" in again.json()["detail"]
