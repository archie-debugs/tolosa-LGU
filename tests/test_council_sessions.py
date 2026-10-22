from datetime import date

import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.database import SessionLocal, engine
from Backends.backend.routes import council, council_sessions
from tests.test_council import TERM, add_member, make_term
from tests.test_settings_pages import add_user, headers_for, reset_db

models.Base.metadata.create_all(bind=engine)

TODAY = date(2026, 10, 22)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(council, "lgu_today", lambda: TODAY)
    monkeypatch.setattr(council_sessions, "lgu_today", lambda: TODAY)
    reset_db()
    add_user("admin", "Super Administrator", ["*"])
    add_user("clerk", "Employee", ["view_documents", "manage_sessions"])
    add_user("member", "SB Member", ["view_documents", "manage_sessions"])
    return TestClient(main.app)


@pytest.fixture
def council_term(client):
    """A term with five members; Hon. Reyes left on 2026-09-30."""
    admin = headers_for(client, "admin")
    term = make_term(client, admin)
    ids = {}
    for name, position in [("Hon. Santos", "Vice Mayor"), ("Hon. Cruz", "Regular Member"), ("Hon. Dela Paz", "Regular Member"),
                           ("Hon. Lim", "Regular Member"), ("Hon. Reyes", "Regular Member")]:
        ids[name] = add_member(client, admin, term["id"], name, position).json()["id"]
    reyes = client.put(f"/council/members/{ids['Hon. Reyes']}", headers=admin,
                       json={"full_name": "Hon. Reyes", "position": "Regular Member", "user_id": None, "left_on": "2026-09-30"})
    assert reyes.status_code == 200, reyes.text
    return term, ids


def new_session(client, headers, term, held_on="2026-10-20", **extra):
    return client.post("/council/sessions", headers=headers, json={"term_id": term["id"], "kind": "Regular", "held_on": held_on, **extra})


def mark(client, headers, session, marks):
    return client.put(f"/council/sessions/{session['id']}/attendance", headers=headers,
                      json={"marks": [{"member_id": member_id, "mark": value} for member_id, value in marks.items()]})


def set_status(client, headers, session, status):
    return client.post(f"/council/sessions/{session['id']}/status", headers=headers, json={"status": status})


def audit_actions():
    with SessionLocal() as db:
        actions = [row.action for row in db.query(models.AuditLog).order_by(models.AuditLog.id).all()]
    return [action for action in actions if action.startswith(("SESSION_", "ATTENDANCE_"))]


def test_sessions_are_numbered_within_the_term_by_kind(client, council_term):
    term, _ = council_term
    clerk = headers_for(client, "clerk")

    first = new_session(client, clerk, term).json()
    second = new_session(client, clerk, term, held_on="2026-10-21").json()
    special = new_session(client, clerk, term, held_on="2026-10-21", kind="Special").json()
    taken = new_session(client, clerk, term, number=2)
    outside = new_session(client, clerk, term, held_on="2029-01-05")

    assert [first["title"], second["title"], special["title"]] == ["1st Regular Session", "2nd Regular Session", "1st Special Session"]
    assert first["status"] == "Draft"
    assert taken.status_code == 409 and outside.status_code == 400
    listed = client.get("/council/sessions", headers=clerk).json()
    assert [s["title"] for s in listed["sessions"]] == ["1st Special Session", "2nd Regular Session", "1st Regular Session"]
    assert listed["next_numbers"] == {"Regular": 3, "Special": 2}


def test_attendance_covers_the_members_in_office_that_day_and_quorum_is_a_majority(client, council_term):
    term, ids = council_term
    clerk = headers_for(client, "clerk")
    session = new_session(client, clerk, term).json()

    assert [row["full_name"] for row in session["attendance"]] == ["Hon. Santos", "Hon. Cruz", "Hon. Dela Paz", "Hon. Lim"]
    left = mark(client, clerk, session, {ids["Hon. Reyes"]: "Present"})
    two = mark(client, clerk, session, {ids["Hon. Santos"]: "Present", ids["Hon. Cruz"]: "Present", ids["Hon. Lim"]: "On leave"}).json()

    assert left.status_code == 400
    assert two["quorum"] == {"present": 2, "in_office": 4, "needed": 3, "has_quorum": False, "unmarked": 1}
    three = mark(client, clerk, session, {ids["Hon. Dela Paz"]: "Present"}).json()
    assert three["quorum"]["has_quorum"] is True and three["quorum"]["unmarked"] == 0


