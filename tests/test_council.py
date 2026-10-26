from datetime import date

import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.database import SessionLocal, engine
from Backends.backend.routes import council
from tests.test_settings_pages import add_user, headers_for, reset_db

models.Base.metadata.create_all(bind=engine)

TODAY = date(2026, 10, 22)
TERM = {"name": "13th Sangguniang Bayan", "starts_on": "2025-07-01", "ends_on": "2028-06-30"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(council, "lgu_today", lambda: TODAY)
    reset_db()
    add_user("admin", "Super Administrator", ["*"])
    add_user("clerk", "Employee", ["view_documents", "manage_members_and_committees"])
    add_user("reader", "Employee", ["view_documents"])
    add_user("member", "SB Member", ["view_documents", "manage_members_and_committees"])
    return TestClient(main.app)


def make_term(client, headers, **overrides):
    response = client.post("/council/terms", headers=headers, json={**TERM, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


def add_member(client, headers, term_id, full_name, position="Regular Member", **extra):
    return client.post("/council/members", headers=headers,
                       json={"term_id": term_id, "full_name": full_name, "position": position, **extra})


def audit_actions():
    with SessionLocal() as db:
        actions = [row.action for row in db.query(models.AuditLog).order_by(models.AuditLog.id).all()]
    return [action for action in actions if action.startswith(("COUNCIL_", "COMMITTEE_"))]


def test_the_secretariat_keeps_the_roster_and_everyone_who_views_documents_can_read_it(client):
    clerk = headers_for(client, "clerk")
    term = make_term(client, clerk)
    assert term["is_current"] is True

    assert add_member(client, clerk, term["id"], "Hon. Maria Santos", "Vice Mayor").status_code == 200
    assert add_member(client, clerk, term["id"], "Hon. Jose Cruz").status_code == 200

    for username in ("reader", "member"):
        members = client.get("/council/members", headers=headers_for(client, username)).json()
        assert [(m["full_name"], m["position"]) for m in members] == [
            ("Hon. Maria Santos", "Vice Mayor"), ("Hon. Jose Cruz", "Regular Member"),
        ]
    assert audit_actions()[-3:] == ["COUNCIL_TERM_CREATED", "COUNCIL_MEMBER_ADDED", "COUNCIL_MEMBER_ADDED"]


def test_only_the_manage_permission_can_change_the_roster_and_sb_members_never_can(client):
    term = make_term(client, headers_for(client, "admin"))
    for username in ("reader", "member"):
        headers = headers_for(client, username)
        assert client.post("/council/terms", headers=headers, json={**TERM, "name": "Other"}).status_code == 403
        assert add_member(client, headers, term["id"], "Someone").status_code == 403
        assert client.post("/council/committees", headers=headers, json={"name": "Committee on Health"}).status_code == 403
    assert client.get("/council/members").status_code in (401, 403)


def test_terms_cannot_overlap_or_end_before_they_start(client):
    admin = headers_for(client, "admin")
    make_term(client, admin)

    overlap = client.post("/council/terms", headers=admin, json={"name": "14th", "starts_on": "2028-06-01", "ends_on": "2031-06-30"})
    backwards = client.post("/council/terms", headers=admin, json={"name": "14th", "starts_on": "2031-06-30", "ends_on": "2028-07-01"})
    next_term = client.post("/council/terms", headers=admin, json={"name": "14th", "starts_on": "2028-07-01", "ends_on": "2031-06-30"})

    assert overlap.status_code == 409 and "13th Sangguniang Bayan" in overlap.json()["detail"]
    assert backwards.status_code == 400
    assert next_term.status_code == 200 and next_term.json()["is_current"] is False


def test_single_seat_positions_have_one_holder_until_they_leave(client):
    admin = headers_for(client, "admin")
    term = make_term(client, admin)
    first = add_member(client, admin, term["id"], "Hon. Ana Reyes", "SK Federation President").json()

    assert add_member(client, admin, term["id"], "Hon. Ben Lim", "SK Federation President").status_code == 409

    left = client.put(f"/council/members/{first['id']}", headers=admin,
                      json={"full_name": first["full_name"], "position": first["position"], "left_on": "2026-09-30"})
    assert left.status_code == 200 and left.json()["is_active"] is False
    assert add_member(client, admin, term["id"], "Hon. Ben Lim", "SK Federation President").status_code == 200

    members = client.get("/council/members", headers=admin).json()
    assert [(m["full_name"], m["is_active"]) for m in members] == [("Hon. Ben Lim", True), ("Hon. Ana Reyes", False)]


def test_a_member_can_be_linked_to_one_login_and_positions_are_checked(client):
    admin = headers_for(client, "admin")
    term = make_term(client, admin)
    with SessionLocal() as db:
        member_user_id = db.query(models.User.id).filter(models.User.username == "member").scalar()

    linked = add_member(client, admin, term["id"], "Hon. Jose Cruz", user_id=member_user_id)
    assert linked.status_code == 200 and linked.json()["username"] == "member"
    assert add_member(client, admin, term["id"], "Hon. Other", user_id=member_user_id).status_code == 409
    assert add_member(client, admin, term["id"], "Hon. Other", user_id=99999).status_code == 404
    assert add_member(client, admin, term["id"], "Hon. Other", "Councilor").status_code == 400


def test_there_is_no_way_to_delete_members_terms_or_committees(client):
    admin = headers_for(client, "admin")
    term = make_term(client, admin)
    member = add_member(client, admin, term["id"], "Hon. Jose Cruz").json()
    committee = client.post("/council/committees", headers=admin, json={"name": "Committee on Health"}).json()

    for path in (f"/council/terms/{term['id']}", f"/council/members/{member['id']}", f"/council/committees/{committee['id']}"):
        assert client.delete(path, headers=admin).status_code == 405


def test_committees_have_a_current_member_as_chair_and_are_deactivated_not_deleted(client):
    clerk = headers_for(client, "clerk")
    term = make_term(client, clerk)
    chair = add_member(client, clerk, term["id"], "Hon. Jose Cruz").json()

    created = client.post("/council/committees", headers=clerk, json={"name": "Committee on Health", "chair_member_id": chair["id"]})
    assert created.status_code == 200 and created.json()["chair_name"] == "Hon. Jose Cruz"
    assert client.post("/council/committees", headers=clerk, json={"name": "committee on health"}).status_code == 409

    committee = created.json()
    deactivated = client.put(f"/council/committees/{committee['id']}", headers=clerk,
                             json={"name": committee["name"], "chair_member_id": chair["id"], "is_active": False})
    assert deactivated.status_code == 200 and deactivated.json()["is_active"] is False
    assert client.get("/council/committees?active_only=true", headers=clerk).json() == []
    assert [c["name"] for c in client.get("/council/committees", headers=clerk).json()] == ["Committee on Health"]
    assert audit_actions()[-2:] == ["COMMITTEE_CREATED", "COMMITTEE_UPDATED"]


def test_a_member_who_has_left_cannot_become_a_chair(client):
    admin = headers_for(client, "admin")
    term = make_term(client, admin)
    gone = add_member(client, admin, term["id"], "Hon. Former").json()
    client.put(f"/council/members/{gone['id']}", headers=admin,
               json={"full_name": gone["full_name"], "position": gone["position"], "left_on": "2026-01-15"})

    response = client.post("/council/committees", headers=admin, json={"name": "Committee on Finance", "chair_member_id": gone["id"]})

    assert response.status_code == 400


def test_members_default_to_the_current_term(client):
    admin = headers_for(client, "admin")
    old = make_term(client, admin, name="12th Sangguniang Bayan", starts_on="2022-07-01", ends_on="2025-06-30")
    current = make_term(client, admin)
    add_member(client, admin, old["id"], "Hon. Past Member")
    add_member(client, admin, current["id"], "Hon. Present Member")

    assert [m["full_name"] for m in client.get("/council/members", headers=admin).json()] == ["Hon. Present Member"]
    assert [m["full_name"] for m in client.get(f"/council/members?term_id={old['id']}", headers=admin).json()] == ["Hon. Past Member"]


def test_sb_member_accounts_keep_their_position_for_filling_in_the_roster(client):
    admin = headers_for(client, "admin")
    account = {"username": "santos", "password": "pw123", "full_name": "Hon. Maria Santos", "email": "santos@example.com"}

    created = client.post("/auth/register", headers=admin, json={**account, "role": "SB Member", "sb_position": "Vice Mayor"})
    assert created.status_code == 200, created.text
    assert created.json()["sb_position"] == "Vice Mayor"
    bad = client.post("/auth/register", headers=admin, json={**account, "username": "x", "role": "SB Member", "sb_position": "Councilor"})
    assert bad.status_code == 400
    employee = client.post("/auth/register", headers=admin, json={**account, "username": "staff", "role": "Employee", "sb_position": "IPMR"})
    assert employee.status_code == 200 and employee.json()["sb_position"] is None

    accounts = client.get("/council/member-accounts", headers=headers_for(client, "clerk")).json()
    assert [(a["full_name"], a["sb_position"]) for a in accounts] == [("Hon. Maria Santos", "Vice Mayor"), ("member", None)]
    for username in ("reader", "member"):
        assert client.get("/council/member-accounts", headers=headers_for(client, username)).status_code == 403

    edit = {"full_name": "Hon. Maria Santos", "username": "santos", "email": "santos@example.com",
            "role": "SB Member", "status": "Active", "permissions": ["view_documents"]}
    user_id = created.json()["id"]
    assert client.put(f"/auth/users/{user_id}", headers=admin, json=edit).status_code == 200  # no sb_position sent: kept
    assert client.put(f"/auth/users/{user_id}", headers=admin, json={**edit, "sb_position": "Regular Member"}).status_code == 200
    users = {user["username"]: user for user in client.get("/auth/users", headers=admin).json()}
    assert users["santos"]["sb_position"] == "Regular Member"
