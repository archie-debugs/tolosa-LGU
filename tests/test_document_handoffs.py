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

        db.add_all([
            models.DocumentOffice(document_id=doc.id, office_id=office_a.id),
            models.DocumentOffice(document_id=doc.id, office_id=office_b.id),
            models.DocumentOffice(document_id=doc.id, office_id=office_c.id),
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

    denied_b = client.get(f"/documents/qr/{qr_token}/office", headers=office_b_headers)
    assert denied_b.status_code == 403, denied_b.text
    assert "pending receipt" in denied_b.json()["detail"].lower()

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
