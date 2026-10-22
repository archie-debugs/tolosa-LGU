from fastapi.testclient import TestClient

import Backends.backend.main as main
import frontend.admin.app as admin_app  # also applies the flet compatibility shims
import flet as ft

from frontend.admin.announcements import build_announcements_view
from tests.test_account_menu_ui import DummyPage, click, walk
from tests.test_session_revocation import AppPage, BackendSession, login, reset_db, sidebar_tile
from tests.test_settings_pages import FakeApi, buttons, surface_card, words


class AnnouncementsApi:
    """Returns stored announcements and records what Save sends."""

    def __init__(self, announcements):
        self.announcements = announcements
        self.saved = []

    def __call__(self, method, path, **kwargs):
        if method == "PUT" and path == "/system-settings":
            self.saved.append(kwargs["json"]["settings"])
            return {}
        if path == "/system-settings":
            return {"settings": {"homepage_announcements": self.announcements}}
        return {}


def announcements_view(api):
    return build_announcements_view(DummyPage(), surface_card, api)


def announcement_fields(view):
    return [c for c in walk(view) if isinstance(c, ft.TextField) and c.label in ("Category", "Title", "Date", "Details (optional)")]


def icon_buttons(view, tooltip):
    return [c for c in walk(view) if isinstance(c, ft.IconButton) and c.tooltip == tooltip]


def test_edit_reorder_and_save_announcements():
    api = AnnouncementsApi([
        {"category": "Public notice", "title": "First", "date": "", "details": ""},
        {"category": "Update", "title": "Second", "date": "Oct 27", "details": "More"},
    ])
    view = announcements_view(api)
    assert [f.value for f in announcement_fields(view) if f.label == "Title"] == ["First", "Second"]

    icon_buttons(view, "Move down")[0].on_click(None)
    buttons(view, "Add announcement")[0].on_click(None)
    titles = [f for f in announcement_fields(view) if f.label == "Title"]
    titles[2].value = "  Third  "
    icon_buttons(view, "Remove")[0].on_click(None)  # removes "Second", now first
    buttons(view, "Save announcements")[0].on_click(None)

    assert api.saved == [{"homepage_announcements": [
        {"category": "Public notice", "title": "First", "date": "", "details": ""},
        {"category": "", "title": "Third", "date": "", "details": ""},
    ]}]
    assert "Announcements saved. The homepage shows them the next time it opens." in words(view)


def test_announcements_without_a_title_are_not_saved():
    api = AnnouncementsApi([])
    view = announcements_view(api)
    assert "No announcements. The homepage will say there are none right now." in words(view)

    buttons(view, "Add announcement")[0].on_click(None)
    buttons(view, "Save announcements")[0].on_click(None)

    assert api.saved == []
    assert "Add a title to announcement 1." in words(view)


def test_announcements_cannot_be_saved_when_they_failed_to_load():
    view = announcements_view(FakeApi(fail={"/system-settings"}))
    assert buttons(view, "Save announcements")[0].disabled
    assert buttons(view, "Add announcement")[0].disabled


def test_add_announcement_stops_at_the_limit():
    view = announcements_view(AnnouncementsApi([{"title": f"Item {n}"} for n in range(9)]))
    add = buttons(view, "Add announcement")[0]
    assert not add.disabled
    add.on_click(None)
    assert add.disabled



def test_super_admin_opens_announcements_from_the_sidebar_and_saves_to_the_homepage(monkeypatch):
    reset_db()
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    client = TestClient(main.app)
    page = AppPage()
    admin_app.main(page, session={**login(client, "admin"), "username": "admin", "role": "Super Administrator", "permissions": ["*"]})

    click(sidebar_tile(page, "Announcements"))
    shown = [c for control in page.controls for c in walk(control)]
    next(c for c in shown if isinstance(c, ft.IconButton) and c.tooltip == "Remove").on_click(None)
    next(c for c in shown if isinstance(c, ft.OutlinedButton) and c.text == "Add announcement").on_click(None)
    shown = [c for control in page.controls for c in walk(control)]
    [c for c in shown if isinstance(c, ft.TextField) and c.label == "Title"][-1].value = "Regular session on Monday"
    next(c for c in shown if isinstance(c, ft.ElevatedButton) and c.text == "Save announcements").on_click(None)

    titles = [item["title"] for item in client.get("/public/announcements").json()["announcements"]]
    assert titles == ["Official records and updates", "Regular session on Monday"]


def test_employees_do_not_get_the_announcements_page(monkeypatch):
    reset_db()
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    page = AppPage()
    admin_app.main(page, session=login(TestClient(main.app), "clerk"))
    sidebar_tile(page, "Documents")
    try:
        sidebar_tile(page, "Announcements")
    except StopIteration:
        return
    raise AssertionError("an Employee sees the Announcements page")
