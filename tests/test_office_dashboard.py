from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

OFFICE_PERMISSIONS = ["pass_office_documents", "view_office_documents", "search_office_documents", "scan_qr",
                      "confirm_document_receipt", "view_office_document_details", "view_office_history"]


def setup_offices():
    """Office A registers five documents and routes them:
    1: A → B, not received (sent 30h ago)    2: A → B, received, then B → C, not received
    3: stays at A                              4: stays at A, archived
    5: A → B, received (B holds it)"""
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        offices = {code: models.Office(name=f"Office {code}", office_code=f"OFF{code}") for code in "ABC"}
        db.add_all(offices.values())
        db.commit()
        office_ids = {code: office.id for code, office in offices.items()}
        db.add_all([
            models.User(username=f"emp_{code.lower()}", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions=str(OFFICE_PERMISSIONS), office_id=office_id, status="Active", is_active=True)
            for code, office_id in office_ids.items()
        ] + [
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", office_id=office_ids["A"], status="Active", is_active=True),
        ])
        db.add_all([
            models.Document(tracking_number=f"DOC-00000{index}", title=f"Document {index}", status="Approved", priority="Medium",
                            qr_token=f"office-queue-{index}", current_office="Office A", current_office_id=office_ids["A"],
                            archived=index == 4)
            for index in range(1, 6)
        ])
        db.commit()
    return office_ids


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def document_id(tracking_number):
    with SessionLocal() as db:
        return db.query(models.Document.id).filter(models.Document.tracking_number == tracking_number).scalar()


def route(client, offices):
    a, b = headers_for(client, "emp_a"), headers_for(client, "emp_b")

    def send(headers, number, to):
        response = client.post(f"/documents/{document_id(f'DOC-00000{number}')}/handoffs", json={"receiving_office_id": offices[to]}, headers=headers)
        assert response.status_code == 200, response.text

    def receive(headers, number):
        response = client.post(f"/documents/qr/DOC-00000{number}/receipt", json={}, headers=headers)
        assert response.status_code == 200, response.text

    for number in (1, 2, 5):
        send(a, number, "B")
    receive(b, 2)
    receive(b, 5)
    send(b, 2, "C")
    with SessionLocal() as db:
        db.query(models.DocumentHandoff).filter(models.DocumentHandoff.document_id == document_id("DOC-000001")).update(
            {"sent_at": datetime.now(timezone.utc) - timedelta(hours=30)}
        )
        db.commit()


def numbers(items):
    return [item["tracking_number"] for item in items]


def test_queue_splits_an_office_s_work_into_incoming_holding_and_outgoing():
    offices = setup_offices()
    client = TestClient(main.app)
    route(client, offices)

    office_b = client.get("/documents/office/queue", headers=headers_for(client, "emp_b")).json()
    assert office_b["office"]["name"] == "Office B"
    assert office_b["own_office"] is True
    assert numbers(office_b["incoming"]) == ["DOC-000001"]
    assert office_b["incoming"][0]["overdue"] is True
    assert numbers(office_b["holding"]["items"]) == ["DOC-000005"]
    assert office_b["holding"]["items"][0]["received_at"] is not None
    assert numbers(office_b["outgoing"]) == ["DOC-000002"]
    assert office_b["outgoing"][0]["to_office"] == "Office C"
    assert office_b["summary"] == {
        "incoming": 1, "incoming_overdue": 1, "holding": 1, "outgoing": 1, "outgoing_overdue": 0,
        "received_today": 2, "sent_today": 1,
    }
    feed = office_b["recent_activity"]
    assert feed[0] == {**feed[0], "type": "sent", "tracking_number": "DOC-000002", "to_office": "Office C"}
    assert [event["at"] for event in feed] == sorted((event["at"] for event in feed), reverse=True)

    office_a = client.get("/documents/office/queue", headers=headers_for(client, "emp_a")).json()
    assert numbers(office_a["holding"]["items"]) == ["DOC-000003"]
    assert numbers(office_a["outgoing"]) == ["DOC-000001"]
    assert office_a["incoming"] == []


def test_queue_holding_list_can_be_searched():
    offices = setup_offices()
    client = TestClient(main.app)
    with SessionLocal() as db:
        db.query(models.Document).filter(models.Document.tracking_number == "DOC-000005").update({"title": "Market ordinance"})
        db.commit()
    headers = headers_for(client, "emp_a")
    assert numbers(client.get("/documents/office/queue", params={"search": "market"}, headers=headers).json()["holding"]["items"]) == ["DOC-000005"]
    assert numbers(client.get("/documents/office/queue", params={"search": "3"}, headers=headers).json()["holding"]["items"]) == ["DOC-000003"]


def test_employees_only_see_their_own_office_queue():
    offices = setup_offices()
    client = TestClient(main.app)
    queue = client.get("/documents/office/queue", params={"office_id": offices["C"]}, headers=headers_for(client, "emp_b")).json()
    assert queue["office"]["name"] == "Office B"

    admin = headers_for(client, "admin")
    monitored = client.get("/documents/office/queue", params={"office_id": offices["C"]}, headers=admin).json()
    assert (monitored["office"]["name"], monitored["own_office"]) == ("Office C", False)


def test_overview_counts_every_office_s_work_for_super_administrators():
    offices = setup_offices()
    client = TestClient(main.app)
    route(client, offices)

    assert client.get("/documents/office/overview", headers=headers_for(client, "emp_a")).status_code == 403
    overview = client.get("/documents/office/overview", headers=headers_for(client, "admin")).json()
    counts = {item["name"]: (item["incoming"], item["incoming_overdue"], item["holding"], item["outgoing"]) for item in overview["items"]}
    assert counts == {
        "Office A": (0, 0, 1, 1),
        "Office B": (1, 1, 1, 1),
        "Office C": (1, 0, 0, 0),
    }