def test_before_a_session_is_held_attendance_is_simply_replaced(client, council_term):
    term, ids = council_term
    clerk = headers_for(client, "clerk")
    session = new_session(client, clerk, term).json()
    mark(client, clerk, session, {ids["Hon. Cruz"]: "Absent"})

    changed = mark(client, clerk, session, {ids["Hon. Cruz"]: "Excused"}).json()
    cruz = next(row for row in changed["attendance"] if row["full_name"] == "Hon. Cruz")
    cleared = mark(client, clerk, session, {ids["Hon. Cruz"]: None}).json()

    assert cruz["mark"] == "Excused" and len(cruz["history"]) == 1
    assert next(row for row in cleared["attendance"] if row["full_name"] == "Hon. Cruz")["mark"] is None


def test_a_session_moves_draft_scheduled_held_and_only_on_or_after_its_date(client, council_term):
    term, _ = council_term
    clerk = headers_for(client, "clerk")
    future = new_session(client, clerk, term, held_on="2026-11-02").json()
    past = new_session(client, clerk, term, held_on="2026-10-19").json()

    assert set_status(client, clerk, future, "Scheduled").json()["next_statuses"] == ["Draft", "Held"]
    assert set_status(client, clerk, future, "Held").status_code == 400
    held = set_status(client, clerk, past, "Held").json()
    assert held["status"] == "Held" and held["next_statuses"] == []
    assert set_status(client, clerk, past, "Draft").status_code == 400
    assert client.put(f"/council/sessions/{past['id']}", headers=clerk,
                      json={"kind": "Regular", "number": 9, "held_on": "2026-10-19"}).status_code == 409


def test_after_a_session_is_held_attendance_is_corrected_with_a_reason_and_the_original_stays(client, council_term):
    term, ids = council_term
    clerk = headers_for(client, "clerk")
    session = new_session(client, clerk, term).json()
    mark(client, clerk, session, {ids["Hon. Lim"]: "Absent"})
    set_status(client, clerk, session, "Held")

    edited = mark(client, clerk, session, {ids["Hon. Lim"]: "Present"})
    no_reason = client.post(f"/council/sessions/{session['id']}/attendance/corrections", headers=clerk,
                            json={"member_id": ids["Hon. Lim"], "mark": "Present", "reason": " "})
    corrected = client.post(f"/council/sessions/{session['id']}/attendance/corrections", headers=clerk,
                            json={"member_id": ids["Hon. Lim"], "mark": "Present", "reason": "Arrived after the roll call"})

    assert edited.status_code == 409 and no_reason.status_code in (400, 422)
    lim = next(row for row in corrected.json()["attendance"] if row["full_name"] == "Hon. Lim")
    assert lim["mark"] == "Present"
    assert [(h["mark"], h["is_correction"], h["note"]) for h in lim["history"]] == [
        ("Present", True, "Arrived after the roll call"), ("Absent", False, None)]
    assert audit_actions() == ["SESSION_CREATED", "ATTENDANCE_RECORDED", "SESSION_STATUS_CHANGED", "ATTENDANCE_CORRECTED"]


def test_only_draft_sessions_can_be_deleted(client, council_term):
    term, _ = council_term
    clerk = headers_for(client, "clerk")
    draft = new_session(client, clerk, term).json()
    scheduled = new_session(client, clerk, term, held_on="2026-10-21").json()
    set_status(client, clerk, scheduled, "Scheduled")

    assert client.delete(f"/council/sessions/{scheduled['id']}", headers=clerk).status_code == 409
    assert client.delete(f"/council/sessions/{draft['id']}", headers=clerk).status_code == 200
    assert client.get(f"/council/sessions/{draft['id']}", headers=clerk).status_code == 404


def test_moving_the_date_drops_marks_of_members_no_longer_in_office(client, council_term):
    term, ids = council_term
    admin = headers_for(client, "admin")
    session = new_session(client, admin, term, held_on="2026-09-15").json()
    mark(client, admin, session, {ids["Hon. Reyes"]: "Present", ids["Hon. Cruz"]: "Present"})

    moved = client.put(f"/council/sessions/{session['id']}", headers=admin,
                       json={"kind": "Regular", "number": 1, "held_on": "2026-10-15"}).json()

    assert [row["full_name"] for row in moved["attendance"] if row["mark"]] == ["Hon. Cruz"]


def test_sb_members_can_read_sessions_but_not_change_them(client, council_term):
    term, _ = council_term
    session = new_session(client, headers_for(client, "admin"), term).json()
    member = headers_for(client, "member")

    assert client.get(f"/council/sessions/{session['id']}", headers=member).status_code == 200
    assert new_session(client, member, term).status_code == 403
    assert set_status(client, member, session, "Scheduled").status_code == 403


def test_ordinals():
    assert [council_sessions.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101, 111)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st", "111th"]
