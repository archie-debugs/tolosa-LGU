import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash, verify_password
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        treasury = models.Office(name="Treasury Office", office_code="TRE")
        db.add(treasury)
        db.flush()
        db.add_all([
            models.User(username="ana", full_name="Ana Bautista", email="ana@example.com",
                        hashed_password=get_password_hash("pw123456"), role="Employee",
                        permissions="['view_documents']", status="Active", is_active=True, office_id=treasury.id),
            models.User(username="admin", hashed_password=get_password_hash("pw123456"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True),
        ])
        db.commit()
    return TestClient(main.app)


def login(client, username="ana", password="pw123456"):
    return client.post("/auth/login", data={"username": username, "password": password})


def headers_for(client, username="ana", password="pw123456"):
    response = login(client, username, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def change_password(client, headers, current="pw123456", new="newpass99", confirm=None):
    return client.post("/auth/me/password", headers=headers, json={
        "current_password": current, "new_password": new, "confirm_password": new if confirm is None else confirm,
    })


def test_me_returns_the_signed_in_account_with_its_office(client):
    response = client.get("/auth/me", headers=headers_for(client))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["username"] == "ana"
    assert body["full_name"] == "Ana Bautista"
    assert body["email"] == "ana@example.com"
    assert body["role"] == "Employee"
    assert body["office"] == "Treasury Office"
    assert body["status"] == "Active"
    assert "hashed_password" not in body


def test_me_without_an_office_or_full_name(client):
    body = client.get("/auth/me", headers=headers_for(client, "admin")).json()

    assert body["office"] is None
    assert body["full_name"] is None
    assert body["role"] == "Super Administrator"


def test_me_requires_a_signed_in_user(client):
    assert client.get("/auth/me").status_code == 401


def test_change_password_replaces_the_password_and_audits_without_plaintext(client):
    response = change_password(client, headers_for(client))

    assert response.status_code == 200, response.text
    assert "newpass99" not in response.text
    assert login(client).status_code == 401
    assert login(client, password="newpass99").status_code == 200
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(username="ana").one()
        assert verify_password("newpass99", user.hashed_password)
        audit = db.query(models.AuditLog).filter_by(action="PASSWORD_CHANGED").one()
        assert audit.actor == "ana"
        assert "newpass99" not in (audit.details or "") and "pw123456" not in (audit.details or "")


def test_change_password_rejects_a_wrong_current_password(client):
    response = change_password(client, headers_for(client), current="not-it")

    assert response.status_code == 400
    assert response.json()["detail"] == "Your current password is incorrect."
    assert login(client).status_code == 200


@pytest.mark.parametrize("new, confirm, message", [
    ("newpass99", "different", "The new passwords do not match."),
    ("short", "short", "Password must be at least 8 characters long"),
    ("        ", "        ", "Password cannot be blank"),
    ("pw123456", "pw123456", "Choose a password different from your current one."),
])
def test_change_password_validates_the_new_password(client, new, confirm, message):
    response = change_password(client, headers_for(client), new=new, confirm=confirm)

    assert response.status_code == 400
    assert response.json()["detail"] == message
    assert login(client).status_code == 200


def test_change_password_signs_out_other_sessions_but_keeps_this_one(client):
    this_session = headers_for(client)
    other_session = headers_for(client)

    assert change_password(client, this_session).status_code == 200

    assert client.get("/auth/me", headers=this_session).status_code == 200
    assert client.get("/auth/me", headers=other_session).status_code == 401


def test_change_password_requires_a_signed_in_user(client):
    assert change_password(client, {}).status_code == 401


def update_me(client, headers, **payload):
    return client.put("/auth/me", headers=headers, json=payload)


def test_update_me_changes_your_own_name_and_email_and_audits_it(client):
    response = update_me(client, headers_for(client), full_name="  Ana B. Reyes ", email="ana.reyes@example.com")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["full_name"], body["email"], body["office"]) == ("Ana B. Reyes", "ana.reyes@example.com", "Treasury Office")
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(username="ana").one()
        assert (user.full_name, user.email, user.role) == ("Ana B. Reyes", "ana.reyes@example.com", "Employee")
        audit = db.query(models.AuditLog).filter_by(action="PROFILE_UPDATED").one()
        assert audit.actor == "ana"


@pytest.mark.parametrize("payload, message", [
    ({"full_name": "  ", "email": "ana@example.com"}, "Full name is required."),
    ({"full_name": "Ana", "email": ""}, "Email is required."),
    ({"full_name": "Ana", "email": "not-an-email"}, "Enter a valid email address."),
])
def test_update_me_validates_name_and_email(client, payload, message):
    response = update_me(client, headers_for(client), **payload)

    assert response.status_code == 400
    assert response.json()["detail"] == message


def test_update_me_cannot_change_role_office_or_username(client):
    response = update_me(client, headers_for(client), full_name="Ana", email="ana@example.com",
                         role="Super Administrator", username="boss", office_id=None, permissions=["*"])

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(full_name="Ana").one()
        assert (user.username, user.role, user.office_id is not None) == ("ana", "Employee", True)


def test_update_me_requires_a_signed_in_user(client):
    assert update_me(client, {}, full_name="Ana", email="ana@example.com").status_code == 401
