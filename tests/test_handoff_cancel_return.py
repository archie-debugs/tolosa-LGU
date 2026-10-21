import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

OFFICE_PERMISSIONS = ["pass_office_documents", "view_office_documents", "scan_qr",
                      "confirm_document_receipt", "view_office_document_details", "view_office_history"]


@pytest.fixture
def setup():
    """Office A holds DOC-000001 and has sent it to Office B, which has not received it yet."""
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        offices = {code: models.Office(name=f"Office {code}", office_code=f"OFF{code}") for code in "ABC"}
        db.add_all(offices.values())
        db.commit()
        office_ids = {code: office.id for code, office in offices.items()}

        def user(username, office, permissions=OFFICE_PERMISSIONS, role="Employee"):
            return models.User(username=username, hashed_password=get_password_hash("pw123"), role=role,
                               permissions=str(permissions), office_id=office, status="Active", is_active=True)

        db.add_all([user(f"emp_{code.lower()}", office_id) for code, office_id in office_ids.items()] + [
            user("viewer_a", office_ids["A"], ["view_office_documents", "view_office_document_details"]),
            user("admin", None, ["*"], role="Super Administrator"),
        ])
        db.add(models.Document(tracking_number="DOC-000001", title="Budget ordinance", status="Approved", priority="Medium",
                               qr_token="cancel-return-1", current_office="Office A", current_office_id=office_ids["A"]))
        db.commit()

    client = TestClient(main.app)
    headers = {name: headers_for(client, name) for name in ("emp_a", "emp_b", "emp_c", "viewer_a", "admin")}
    response = client.post(f"/documents/{document_id()}/handoffs", json={"receiving_office_id": office_ids["B"]}, headers=headers["emp_a"])
    assert response.status_code == 200, response.text
    return client, headers, office_ids, response.json()["id"]


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def document_id():
    with SessionLocal() as db:
        return db.query(models.Document.id).filter(models.Document.tracking_number == "DOC-000001").scalar()


