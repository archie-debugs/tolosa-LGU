from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal

import frontend.admin.app as admin_app

from tests.test_session_revocation import AppPage, BackendSession, login
from tests.test_account_menu_ui import texts


def reset_db(clerk_permissions):
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        for username, role, permissions in (("admin", "Super Administrator", ["*"]), ("clerk", "Employee", clerk_permissions)):
            db.add(models.User(username=username, hashed_password=get_password_hash("pw123"), role=role,
                               permissions=str(permissions), status="Active", is_active=True))
        db.commit()


def shown(monkeypatch, username):
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    page = AppPage()
    admin_app.main(page, session=login(TestClient(main.app), username))
    return [t for control in page.controls for t in texts(control)]


def test_an_employee_sees_employee_panel_and_no_users_cards_without_view_users(monkeypatch):
    reset_db(["view_dashboard", "view_documents"])
    words = shown(monkeypatch, "clerk")

    assert "Employee Panel" in words and "Admin Panel" not in words
    assert "Total Documents" in words
    assert "Total Users" not in words


def test_an_employee_with_view_users_sees_the_users_cards(monkeypatch):
    reset_db(["view_dashboard", "view_documents", "view_users"])
    assert "Total Users" in shown(monkeypatch, "clerk")


def test_a_super_administrator_keeps_admin_panel_and_the_users_cards(monkeypatch):
    reset_db([])
    words = shown(monkeypatch, "admin")

    assert "Admin Panel" in words and "Total Users" in words
