import os

os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///./test_document_handoffs.sqlite"

for db_path in ["test_document_handoffs.sqlite"]:
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError:
        pass

import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.auth_jwt import create_access_token
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


def reset_db():
    with SessionLocal() as db:
        db.query(models.DocumentTrackingNumberAlias).delete()
        db.query(models.DocumentHandoff).delete()
        db.query(models.DocumentAction).delete()
        db.query(models.DocumentOffice).delete()
        db.query(models.DocumentReceipt).delete()
        db.query(models.Attachment).delete()
        db.query(models.Document).delete()
        db.query(models.UserSession).delete()
        db.query(models.AuditLog).delete()
        db.query(models.SystemSetting).delete()
        db.query(models.User).delete()
        db.query(models.Office).delete()
        db.query(models.RegistrationRequest).delete()
        db.commit()


def bearer_headers(client, username, password="pw123"):
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_employee(db, username, office_id, permissions=None):
    permissions = permissions or []
    user = models.User(
        username=username,
        hashed_password=get_password_hash("pw123"),
        role="Employee",
        office_id=office_id,
        permissions=str(permissions),
        status="Active",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_handoff_creation_and_pending_receipt_flow():
    reset_db()
    client = TestClient(main.app)

    with SessionLocal() as db:
        office_a = models.Office(name="Office A", office_code="OFFA")
        office_b = models.Office(name="Office B", office_code="OFFB")
        office_c = models.Office(name="Office C", office_code="OFFC")
        db.add_all([office_a, office_b, office_c])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)
        db.refresh(office_c)

        doc = models.Document(
            tracking_number="DOC-500001",
            title="Handoff Test Document",
            status="Approved",
            priority="Medium",
            qr_token="handoff-test-token-001",
            qr_code_value="https://example.test/qr/handoff-test-token-001",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        document_id = doc.id
        db.add(models.DocumentOffice(document_id=doc.id, office_id=office_a.id))
        db.commit()

        sender = create_employee(db, "handoffsender", office_a.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "view_office_document_details", "view_office_history"])
        receiving = create_employee(db, "handoffreceiver", office_b.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "confirm_document_receipt", "view_office_document_details", "view_office_history"])
        wrong_office = create_employee(db, "wrongoffice", office_c.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "confirm_document_receipt", "view_office_document_details", "view_office_history"])

        document_id = doc.id
        office_a_id = office_a.id
        office_b_id = office_b.id
        office_c_id = office_c.id
        sender_id = sender.id
        receiver_id = receiving.id
        qr_token = doc.qr_token

    sender_headers = bearer_headers(client, "handoffsender")
    receiver_headers = bearer_headers(client, "handoffreceiver")
    wrong_headers = bearer_headers(client, "wrongoffice")

    create_response = client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": office_b_id}, headers=sender_headers)
    assert create_response.status_code == 200, create_response.text
    payload = create_response.json()
    assert payload["document_id"] == document_id
    assert payload["sending_office_id"] == office_a_id
    assert payload["receiving_office_id"] == office_b_id
    assert payload["sending_employee_id"] == sender_id
    assert payload["status"] == "Pending Receipt"

    duplicate = client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": office_b_id}, headers=sender_headers)
    assert duplicate.status_code == 409, duplicate.text

    own_office = client.post(f"/documents/{document_id}/handoffs", json={"receiving_office_id": office_a_id}, headers=sender_headers)
    assert own_office.status_code == 400, own_office.text

    available = client.get("/offices/available-for-handoff", headers=sender_headers)
    assert available.status_code == 200, available.text
    office_ids = {item["id"] for item in available.json()}
    assert office_b_id in office_ids
    assert office_a_id not in office_ids

    qr_ok = client.get(f"/documents/qr/{qr_token}/office", headers=receiver_headers)
    assert qr_ok.status_code == 200, qr_ok.text

    qr_wrong = client.get(f"/documents/qr/{qr_token}/office", headers=wrong_headers)
    assert qr_wrong.status_code == 403, qr_wrong.text

    receipt = client.post(f"/documents/qr/{qr_token}/receipt", headers=receiver_headers)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["status"] == "confirmed"
    assert receipt.json()["receipt"]["handoff_id"] is not None
    assert receipt.json()["receipt"]["office_id"] == office_b_id

    history = client.get(f"/documents/{document_id}/handoffs", headers=receiver_headers)
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "Received"
    assert items[0]["receiving_office_id"] == office_b_id


