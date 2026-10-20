import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        records = models.Office(name="Records Office")
        mayor = models.Office(name="Office of the Mayor")
        db.add_all([records, mayor])
        db.flush()
        db.add_all([
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True),
            models.User(username="clerk", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions="['view_office_documents', 'view_office_document_details']", status="Active",
                        is_active=True, office_id=records.id),
            models.User(username="nobody", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions="['view_office_documents']", status="Active", is_active=True, office_id=records.id),
        ])
        docs = [
            ("DOC-000001", "Budget Ordinance 2026", "12", records, False),
            ("DOC-000002", "Health Resolution", "7", mayor, False),
            ("DOC-000012", "Market Fees Ordinance", "12", records, False),
            ("DOC-000123", "Archived Budget Report", None, records, True),
        ]
        for tracking, title, number, office, archived in docs:
            doc = models.Document(tracking_number=tracking, title=title, document_number=number, series_year=2026,
                                  document_type="Ordinance", current_office=office.name, current_office_id=office.id,
                                  originating_office_id=office.id, archived=archived)
            db.add(doc)
            db.flush()
            db.add(models.DocumentOffice(document_id=doc.id, office_id=office.id))
        db.commit()
    return TestClient(main.app)


def search(client, username, q, **params):
    login = client.post("/auth/login", data={"username": username, "password": "pw123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return client.get("/documents/quick-search", params={"q": q, **params}, headers=headers)


def tracking_numbers(response):
    assert response.status_code == 200, response.text
    return [item["tracking_number"] for item in response.json()["items"]]


@pytest.mark.parametrize("q", ["DOC-000012", "doc-12", "000012"])
def test_a_tracking_number_finds_that_document_first(client, q):
    assert tracking_numbers(search(client, "admin", q))[0] == "DOC-000012"


def test_bare_twelve_puts_the_exact_tracking_number_before_other_matches(client):
    results = tracking_numbers(search(client, "admin", "12"))

    assert results[0] == "DOC-000012"
    assert results == ["DOC-000012", "DOC-000123", "DOC-000001"]  # then "12" in a tracking or document number, newest first


def test_title_words_match_case_insensitively_and_include_archived(client):
    response = search(client, "admin", "budget")

    assert tracking_numbers(response) == ["DOC-000123", "DOC-000001"]  # newest first
    archived = {item["tracking_number"]: item["archived"] for item in response.json()["items"]}
    assert archived == {"DOC-000123": True, "DOC-000001": False}
    item = next(i for i in response.json()["items"] if i["tracking_number"] == "DOC-000001")
    assert set(item) >= {"id", "tracking_number", "title", "document_type", "document_number", "series_year", "current_office", "archived"}


def test_office_staff_only_find_their_offices_documents(client):
    assert tracking_numbers(search(client, "clerk", "ordinance")) == ["DOC-000012", "DOC-000001"]
    assert tracking_numbers(search(client, "clerk", "DOC-000002")) == []


def test_search_needs_permission_to_open_details(client):
    assert search(client, "nobody", "budget").status_code == 403


def test_short_queries_return_nothing_and_limit_caps_results(client):
    assert tracking_numbers(search(client, "admin", " a ")) == []
    assert len(tracking_numbers(search(client, "admin", "o", limit=2))) == 0
    assert len(tracking_numbers(search(client, "admin", "ordinance", limit=1))) == 1
