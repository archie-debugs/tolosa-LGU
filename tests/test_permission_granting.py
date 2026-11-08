"""Who may give which permissions when creating or editing an account, and what is checked."""

import ast

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

ACCOUNT = {"password": "longenough", "full_name": "New Person", "email": "new@example.com", "role": "Employee"}


def setup():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        office = models.Office(name="Records", office_code="REC")
        db.add(office)
        for username, permissions in (
            ("admin", ["*"]),
            ("hr", ["create_users"]),
            ("manager", ["view_users", "create_users", "edit_users", "manage_permissions", "view_documents"]),
        ):
            db.add(models.User(username=username, hashed_password=get_password_hash("pw123"), status="Active", is_active=True,
                               role="Super Administrator" if username == "admin" else "Employee", permissions=str(permissions)))
        db.commit()
        return office.id


def headers(client, username):
    token = client.post("/auth/login", data={"username": username, "password": "pw123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def saved_permissions(username):
    with SessionLocal() as db:
        return ast.literal_eval(db.query(models.User).filter_by(username=username).one().permissions)


def register(client, who, **fields):
    return client.post("/auth/register", json={**ACCOUNT, **fields}, headers=headers(client, who))


def test_create_users_alone_cannot_give_permissions():
    setup()
    client = TestClient(main.app)

    assert register(client, "hr", username="a", permissions=["*"]).status_code == 400
    assert register(client, "hr", username="b", permissions=["delete_users"]).status_code == 403
    assert register(client, "hr", username="c", permissions=["view_documents"]).status_code == 403
    nothing = register(client, "hr", username="d")
    assert nothing.status_code == 200 and saved_permissions("d") == []


def test_a_manager_gives_only_permissions_they_have():
    setup()
    client = TestClient(main.app)

    assert register(client, "manager", username="a", permissions=["view_documents"]).status_code == 200
    refused = register(client, "manager", username="b", permissions=["view_documents", "delete_users"])
    assert refused.status_code == 403 and "delete_users" in refused.json()["detail"]
    assert register(client, "admin", username="c", permissions=["*"]).status_code == 400


def test_editing_cannot_add_permissions_the_editor_lacks_or_give_everything():
    setup()
    client = TestClient(main.app)
    register(client, "admin", username="target", permissions=["view_documents", "delete_documents"])
    with SessionLocal() as db:
        target_id = db.query(models.User.id).filter_by(username="target").scalar()
    body = {"full_name": "T", "username": "target", "email": "t@example.com", "role": "Employee", "status": "Active"}

    # Keeping a permission the editor lacks is fine; adding one is not.
    assert client.put(f"/auth/users/{target_id}", headers=headers(client, "manager"),
                      json={**body, "permissions": ["view_documents", "delete_documents", "view_users"]}).status_code == 200
    assert client.put(f"/auth/users/{target_id}", headers=headers(client, "manager"),
                      json={**body, "permissions": ["view_documents", "delete_documents", "view_users", "delete_users"]}).status_code == 403
    assert client.put(f"/auth/users/{target_id}", headers=headers(client, "admin"),
                      json={**body, "permissions": ["*"]}).status_code == 400


def test_office_employees_keep_general_permissions_too_when_edited():
    office_id = setup()
    client = TestClient(main.app)
    register(client, "admin", username="clerk", permissions=["register_documents"])
    with SessionLocal() as db:
        clerk_id = db.query(models.User.id).filter_by(username="clerk").scalar()

    response = client.put(f"/auth/users/{clerk_id}", headers=headers(client, "admin"), json={
        "full_name": "C", "username": "clerk", "email": "c@example.com", "role": "Employee", "status": "Active",
        "office_id": office_id, "permissions": ["register_documents", "scan_qr", "pass_office_documents"],
    })

    assert response.status_code == 200, response.text
    assert saved_permissions("clerk") == ["pass_office_documents", "register_documents", "scan_qr"]


def test_new_accounts_need_a_real_email_and_an_eight_character_password():
    setup()
    client = TestClient(main.app)

    assert register(client, "admin", username="a", email="not-an-email").json()["detail"] == "Enter a valid email address."
    assert register(client, "admin", username="b", password="short").status_code == 400
    assert register(client, "admin", username="c").status_code == 200