def test_super_admin_handoff_uses_assigned_office_and_requires_assignment():
    reset_db()
    client = TestClient(main.app)

    with SessionLocal() as db:
        office_a = models.Office(name="Main SB Office", office_code="MAIN")
        office_b = models.Office(name="Receiving Office", office_code="RECV")
        office_c = models.Office(name="Arbitrary Office", office_code="ARBT")
        db.add_all([office_a, office_b, office_c])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)
        db.refresh(office_c)

        doc = models.Document(
            tracking_number="DOC-500010",
            title="Super Administrator Handoff",
            status="Approved",
            priority="Medium",
            qr_token="handoff-super-admin-token-010",
            qr_code_value="https://example.test/qr/handoff-super-admin-token-010",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        db.add(models.DocumentOffice(document_id=doc.id, office_id=office_a.id))
        assigned_admin = models.User(
            username="assigned-super-admin",
            hashed_password=get_password_hash("pw123"),
            role="Super Administrator",
            office_id=office_a.id,
            permissions="['*']",
            status="Active",
            is_active=True,
        )
        unassigned_admin = models.User(
            username="unassigned-super-admin",
            hashed_password=get_password_hash("pw123"),
            role="Super Administrator",
            office_id=None,
            permissions="['*']",
            status="Active",
            is_active=True,
        )
        db.add_all([assigned_admin, unassigned_admin])
        db.commit()
        document_id = doc.id
        office_a_id = office_a.id
        office_b_id = office_b.id
        office_c_id = office_c.id

    denied = client.post(
        f"/documents/{document_id}/handoffs",
        json={"receiving_office_id": office_b_id},
        headers=bearer_headers(client, "unassigned-super-admin", "pw123"),
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Office assignment required"

    created = client.post(
        f"/documents/{document_id}/handoffs",
        json={"receiving_office_id": office_b_id, "sending_office_id": office_c_id},
        headers=bearer_headers(client, "assigned-super-admin", "pw123"),
    )
    assert created.status_code == 200, created.text
    assert created.json()["sending_office_id"] == office_a_id
    assert created.json()["receiving_office_id"] == office_b_id


def test_super_admin_can_monitor_selected_office_without_changing_assignment():
    reset_db()
    client = TestClient(main.app)

    with SessionLocal() as db:
        office_a = models.Office(name="Assigned Office", office_code="ASGN")
        office_b = models.Office(name="Monitored Office", office_code="MONI")
        db.add_all([office_a, office_b])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)
        doc = models.Document(
            tracking_number="DOC-500011",
            title="Monitored Document",
            status="Approved",
            priority="Medium",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        db.add(models.DocumentOffice(document_id=doc.id, office_id=office_b.id))
        admin = models.User(
            username="monitoring-super-admin",
            hashed_password=get_password_hash("pw123"),
            role="Super Administrator",
            office_id=office_a.id,
            permissions="['*']",
            status="Active",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        monitored_office_id = office_b.id
        document_id = doc.id

    headers = bearer_headers(client, "monitoring-super-admin", "pw123")
    documents = client.get(
        "/documents/office",
        params={"office_id": monitored_office_id},
        headers=headers,
    )
    assert documents.status_code == 200, documents.text
    assert [item["id"] for item in documents.json()["items"]] == [document_id]

    incoming = client.get(
        "/documents/office/handoffs",
        params={"office_id": monitored_office_id, "direction": "incoming"},
        headers=headers,
    )
    assert incoming.status_code == 200, incoming.text

    history = client.get(
        "/documents/office/history",
        params={"office_id": monitored_office_id},
        headers=headers,
    )
    assert history.status_code == 200, history.text
    assert history.json()["office_id"] == monitored_office_id

    with SessionLocal() as db:
        admin = db.query(models.User).filter(models.User.username == "monitoring-super-admin").one()
        assert admin.office_id != monitored_office_id


def test_handoff_lists_are_office_scoped_and_history_is_ordered():
    reset_db()
    client = TestClient(main.app)

    with SessionLocal() as db:
        office_a = models.Office(name="Office A List", office_code="OFFAL")
        office_b = models.Office(name="Office B List", office_code="OFFBL")
        office_c = models.Office(name="Office C List", office_code="OFFCL")
        db.add_all([office_a, office_b, office_c])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)
        db.refresh(office_c)

        doc = models.Document(
            tracking_number="DOC-500002",
            title="History Document",
            status="Approved",
            priority="Medium",
            qr_token="handoff-history-token-002",
            qr_code_value="https://example.test/qr/handoff-history-token-002",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        db.add_all([
            models.DocumentOffice(document_id=doc.id, office_id=office_a.id),
            models.DocumentOffice(document_id=doc.id, office_id=office_b.id),
        ])

        sender = create_employee(db, "list_sender", office_a.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "view_office_document_details", "view_office_history"])
        receiver = create_employee(db, "list_receiver", office_b.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "confirm_document_receipt", "view_office_document_details", "view_office_history"])
        other = create_employee(db, "other_office", office_c.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "confirm_document_receipt", "view_office_document_details", "view_office_history"])

        handoff = models.DocumentHandoff(
            document_id=doc.id,
            sending_office_id=office_a.id,
            receiving_office_id=office_b.id,
            sending_employee_id=sender.id,
            status="Pending Receipt",
        )
        db.add(handoff)
        db.commit()
        db.refresh(handoff)

        receipt = models.DocumentReceipt(
            document_id=doc.id,
            office_id=office_b.id,
            confirmed_by_user_id=receiver.id,
            status="Received",
            handoff_id=handoff.id,
        )
        db.add(receipt)
        db.commit()
        handoff.status = "Received"
        db.commit()

        office_a_id = office_a.id
        office_b_id = office_b.id
        document_id = doc.id
        receiver_id = receiver.id

    sender_headers = bearer_headers(client, "list_sender")
    receiver_headers = bearer_headers(client, "list_receiver")
    other_headers = bearer_headers(client, "other_office")

    sent = client.get("/documents/office/handoffs", params={"direction": "sent"}, headers=sender_headers)
    assert sent.status_code == 200, sent.text
    assert sent.json()["total"] == 1
    assert sent.json()["items"][0]["sending_office_id"] == office_a_id

    incoming = client.get("/documents/office/handoffs", params={"direction": "incoming"}, headers=receiver_headers)
    assert incoming.status_code == 200, incoming.text
    assert incoming.json()["total"] == 1
    assert incoming.json()["items"][0]["receiving_office_id"] == office_b_id

    other_list = client.get("/documents/office/handoffs", params={"direction": "incoming", "office_id": office_a_id}, headers=receiver_headers)
    assert other_list.status_code == 200, other_list.text
    assert other_list.json()["items"][0]["receiving_office_id"] == office_b_id

    history = client.get(f"/documents/{document_id}/handoffs", headers=receiver_headers)
    assert history.status_code == 200, history.text
    rows = history.json()["items"]
    assert rows[0]["status"] == "Received"
    assert rows[0]["linked_receipt"]["receiving_employee_id"] == receiver_id


