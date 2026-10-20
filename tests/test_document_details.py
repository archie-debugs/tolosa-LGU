from datetime import datetime, timezone

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

OFFICE_PERMISSIONS = ["pass_office_documents", "view_office_documents", "scan_qr", "confirm_document_receipt",
                      "view_office_document_details", "view_office_history"]


def setup_offices():
    """Offices A, B and C, an employee in each, a Super Administrator assigned to A,
    and one document registered by Office A."""
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        offices = {code: models.Office(name=f"Office {code}", office_code=f"OFF{code}") for code in "ABC"}
        db.add_all(offices.values())
        db.commit()
        ids = {code: office.id for code, office in offices.items()}
        db.add_all([
            models.User(username=f"emp_{code.lower()}", full_name=f"Clerk {code}", hashed_password=get_password_hash("pw123"),
                        role="Employee", permissions=str(OFFICE_PERMISSIONS), office_id=office_id, status="Active", is_active=True)
            for code, office_id in ids.items()
        ] + [
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", office_id=ids["A"], status="Active", is_active=True),
        ])
        doc = models.Document(tracking_number="DOC-000001", title="Market ordinance", status="Approved", priority="High",
                              document_type="Ordinance", document_number="12", series_year="2026", remarks="Urgent",
                              qr_token="details-1", originating_office="Office A", current_office="Office A",
                              current_office_id=ids["A"], created_by="emp_a")
        db.add(doc)
        db.flush()
        db.add(models.DocumentOffice(document_id=doc.id, office_id=ids["A"]))
        db.commit()
        ids["doc"] = doc.id
    return ids


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def send(client, headers, ids, to):
    response = client.post(f"/documents/{ids['doc']}/handoffs", json={"receiving_office_id": ids[to]}, headers=headers)
    assert response.status_code == 200, response.text


def receive(client, headers):
    response = client.post("/documents/qr/details-1/receipt", json={}, headers=headers)
    assert response.status_code == 200, response.text


def record(client, headers, action_type="Signed", notes=None):
    return client.post("/documents/qr/details-1/actions", json={"action_type": action_type, "notes": notes}, headers=headers)


def overview(client, headers, ids):
    response = client.get(f"/documents/{ids['doc']}/overview", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_an_office_cannot_record_actions_on_a_document_it_passed_on():
    ids = setup_offices()
    client = TestClient(main.app)
    a, b, c = (headers_for(client, name) for name in ("emp_a", "emp_b", "emp_c"))
    send(client, a, ids, "B")
    receive(client, b)
    assert record(client, b).status_code == 200

    send(client, b, ids, "C")
    assert record(client, b).status_code == 403, "in transit to C: Office B no longer has it"
    receive(client, c)
    assert record(client, b).status_code == 403, "Office C holds it now"
    assert record(client, c).status_code == 200


def test_location_and_what_each_office_can_do_follow_custody():
    ids = setup_offices()
    client = TestClient(main.app)
    a, b, c = (headers_for(client, name) for name in ("emp_a", "emp_b", "emp_c"))

    at_a = overview(client, a, ids)
    assert at_a["location"] == {**at_a["location"], "state": "held", "office": "Office A"}
    assert at_a["can"] == {"receive": False, "pass": True, "record_action": False}

    send(client, a, ids, "B")
    sent = overview(client, a, ids)
    assert sent["location"] == {**sent["location"], "state": "in_transit", "office": "Office A", "to_office": "Office B", "actor": "Clerk A"}
    assert sent["can"] == {"receive": False, "pass": False, "record_action": False}
    assert overview(client, b, ids)["can"] == {"receive": True, "pass": False, "record_action": False}
    assert client.get(f"/documents/{ids['doc']}/overview", headers=c).status_code == 404

    receive(client, b)
    held = overview(client, b, ids)
    assert held["location"] == {**held["location"], "state": "held", "office": "Office B", "actor": "Clerk B"}
    assert held["can"] == {"receive": False, "pass": True, "record_action": True}
    assert overview(client, a, ids)["can"] == {"receive": False, "pass": False, "record_action": False}


def test_timeline_lists_the_whole_trail_newest_first():
    ids = setup_offices()
    client = TestClient(main.app)
    a, b = headers_for(client, "emp_a"), headers_for(client, "emp_b")
    send(client, a, ids, "B")
    receive(client, b)
    assert record(client, b, "Reviewed", "for the committee").status_code == 200

    events = overview(client, b, ids)["events"]
    assert [event["type"] for event in events] == ["action", "received", "sent", "registered"]
    assert events[0]["detail"] == "Reviewed: for the committee"
    assert events[2] == {**events[2], "office": "Office A", "to_office": "Office B", "actor": "Clerk A"}
    assert events[3] == {**events[3], "office": "Office A", "actor": "emp_a"}


def test_offices_see_only_their_own_actions_but_admins_see_everything():
    ids = setup_offices()
    client = TestClient(main.app)
    a, b, c = (headers_for(client, name) for name in ("emp_a", "emp_b", "emp_c"))
    send(client, a, ids, "B")
    receive(client, b)
    assert record(client, b, "Signed").status_code == 200
    send(client, b, ids, "C")
    receive(client, c)

    seen_by_c = overview(client, c, ids)
    assert [event["type"] for event in seen_by_c["events"]] == ["received", "sent", "received", "sent", "registered"]
    assert "remarks" not in seen_by_c["document"]

    seen_by_admin = overview(client, headers_for(client, "admin"), ids)
    assert "action" in [event["type"] for event in seen_by_admin["events"]]
    assert seen_by_admin["document"]["remarks"] == "Urgent"
    assert seen_by_admin["document"]["priority"] == "High"
    assert seen_by_admin["can"] == {"receive": False, "pass": False, "record_action": False}


def test_archived_documents_show_who_archived_them_and_allow_nothing():
    ids = setup_offices()
    client = TestClient(main.app)
    archived_at = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.query(models.Document).filter(models.Document.id == ids["doc"]).update(
            {"archived": True, "archived_at": archived_at, "archived_by": "admin"}
        )
        db.commit()

    archived = overview(client, headers_for(client, "admin"), ids)
    assert archived["location"] == {**archived["location"], "state": "archived", "actor": "admin"}
    assert archived["location"]["since"].startswith("2026-10-01T09:30")
    assert overview(client, headers_for(client, "emp_a"), ids)["can"] == {"receive": False, "pass": False, "record_action": False}


def test_overview_requires_document_access():
    ids = setup_offices()
    client = TestClient(main.app)
    with SessionLocal() as db:
        db.add(models.User(username="nobody", hashed_password=get_password_hash("pw123"), role="Employee",
                           permissions="[]", office_id=ids["A"], status="Active", is_active=True))
        db.commit()
    assert client.get(f"/documents/{ids['doc']}/overview", headers=headers_for(client, "nobody")).status_code == 403
    assert client.get("/documents/999999/overview", headers=headers_for(client, "admin")).status_code == 404
