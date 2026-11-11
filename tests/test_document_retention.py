from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine
from Backends.backend.retention import add_months

models.Base.metadata.create_all(bind=engine)

NOW = datetime.now(timezone.utc)
TYPES = {"ORD": "Ordinance", "RES": "Resolution", "LTR": "Letter Request"}


@pytest.fixture
def client():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        records = models.Office(name="Records Office", is_main=True)
        db.add(records)
        db.flush()
        db.add_all([
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True),
            # An office employee who may delete archived documents sees retention notices too.
            models.User(username="clerk", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions="['view_documents', 'delete_documents', 'view_office_documents']",
                        status="Active", is_active=True, office_id=records.id),
            models.User(username="staff", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions="['view_documents', 'archive_documents', 'restore_documents', 'view_office_documents']",
                        status="Active", is_active=True, office_id=records.id),
        ])
        db.commit()
    return TestClient(main.app)


def archived(tracking, archived_at, extended_until=None):
    with SessionLocal() as db:
        doc = models.Document(tracking_number=tracking, title=f"Title of {tracking}", document_type=TYPES[tracking[:3]],
                              current_office="Records Office", archived=True, archived_at=archived_at, archived_by="admin",
                              retention_extended_until=extended_until)
        db.add(doc)
        db.commit()
        return doc.id


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def notifications(client, username):
    response = client.get("/notifications", headers=headers_for(client, username))
    assert response.status_code == 200, response.text
    return response.json()


def retention_kinds(body):
    return [(item["kind"], item["tracking_number"]) for item in body["items"] if item["kind"].startswith("retention")]


def test_add_months_keeps_the_day_or_takes_the_last_of_a_shorter_month():
    assert add_months(datetime(2026, 1, 31, tzinfo=timezone.utc), 1) == datetime(2026, 2, 28, tzinfo=timezone.utc)
    assert add_months(datetime(2026, 11, 15, tzinfo=timezone.utc), 10) == datetime(2027, 9, 15, tzinfo=timezone.utc)
    assert add_months(datetime(2026, 3, 1, tzinfo=timezone.utc), 120) == datetime(2036, 3, 1, tzinfo=timezone.utc)


def test_each_type_is_kept_its_own_time_after_it_is_archived(client):
    archived("ORD-000001", NOW - timedelta(days=365 * 50))
    archived("RES-000001", NOW - timedelta(days=365 * 11))
    archived("RES-000002", NOW - timedelta(days=365))
    archived("LTR-000001", NOW - timedelta(days=330))
    archived("LTR-000002", NOW - timedelta(days=30))

    payload = client.get("/documents", params={"archived": "true"}, headers=headers_for(client, "admin")).json()
    until = {item["tracking_number"]: item["retain_until"] for item in payload["items"]}
    assert until["ORD-000001"] is None
    assert datetime.fromisoformat(until["RES-000002"]).date() == add_months(NOW - timedelta(days=365), 120).date()
    assert datetime.fromisoformat(until["LTR-000002"]).date() == add_months(NOW - timedelta(days=30), 10).date()

    assert sorted(retention_kinds(notifications(client, "admin"))) == [("retention_due", "LTR-000001"), ("retention_due", "RES-000001")]


def test_due_documents_are_priority_stay_unread_and_come_first(client):
    archived("LTR-000001", add_months(NOW, -10) - timedelta(days=2))
    soon = archived("LTR-000002", add_months(NOW, -10) + timedelta(days=10))
    archived("LTR-000003", add_months(NOW, -10) + timedelta(days=60))
    headers = headers_for(client, "admin")

    body = notifications(client, "admin")
    assert retention_kinds(body) == [("retention_due", "LTR-000001"), ("retention_soon", "LTR-000002")]
    assert body["items"][0]["priority"] is True
    assert "priority" not in next(item for item in body["items"] if item["document_id"] == soon)

    client.post("/notifications/seen", headers=headers)
    body = notifications(client, "admin")
    assert body["unread"] == 1
    assert [item["tracking_number"] for item in body["items"] if item["unread"]] == ["LTR-000001"]