def test_qr_office_access_requires_matching_pending_handoff_for_receiving_office():
    reset_db()
    client = TestClient(main.app)

    qr_token = "handoff-repeat-token-003"
    with SessionLocal() as db:
        office_a = models.Office(name="Office A Repeat", office_code="OFFAR")
        office_b = models.Office(name="Office B Repeat", office_code="OFFBR")
        office_c = models.Office(name="Office C Repeat", office_code="OFFCR")
        db.add_all([office_a, office_b, office_c])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)
        db.refresh(office_c)

        doc = models.Document(
            tracking_number="DOC-500003",
            title="Repeated Handoff Document",
            status="Approved",
            priority="Medium",
            qr_token=qr_token,
            qr_code_value="https://example.test/qr/handoff-repeat-token-003",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        document_id = doc.id

        db.add_all([
            models.DocumentOffice(document_id=doc.id, office_id=office_a.id),
        ])

        sender_a = create_employee(db, "repeat_sender_a", office_a.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "view_office_document_details", "view_office_history"])
        sender_b = create_employee(db, "repeat_sender_b", office_b.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "view_office_document_details", "view_office_history"])
        receiver_c = create_employee(db, "repeat_receiver_c", office_c.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "confirm_document_receipt", "view_office_document_details", "view_office_history"])
        receiver_b = create_employee(db, "repeat_receiver_b", office_b.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "confirm_document_receipt", "view_office_document_details", "view_office_history"])

        history_1 = models.DocumentHandoff(
            document_id=doc.id,
            sending_office_id=office_a.id,
            receiving_office_id=office_b.id,
            sending_employee_id=sender_a.id,
            status="Received",
        )
        history_2 = models.DocumentHandoff(
            document_id=doc.id,
            sending_office_id=office_b.id,
            receiving_office_id=office_c.id,
            sending_employee_id=sender_b.id,
            status="Pending Receipt",
        )
        db.add_all([history_1, history_2])
        db.commit()
        db.refresh(history_1)
        db.refresh(history_2)

        db.add(models.DocumentReceipt(
            document_id=doc.id,
            office_id=office_b.id,
            handoff_id=history_1.id,
            confirmed_by_user_id=receiver_b.id,
            status="Received",
        ))
        db.commit()

    office_a_headers = bearer_headers(client, "repeat_sender_a")
    office_b_headers = bearer_headers(client, "repeat_receiver_b")
    office_c_headers = bearer_headers(client, "repeat_receiver_c")

    allowed = client.get(f"/documents/qr/{qr_token}/office", headers=office_c_headers)
    assert allowed.status_code == 200, allowed.text
    allowed_details = client.get(
        f"/documents/office/{document_id}",
        headers=office_c_headers,
    )
    assert allowed_details.status_code == 200, allowed_details.text

    received_b = client.get(f"/documents/qr/{qr_token}/office", headers=office_b_headers)
    assert received_b.status_code == 200, received_b.text
    assert received_b.json()["handoff_status"] == "Received"
    received_b_details = client.get(
        f"/documents/office/{document_id}",
        headers=office_b_headers,
    )
    assert received_b_details.status_code == 200, received_b_details.text

    denied_a = client.get(f"/documents/qr/{qr_token}/office", headers=office_a_headers)
    assert denied_a.status_code == 403, denied_a.text


