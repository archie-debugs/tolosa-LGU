from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

OFFICE_PERMISSIONS = ["pass_office_documents", "view_office_documents", "scan_qr", "confirm_document_receipt",
                      "view_office_document_details", "view_office_history", "record_document_actions"]


def setup_offices():
    """Office A sends two documents to Office B: one is received and acted on, one is still on its way."""
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        office_a = models.Office(name="Office A", office_code="OFFA")
        office_b = models.Office(name="Office B", office_code="OFFB")
        db.add_all([office_a, office_b])
        db.commit()
        users = [
            ("sender", "Employee", OFFICE_PERMISSIONS, office_a.id),
            ("receiver", "Employee", OFFICE_PERMISSIONS, office_b.id),
            ("monitor", "Employee", ["view_qr_tracking"], None),
            ("clerk", "Employee", ["view_documents"], None),
        ]
        db.add_all([
            models.User(username=name, hashed_password=get_password_hash("pw123"), role=role, permissions=str(perms),
                        office_id=office, status="Active", is_active=True)
            for name, role, perms, office in users
        ])
        docs = [
            models.Document(tracking_number=f"DOC-00000{index}", title=title, status="Approved", priority="Medium",
                            qr_token=f"qr-tracking-{index}", current_office="Office A", current_office_id=office_a.id, created_by="sender")
            for index, title in [(1, "Budget ordinance"), (2, "Road resolution")]
        ]
        db.add_all(docs)
        db.commit()
        return {"A": office_a.id, "B": office_b.id, "received": docs[0].id, "pending": docs[1].id}


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def route_documents(client, ids):
    sender, receiver = headers_for(client, "sender"), headers_for(client, "receiver")
    for document_id in (ids["received"], ids["pending"]):
        response = client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": ids["B"]}, headers=sender)
        assert response.status_code == 200, response.text
    assert client.post("/documents/qr/qr-tracking-1/receipt", json={}, headers=receiver).status_code == 200
    action = client.post("/documents/qr/qr-tracking-1/actions", json={"action_type": "Signed", "notes": "by the Vice Mayor"}, headers=receiver)
    assert action.status_code == 200, action.text
    # The second handoff was sent yesterday and nobody has received it.
    with SessionLocal() as db:
        db.query(models.DocumentHandoff).filter(models.DocumentHandoff.document_id == ids["pending"]).update(
            {"sent_at": datetime.now(timezone.utc) - timedelta(hours=30)}
        )
        db.commit()


def test_monitor_shows_todays_movement_and_documents_in_transit():
    ids = setup_offices()
    client = TestClient(main.app)
    route_documents(client, ids)

    response = client.get("/documents/qr/monitor", headers=headers_for(client, "monitor"))
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["summary"] == {
        "active_documents": 2,
        "in_transit": 1,
        "overdue": 1,
        "sent_today": 1,
        "received_today": 1,
        "actions_today": 1,
        "scans_today": 0,
        "unrecognized_today": 0,
    }
    [waiting] = payload["in_transit"]
    assert (waiting["tracking_number"], waiting["from_office"], waiting["to_office"], waiting["overdue"]) == ("DOC-000002", "Office A", "Office B", True)
    assert waiting["hours_waiting"] >= 30

    activity = payload["recent_activity"]
    assert [event["type"] for event in activity[:3]] == ["action", "received", "sent"]
    assert activity[0]["detail"] == "Signed: by the Vice Mayor"
    assert activity[-1] == {**activity[-1], "type": "sent", "tracking_number": "DOC-000002"}
    assert [event["at"] for event in activity] == sorted((event["at"] for event in activity), reverse=True)


def test_trail_shows_where_a_document_is_and_its_route_and_counts_as_a_scan():
    ids = setup_offices()
    client = TestClient(main.app)
    route_documents(client, ids)
    monitor = headers_for(client, "monitor")

    received = client.get("/documents/qr/DOC-000001/trail", headers=monitor)
    assert received.status_code == 200, received.text
    trail = received.json()
    assert trail["document"]["title"] == "Budget ordinance"
    assert trail["location"]["state"] == "held"
    assert trail["location"]["office"] == "Office B"
    assert [event["type"] for event in trail["events"]] == ["action", "received", "sent", "registered"]

    pending = client.get("/documents/qr/qr-tracking-2/trail", headers=monitor).json()
    assert pending["location"] == {**pending["location"], "state": "in_transit", "office": "Office A", "to_office": "Office B"}

    assert client.get("/documents/qr/NOT-A-CODE/trail", headers=monitor).status_code == 404

    summary = client.get("/documents/qr/monitor", headers=monitor).json()["summary"]
    assert (summary["scans_today"], summary["unrecognized_today"]) == (2, 1)
    feed = client.get("/documents/qr/monitor", headers=monitor).json()["recent_activity"]
    assert feed[0]["type"] == "unrecognized"
    assert feed[1] == {**feed[1], "type": "scan", "tracking_number": "DOC-000002"}


def test_qr_tracking_needs_its_permission():
    setup_offices()
    client = TestClient(main.app)
    clerk = headers_for(client, "clerk")
    assert client.get("/documents/qr/monitor", headers=clerk).status_code == 403
    assert client.get("/documents/qr/DOC-000001/trail", headers=clerk).status_code == 403