def test_only_users_who_may_delete_hear_about_retention(client):
    archived("LTR-000001", NOW - timedelta(days=400))
    assert retention_kinds(notifications(client, "clerk")) == [("retention_due", "LTR-000001")]
    assert retention_kinds(notifications(client, "staff")) == []


def test_extending_keeps_the_document_and_clears_the_notice(client):
    doc_id = archived("LTR-000001", add_months(NOW, -10) - timedelta(days=5))
    headers = headers_for(client, "admin")

    response = client.post(f"/documents/{doc_id}/retention/extend", json={"months": 6}, headers=headers)
    assert response.status_code == 200, response.text
    # Counted from today, since the original date has passed.
    assert datetime.fromisoformat(response.json()["retain_until"]).date() == add_months(NOW, 6).date()
    assert retention_kinds(notifications(client, "admin")) == []

    again = client.post(f"/documents/{doc_id}/retention/extend", json={"months": 12}, headers=headers)
    assert datetime.fromisoformat(again.json()["retain_until"]).date() == add_months(add_months(NOW, 6), 12).date()
    with SessionLocal() as db:
        assert db.query(models.AuditLog).filter(models.AuditLog.action == "EXTEND_DOCUMENT_RETENTION").count() == 2


def test_extend_needs_permission_a_period_and_a_sensible_length(client):
    letter = archived("LTR-000001", NOW - timedelta(days=400))
    ordinance = archived("ORD-000001", NOW - timedelta(days=400))
    admin = headers_for(client, "admin")

    assert client.post(f"/documents/{letter}/retention/extend", json={"months": 6}, headers=headers_for(client, "staff")).status_code == 403
    assert client.post(f"/documents/{letter}/retention/extend", json={"months": 0}, headers=admin).status_code == 422
    assert client.post(f"/documents/{letter}/retention/extend", json={"months": 121}, headers=admin).status_code == 422
    permanent = client.post(f"/documents/{ordinance}/retention/extend", json={"months": 6}, headers=admin)
    assert permanent.status_code == 400


def test_restoring_forgets_an_extension(client):
    doc_id = archived("LTR-000001", NOW - timedelta(days=400), extended_until=NOW + timedelta(days=200))
    assert client.post(f"/documents/{doc_id}/restore", headers=headers_for(client, "admin")).status_code == 200
    with SessionLocal() as db:
        assert db.get(models.Document, doc_id).retention_extended_until is None


def test_retention_periods_are_editable_per_type(client):
    archived("ORD-000001", NOW - timedelta(days=400))
    headers = headers_for(client, "admin")
    assert client.get("/system-settings", headers=headers).json()["settings"]["retention_months"] == {
        "Ordinance": None, "Resolution": 120, "Letter Request": 10}

    response = client.put("/system-settings", json={"settings": {"retention_months": {"Ordinance": 12}}}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["settings"]["retention_months"] == {"Ordinance": 12, "Resolution": 120, "Letter Request": 10}
    assert retention_kinds(notifications(client, "admin")) == [("retention_due", "ORD-000001")]

    for bad in ({"Memo": 5}, {"Resolution": 0}, {"Resolution": "ten"}, {"Resolution": 1201}):
        assert client.put("/system-settings", json={"settings": {"retention_months": bad}}, headers=headers).status_code == 400


def test_the_details_of_an_archived_document_say_when_it_is_due_for_deletion(client):
    doc_id = archived("LTR-000001", NOW - timedelta(days=30))
    listed = next(item for item in client.get("/documents", params={"archived": "true"}, headers=headers_for(client, "admin")).json()["items"] if item["id"] == doc_id)
    details = client.get(f"/documents/{doc_id}/overview", headers=headers_for(client, "admin")).json()["document"]
    assert datetime.fromisoformat(details["retain_until"]) == datetime.fromisoformat(listed["retain_until"].replace("Z", "+00:00"))
    assert details["retain_until"]