def test_receipt_confirmation_requires_matching_pending_handoff():
    reset_db()
    client = TestClient(main.app)

    qr_token = "handoff-receipt-gate-004"
    with SessionLocal() as db:
        office_a = models.Office(name="Office A Receipt Gate", office_code="OFFARG")
        office_b = models.Office(name="Office B Receipt Gate", office_code="OFFBRG")
        db.add_all([office_a, office_b])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)

        doc = models.Document(
            tracking_number="DOC-500004",
            title="Receipt Gate Document",
            status="Approved",
            priority="Medium",
            qr_token=qr_token,
            qr_code_value="https://example.test/qr/handoff-receipt-gate-004",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        db.add(models.DocumentOffice(document_id=doc.id, office_id=office_a.id))
        sender = create_employee(db, "receiptgate_sender", office_a.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "view_office_document_details", "view_office_history"])
        receiver = create_employee(db, "receiptgate_receiver", office_b.id, permissions=["pass_office_documents", "view_office_documents", "scan_qr", "confirm_document_receipt", "view_office_document_details", "view_office_history"])

        handoff = models.DocumentHandoff(
            document_id=doc.id,
            sending_office_id=office_a.id,
            receiving_office_id=office_b.id,
            sending_employee_id=sender.id,
            status="Received",
        )
        db.add(handoff)
        db.commit()
        db.refresh(handoff)

        db.add(models.DocumentReceipt(
            document_id=doc.id,
            office_id=office_b.id,
            handoff_id=handoff.id,
            confirmed_by_user_id=receiver.id,
            status="Received",
        ))
        db.commit()

    receiver_headers = bearer_headers(client, "receiptgate_receiver")
    denied = client.post(f"/documents/qr/{qr_token}/receipt", headers=receiver_headers)
    assert denied.status_code == 403, denied.text
    assert "not pending receipt" in denied.json()["detail"].lower()