def queue(client, headers):
    response = client.get("/documents/office/queue", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def audit_actions():
    with SessionLocal() as db:
        return [row.action for row in db.query(models.AuditLog).order_by(models.AuditLog.id)]


def test_the_sender_cancels_a_handoff_and_still_holds_the_document(setup):
    client, headers, offices, handoff_id = setup

    response = client.post(f"/documents/handoffs/{handoff_id}/cancel", json={}, headers=headers["emp_a"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "Cancelled"
    assert body["closed_at"] and body["closed_by_name"] == "emp_a" and body["close_reason"] is None
    assert "DOCUMENT_HANDOFF_CANCELLED" in audit_actions()
    sender = queue(client, headers["emp_a"])
    assert [item["tracking_number"] for item in sender["holding"]["items"]] == ["DOC-000001"]
    assert sender["outgoing"] == []
    assert queue(client, headers["emp_b"])["incoming"] == []
    # It can be sent again, to the right office this time.
    resend = client.post(f"/documents/{document_id()}/handoffs", json={"receiving_office_id": offices["C"]}, headers=headers["emp_a"])
    assert resend.status_code == 200, resend.text


def test_the_receiver_returns_a_handoff_with_a_reason(setup):
    client, headers, _, handoff_id = setup

    response = client.post(f"/documents/handoffs/{handoff_id}/return", json={"reason": "  Not for our office  "}, headers=headers["emp_b"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "Returned"
    assert body["close_reason"] == "Not for our office"
    assert body["closed_by_name"] == "emp_b"
    assert "DOCUMENT_HANDOFF_RETURNED" in audit_actions()
    assert [item["tracking_number"] for item in queue(client, headers["emp_a"])["holding"]["items"]] == ["DOC-000001"]
    # The receiver can no longer receive it.
    receipt = client.post("/documents/qr/DOC-000001/receipt", json={}, headers=headers["emp_b"])
    assert receipt.status_code == 403, receipt.text


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_returning_needs_a_reason(setup, reason):
    client, headers, _, handoff_id = setup

    response = client.post(f"/documents/handoffs/{handoff_id}/return", json={"reason": reason}, headers=headers["emp_b"])

    assert response.status_code == 400
    assert "why" in response.json()["detail"]
    assert queue(client, headers["emp_b"])["incoming"][0]["handoff_id"] == handoff_id


def test_only_the_right_office_can_cancel_or_return(setup):
    client, headers, _, handoff_id = setup

    def post(action, user):
        return client.post(f"/documents/handoffs/{handoff_id}/{action}", json={"reason": "x"}, headers=headers[user]).status_code

    assert post("cancel", "emp_b") == 403
    assert post("cancel", "emp_c") == 403
    assert post("return", "emp_a") == 403
    assert post("return", "emp_c") == 403
    # Same office, without the permission for the step.
    assert post("cancel", "viewer_a") == 403
    # A Super Administrator without an office monitors; the offices act.
    assert post("cancel", "admin") == 403
    assert client.post("/documents/handoffs/999999/cancel", json={}, headers=headers["emp_a"]).status_code == 404


def test_a_handoff_that_is_no_longer_pending_cannot_be_cancelled_or_returned(setup):
    client, headers, _, handoff_id = setup
    assert client.post("/documents/qr/DOC-000001/receipt", json={}, headers=headers["emp_b"]).status_code == 200

    cancel = client.post(f"/documents/handoffs/{handoff_id}/cancel", json={}, headers=headers["emp_a"])
    returned = client.post(f"/documents/handoffs/{handoff_id}/return", json={"reason": "late"}, headers=headers["emp_b"])

    assert cancel.status_code == 409 and "already received" in cancel.json()["detail"]
    assert returned.status_code == 409


def test_cancelling_twice_is_refused(setup):
    client, headers, _, handoff_id = setup
    assert client.post(f"/documents/handoffs/{handoff_id}/cancel", json={}, headers=headers["emp_a"]).status_code == 200

    again = client.post(f"/documents/handoffs/{handoff_id}/cancel", json={}, headers=headers["emp_a"])

    assert again.status_code == 409 and "already cancelled" in again.json()["detail"]


def test_the_trail_and_activity_show_the_return_with_its_reason(setup):
    client, headers, _, handoff_id = setup
    client.post(f"/documents/handoffs/{handoff_id}/return", json={"reason": "Wrong office"}, headers=headers["emp_b"])

    trail = client.get("/documents/qr/DOC-000001/trail", headers=headers["admin"]).json()

    # Only handoff events: on PostgreSQL the registration time is skewed by the session time zone (#16).
    handoff_events = [event for event in trail["events"] if event["type"] != "registered"]
    assert [event["type"] for event in handoff_events] == ["returned", "sent"]
    returned = handoff_events[0]
    assert (returned["office"], returned["to_office"], returned["actor"], returned["detail"]) == ("Office B", "Office A", "emp_b", "Wrong office")
    assert trail["location"]["state"] == "held" and trail["location"]["office"] == "Office A"
    assert queue(client, headers["emp_a"])["recent_activity"][0]["type"] == "returned"


def test_the_other_office_is_notified(setup):
    client, headers, offices, handoff_id = setup
    client.post(f"/documents/handoffs/{handoff_id}/return", json={"reason": "Wrong office"}, headers=headers["emp_b"])
    resend = client.post(f"/documents/{document_id()}/handoffs", json={"receiving_office_id": offices["C"]}, headers=headers["emp_a"])
    client.post(f"/documents/handoffs/{resend.json()['id']}/cancel", json={"reason": "Sent too early"}, headers=headers["emp_a"])

    def kinds(user):
        items = client.get("/notifications", headers=headers[user]).json()["items"]
        return {item["kind"]: item["message"] for item in items}

    sender = kinds("emp_a")
    assert "Returned by Office B" in sender["returned"] and "Reason: Wrong office" in sender["returned"]
    receiver = kinds("emp_c")
    assert "Office A cancelled the handoff" in receiver["cancelled"] and "Sent too early" in receiver["cancelled"]
    assert "incoming" not in receiver
    assert "returned" not in kinds("emp_b") and "cancelled" not in kinds("emp_b")
