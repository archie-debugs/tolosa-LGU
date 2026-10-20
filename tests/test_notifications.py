from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash, lgu_today
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

NOW = datetime.now(timezone.utc)


@pytest.fixture
def client():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        records = models.Office(name="Records Office")
        mayor = models.Office(name="Office of the Mayor")
        db.add_all([records, mayor])
        db.flush()
        perms = "['view_office_documents', 'view_office_document_details']"
        db.add_all([
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True),
            models.User(username="rec", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions=perms, status="Active", is_active=True, office_id=records.id),
            models.User(username="mayor", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions=perms, status="Active", is_active=True, office_id=mayor.id),
        ])
        db.commit()
    return TestClient(main.app)


def ids():
    with SessionLocal() as db:
        offices = {o.name: o.id for o in db.query(models.Office)}
        users = {u.username: u.id for u in db.query(models.User)}
    return offices, users


def add_document(tracking, office, *, created_by="admin", created_at=None, due=None, archived=False):
    offices, _ = ids()
    with SessionLocal() as db:
        doc = models.Document(tracking_number=tracking, title=f"Title of {tracking}", series_year=2026,
                              current_office=office, current_office_id=offices[office],
                              originating_office=office, originating_office_id=offices[office],
                              created_by=created_by, created_at=(created_at or NOW).replace(tzinfo=None),
                              due_date=due, archived=archived)
        db.add(doc)
        db.flush()
        db.add(models.DocumentOffice(document_id=doc.id, office_id=offices[office]))
        db.commit()
        return doc.id


def add_handoff(document_id, sender, receiver, hours_ago, status="Pending Receipt"):
    offices, users = ids()
    with SessionLocal() as db:
        db.add(models.DocumentHandoff(document_id=document_id, sending_office_id=offices[sender],
                                      receiving_office_id=offices[receiver], sending_employee_id=users["admin"],
                                      sent_at=NOW - timedelta(hours=hours_ago), status=status))
        db.commit()


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def notifications(client, username):
    response = client.get("/notifications", headers=headers_for(client, username))
    assert response.status_code == 200, response.text
    return response.json()


def kinds(body):
    return [(item["kind"], item["tracking_number"]) for item in body["items"]]


def test_documents_sent_to_your_office_wait_for_receipt_and_turn_overdue(client):
    fresh = add_document("DOC-000001", "Records Office", created_at=NOW - timedelta(days=30))
    stale = add_document("DOC-000002", "Records Office", created_at=NOW - timedelta(days=30))
    done = add_document("DOC-000003", "Records Office", created_at=NOW - timedelta(days=30))
    add_handoff(fresh, "Records Office", "Office of the Mayor", hours_ago=2)
    add_handoff(stale, "Records Office", "Office of the Mayor", hours_ago=30)
    add_handoff(done, "Records Office", "Office of the Mayor", hours_ago=1, status="Received")

    body = notifications(client, "mayor")

    assert kinds(body) == [("incoming", "DOC-000001"), ("incoming_overdue", "DOC-000002")]
    first = body["items"][0]
    assert first["message"] == "Sent to your office by Records Office. Waiting for receipt."
    assert first["document_id"] == fresh
    assert "over 24 hours" in body["items"][1]["message"]


def test_the_sending_office_hears_when_its_handoff_is_overdue(client):
    doc = add_document("DOC-000004", "Records Office", created_at=NOW - timedelta(days=30))
    other = add_document("DOC-000005", "Records Office", created_at=NOW - timedelta(days=30))
    add_handoff(doc, "Records Office", "Office of the Mayor", hours_ago=26)
    add_handoff(other, "Records Office", "Office of the Mayor", hours_ago=3)

    body = notifications(client, "rec")

    assert kinds(body) == [("outgoing_overdue", "DOC-000004")]
    assert body["items"][0]["message"] == "Not yet received by Office of the Mayor after 26 hours."


