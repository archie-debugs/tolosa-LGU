import json

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.database import SessionLocal

import frontend.admin.app as admin_app  # also applies the flet compatibility shims

from tests.test_session_revocation import AppPage, BackendSession, login, on_login_screen, reset_db, sidebar_tile


def page_with_saved_sign_in(username, app_run):
    """A browser that signed in as `username` while the app run `app_run` was serving it."""
    tokens = login(TestClient(main.app), username)
    page = AppPage()
    for key, value in {
        "sb_access_token": tokens["access_token"],
        "sb_refresh_token": tokens["refresh_token"],
        "sb_current_user": username,
        "sb_current_user_role": "Employee",
        "sb_current_user_permissions": json.dumps(["view_documents", "search_documents"]),
        "sb_app_run": app_run,
    }.items():
        if value is not None:
            page.client_storage.set(key, value)
    return page


def open_sessions(username):
    with SessionLocal() as db:
        return db.query(models.UserSession).join(models.User).filter(
            models.User.username == username, models.UserSession.revoked_at.is_(None)).count()


def test_reloading_during_the_same_run_keeps_the_sign_in(monkeypatch):
    reset_db()
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    page = page_with_saved_sign_in("clerk", admin_app.APP_RUN_ID)

    admin_app.main(page)

    assert not on_login_screen(page)
    sidebar_tile(page, "Documents")


def test_a_sign_in_from_before_a_restart_goes_through_login(monkeypatch):
    reset_db()
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    page = page_with_saved_sign_in("clerk", "an-earlier-run")
    assert open_sessions("clerk") == 1

    admin_app.main(page)

    assert on_login_screen(page)
    assert page.client_storage.get("sb_access_token") is None
    assert page.client_storage.get("sb_app_run") is None
    assert open_sessions("clerk") == 0  # the old session is signed out, not left active


def test_a_sign_in_saved_before_this_change_goes_through_login(monkeypatch):
    reset_db()
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    page = page_with_saved_sign_in("clerk", None)

    admin_app.main(page)

    assert on_login_screen(page)