def test_received_document_can_record_multiple_actions_and_list_history():
    reset_db()
    client = TestClient(main.app)

    with SessionLocal() as db:
        office_a = models.Office(name="Action Sender Office", office_code="ACTA")
        office_b = models.Office(name="Action Receiver Office", office_code="ACTB")
        db.add_all([office_a, office_b])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)

        doc = models.Document(
            tracking_number="DOC-ACTION-001",
            title="Action Test Document",
            status="Approved",
            priority="Medium",
            qr_token="action-test-token-001",
            qr_code_value="https://example.test/qr/action-test-token-001",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        db.add(models.DocumentOffice(document_id=doc.id, office_id=office_a.id))
        sender = create_employee(
            db,
            "action_sender",
            office_a.id,
            permissions=["pass_office_documents"],
        )
        employee = create_employee(
            db,
            "action_receiver",
            office_b.id,
            permissions=["scan_qr", "view_office_document_details", "view_office_history"],
        )
        handoff = models.DocumentHandoff(
            document_id=doc.id,
            sending_office_id=office_a.id,
            receiving_office_id=office_b.id,
            sending_employee_id=sender.id,
            status="Received",
        )
        db.add(handoff)
        db.commit()
        db.refresh(handoff)
        db.add(models.DocumentReceipt(
            document_id=doc.id,
            office_id=office_b.id,
            handoff_id=handoff.id,
            confirmed_by_user_id=employee.id,
            status="Received",
        ))
        db.commit()
        document_id = doc.id
        office_b_id = office_b.id
        employee_id = employee.id
        handoff_id = handoff.id

    headers = bearer_headers(client, "action_receiver")
    first = client.post(
        f"/documents/qr/action-test-token-001/actions",
        json={"action_type": "Signed", "notes": "Signed by reviewer"},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["document_id"] == document_id
    assert first_payload["office_id"] == office_b_id
    assert first_payload["employee_id"] == employee_id
    assert first_payload["handoff_id"] == handoff_id
    assert first_payload["action_type"] == "Signed"

    second = client.post(
        f"/documents/qr/action-test-token-001/actions",
        json={"action_type": "Reviewed"},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    third = client.post(
        f"/documents/qr/action-test-token-001/actions",
        json={"action_type": "Received", "notes": "Document received and acknowledged."},
        headers=headers,
    )
    assert third.status_code == 200, third.text
    third_payload = third.json()
    assert third_payload["document_id"] == document_id
    assert third_payload["office_id"] == office_b_id
    assert third_payload["employee_id"] == employee_id
    assert third_payload["handoff_id"] == handoff_id
    assert third_payload["action_type"] == "Received"
    assert third_payload["performed_at"]
    history = client.get(f"/documents/{document_id}/actions", headers=headers)
    assert history.status_code == 200, history.text
    assert [item["action_type"] for item in history.json()["items"]] == ["Signed", "Reviewed", "Received"]

    with SessionLocal() as db:
        rows = db.query(models.DocumentAction).filter(models.DocumentAction.document_id == document_id).all()
        assert len(rows) == 3
        received = next(row for row in rows if row.action_type == "Received")
        assert received.document_id == document_id
        assert received.office_id == office_b_id
        assert received.employee_id == employee_id
        assert received.handoff_id == handoff_id
        assert received.performed_at is not None


def test_pending_receipt_cannot_record_document_action():
    reset_db()
    client = TestClient(main.app)

    with SessionLocal() as db:
        office_a = models.Office(name="Pending Action Sender", office_code="PASA")
        office_b = models.Office(name="Pending Action Receiver", office_code="PASB")
        db.add_all([office_a, office_b])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)
        doc = models.Document(
            tracking_number="DOC-ACTION-002",
            title="Pending Action Document",
            status="Approved",
            priority="Medium",
            qr_token="action-test-token-002",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        db.add(models.DocumentOffice(document_id=doc.id, office_id=office_a.id))
        receiver = create_employee(
            db,
            "pending_action_receiver",
            office_b.id,
            permissions=["scan_qr", "view_office_document_details"],
        )
        db.add(models.DocumentHandoff(
            document_id=doc.id,
            sending_office_id=office_a.id,
            receiving_office_id=office_b.id,
            sending_employee_id=receiver.id,
            status="Pending Receipt",
        ))
        db.commit()

    response = client.post(
        "/documents/qr/action-test-token-002/actions",
        json={"action_type": "Received"},
        headers=bearer_headers(client, "pending_action_receiver"),
    )
    assert response.status_code == 403, response.text
    with SessionLocal() as db:
        assert db.query(models.DocumentAction).count() == 0


def test_wrong_office_cannot_record_document_action():
    reset_db()
    client = TestClient(main.app)

    with SessionLocal() as db:
        office_a = models.Office(name="Wrong Action Sender", office_code="WASA")
        office_b = models.Office(name="Wrong Action Receiver", office_code="WASB")
        office_c = models.Office(name="Wrong Action Office", office_code="WASC")
        db.add_all([office_a, office_b, office_c])
        db.commit()
        db.refresh(office_a)
        db.refresh(office_b)
        db.refresh(office_c)
        doc = models.Document(
            tracking_number="DOC-ACTION-003",
            title="Wrong Office Action Document",
            status="Approved",
            priority="Medium",
            qr_token="action-test-token-003",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        db.add(models.DocumentOffice(document_id=doc.id, office_id=office_a.id))
        receiver = create_employee(
            db,
            "correct_action_receiver",
            office_b.id,
            permissions=["scan_qr", "view_office_document_details"],
        )
        wrong_office = create_employee(
            db,
            "wrong_action_office",
            office_c.id,
            permissions=["scan_qr", "view_office_document_details"],
        )
        db.add(models.DocumentHandoff(
            document_id=doc.id,
            sending_office_id=office_a.id,
            receiving_office_id=office_b.id,
            sending_employee_id=receiver.id,
            status="Received",
        ))
        db.commit()
        handoff = db.query(models.DocumentHandoff).filter(
            models.DocumentHandoff.document_id == doc.id
        ).one()
        db.add(models.DocumentReceipt(
            document_id=doc.id,
            office_id=office_b.id,
            handoff_id=handoff.id,
            confirmed_by_user_id=receiver.id,
            status="Received",
        ))
        db.commit()

    response = client.post(
        "/documents/qr/action-test-token-003/actions",
        json={"action_type": "Received"},
        headers=bearer_headers(client, "wrong_action_office"),
    )
    assert response.status_code == 403, response.text
    with SessionLocal() as db:
        assert db.query(models.DocumentAction).count() == 0


def test_received_office_document_count_uses_completed_receipts_without_duplicates():
    reset_db()
    client = TestClient(main.app)

    with SessionLocal() as db:
        office_a = models.Office(name="Count Sender Office", office_code="CSA")
        office_b = models.Office(name="Count Receiver Office", office_code="CSB")
        office_c = models.Office(name="Count Other Office", office_code="CSC")
        db.add_all([office_a, office_b, office_c])
        db.commit()
        for office in (office_a, office_b, office_c):
            db.refresh(office)

        employee_a = create_employee(db, "count_employee_a", office_a.id, ["view_office_documents"])
        employee_b = create_employee(db, "count_employee_b", office_b.id, ["view_office_documents"])
        employee_c = create_employee(db, "count_employee_c", office_c.id, ["view_office_documents"])

        received_doc = models.Document(
            tracking_number="DOC-COUNT-001",
            title="Received Count Document",
            status="Approved",
            priority="Medium",
            qr_token="count-test-token-001",
        )
        pending_doc = models.Document(
            tracking_number="DOC-COUNT-002",
            title="Pending Count Document",
            status="Approved",
            priority="Medium",
            qr_token="count-test-token-002",
        )
        sent_doc = models.Document(
            tracking_number="DOC-COUNT-003",
            title="Sent Count Document",
            status="Approved",
            priority="Medium",
            qr_token="count-test-token-003",
        )
        current_doc = models.Document(
            tracking_number="DOC-COUNT-004",
            title="Current Office Count Document",
            status="Approved",
            priority="Medium",
            qr_token="count-test-token-004",
            current_office_id=office_a.id,
        )
        archived_doc = models.Document(
            tracking_number="DOC-COUNT-005",
            title="Archived Count Document",
            status="Approved",
            priority="Medium",
            qr_token="count-test-token-005",
            current_office_id=office_a.id,
            archived=True,
        )
        db.add_all([received_doc, pending_doc, sent_doc, current_doc, archived_doc])
        db.commit()
        for document in (received_doc, pending_doc, sent_doc, current_doc, archived_doc):
            db.refresh(document)

        db.add_all([
            models.DocumentOffice(document_id=received_doc.id, office_id=office_a.id),
            models.DocumentOffice(document_id=pending_doc.id, office_id=office_a.id),
        ])
        received_handoff_one = models.DocumentHandoff(
            document_id=received_doc.id,
            sending_office_id=office_a.id,
            receiving_office_id=office_b.id,
            sending_employee_id=employee_a.id,
            status="Received",
        )
        received_handoff_two = models.DocumentHandoff(
            document_id=received_doc.id,
            sending_office_id=office_a.id,
            receiving_office_id=office_b.id,
            sending_employee_id=employee_a.id,
            status="Received",
        )
        pending_handoff = models.DocumentHandoff(
            document_id=pending_doc.id,
            sending_office_id=office_a.id,
            receiving_office_id=office_b.id,
            sending_employee_id=employee_a.id,
            status="Pending Receipt",
        )
        sent_handoff = models.DocumentHandoff(
            document_id=sent_doc.id,
            sending_office_id=office_b.id,
            receiving_office_id=office_c.id,
            sending_employee_id=employee_b.id,
            status="Received",
        )
        db.add_all([received_handoff_one, received_handoff_two, pending_handoff, sent_handoff])
        db.commit()
        for handoff in (received_handoff_one, received_handoff_two, sent_handoff):
            db.refresh(handoff)
        db.add_all([
            models.DocumentReceipt(
                document_id=received_doc.id,
                office_id=office_b.id,
                handoff_id=received_handoff_one.id,
                confirmed_by_user_id=employee_b.id,
                status="Received",
            ),
            models.DocumentReceipt(
                document_id=received_doc.id,
                office_id=office_b.id,
                handoff_id=received_handoff_two.id,
                confirmed_by_user_id=employee_b.id,
                status="Received",
            ),
            models.DocumentReceipt(
                document_id=sent_doc.id,
                office_id=office_c.id,
                handoff_id=sent_handoff.id,
                confirmed_by_user_id=employee_c.id,
                status="Received",
            ),
        ])
        db.commit()
        office_a_id = office_a.id
        office_b_id = office_b.id
        office_c_id = office_c.id

    office_b_response = client.get(
        f"/documents/office/received-count?office_id={office_b_id}",
        headers=bearer_headers(client, "count_employee_b"),
    )
    assert office_b_response.status_code == 200, office_b_response.text
    assert office_b_response.json()["total"] == 1

    office_c_response = client.get(
        f"/documents/office/received-count?office_id={office_c_id}",
        headers=bearer_headers(client, "count_employee_c"),
    )
    assert office_c_response.status_code == 200, office_c_response.text
    assert office_c_response.json()["total"] == 1

    office_a_response = client.get(
        f"/documents/office/received-count?office_id={office_a_id}",
        headers=bearer_headers(client, "count_employee_a"),
    )
    assert office_a_response.status_code == 200, office_a_response.text
    assert office_a_response.json()["total"] == 3