def test_recent_registrations_into_your_office_by_someone_else(client):
    add_document("DOC-000006", "Records Office", created_by="admin", created_at=NOW - timedelta(hours=1))
    add_document("DOC-000007", "Records Office", created_by="rec", created_at=NOW - timedelta(hours=1))
    add_document("DOC-000008", "Records Office", created_by="admin", created_at=NOW - timedelta(days=9))

    body = notifications(client, "rec")

    assert kinds(body) == [("registered", "DOC-000006")]
    assert body["items"][0]["message"] == "Registered into your office by admin."


def test_due_and_overdue_documents_in_your_office(client):
    today = lgu_today()
    add_document("DOC-000010", "Records Office", created_at=NOW - timedelta(days=30), due=today + timedelta(days=2))
    add_document("DOC-000011", "Records Office", created_at=NOW - timedelta(days=30), due=today - timedelta(days=1))
    add_document("DOC-000012", "Records Office", created_at=NOW - timedelta(days=30), due=today + timedelta(days=10))
    add_document("DOC-000013", "Records Office", created_at=NOW - timedelta(days=30), due=today, archived=True)
    add_document("DOC-000014", "Office of the Mayor", created_at=NOW - timedelta(days=30), due=today)

    body = notifications(client, "rec")

    assert sorted(kinds(body)) == [("due", "DOC-000010"), ("overdue", "DOC-000011")]
    messages = {item["tracking_number"]: item["message"] for item in body["items"]}
    assert messages == {"DOC-000010": "Due in 2 days.", "DOC-000011": "Overdue by 1 day."}


def test_unread_count_clears_when_seen_and_counts_new_items_again(client):
    doc = add_document("DOC-000020", "Records Office", created_at=NOW - timedelta(days=30))
    add_handoff(doc, "Records Office", "Office of the Mayor", hours_ago=1)
    headers = headers_for(client, "mayor")

    assert client.get("/notifications", headers=headers).json()["unread"] == 1
    assert client.post("/notifications/seen", headers=headers).status_code == 200
    body = client.get("/notifications", headers=headers).json()
    assert body["unread"] == 0
    assert [item["unread"] for item in body["items"]] == [False]

    later = add_document("DOC-000021", "Records Office", created_at=NOW - timedelta(days=30))
    with SessionLocal() as db:
        offices, users = ids()
        db.add(models.DocumentHandoff(document_id=later, sending_office_id=offices["Records Office"],
                                      receiving_office_id=offices["Office of the Mayor"], sending_employee_id=users["admin"],
                                      sent_at=datetime.now(timezone.utc) + timedelta(seconds=5), status="Pending Receipt"))
        db.commit()
    assert client.get("/notifications", headers=headers).json()["unread"] == 1


def test_a_super_admin_without_an_office_sees_system_wide_problems(client):
    today = lgu_today()
    late = add_document("DOC-000030", "Records Office", created_at=NOW - timedelta(days=30))
    fresh = add_document("DOC-000031", "Records Office", created_at=NOW - timedelta(days=30))
    add_handoff(late, "Records Office", "Office of the Mayor", hours_ago=40)
    add_handoff(fresh, "Records Office", "Office of the Mayor", hours_ago=1)
    add_document("DOC-000032", "Office of the Mayor", created_at=NOW - timedelta(days=30), due=today - timedelta(days=3))

    body = notifications(client, "admin")

    assert sorted(kinds(body)) == [("handoff_overdue", "DOC-000030"), ("overdue", "DOC-000032")]
    by_number = {item["tracking_number"]: item["message"] for item in body["items"]}
    assert by_number["DOC-000030"] == "Records Office → Office of the Mayor, not received after 40 hours."
    assert by_number["DOC-000032"] == "Overdue by 3 days · Office of the Mayor."


def test_notifications_require_a_signed_in_user(client):
    assert client.get("/notifications").status_code == 401
    assert client.post("/notifications/seen").status_code == 401
