import flet as ft

import frontend.Frontend_Homepage.page as homepage
from frontend.Frontend_Homepage.page import build_homepage_view


def collect_controls(control):
    found = [control]
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        found.extend(collect_controls(content))
    for child in getattr(control, "controls", None) or []:
        found.extend(collect_controls(child))
    return found


def test_every_homepage_button_has_a_click_handler():
    buttons = [
        control
        for control in collect_controls(build_homepage_view(None))
        if isinstance(control, (ft.TextButton, ft.ElevatedButton, ft.IconButton))
    ]
    assert buttons
    dead = [getattr(button, "text", None) or getattr(button, "tooltip", None) for button in buttons if button.on_click is None]
    assert dead == []


def test_homepage_borders_use_border_sides():
    for control in collect_controls(build_homepage_view(None)):
        border = getattr(control, "border", None)
        if border is None:
            continue
        for side in (border.top, border.right, border.bottom, border.left):
            assert side is None or isinstance(side, ft.BorderSide)


def homepage_words(monkeypatch, announcements):
    monkeypatch.setattr(homepage, "load_homepage_announcements", lambda: announcements)
    return [c.value for c in collect_controls(build_homepage_view(None)) if isinstance(c, ft.Text)]


def test_homepage_shows_the_saved_announcements(monkeypatch):
    shown = homepage_words(monkeypatch, [
        {"category": "Public notice", "title": "Regular session on Monday", "date": "Oct 27, 2026", "details": "Session hall, 9:00 AM"},
    ])
    for text in ("PUBLIC NOTICE", "Regular session on Monday", "Oct 27, 2026", "Session hall, 9:00 AM"):
        assert text in shown


def test_homepage_says_when_there_are_no_announcements(monkeypatch):
    assert "There are no announcements right now." in homepage_words(monkeypatch, [])


def test_homepage_falls_back_to_default_announcements_when_the_backend_is_down(monkeypatch):
    def refuse(*args, **kwargs):
        raise homepage.requests.ConnectionError("backend down")

    monkeypatch.setattr(homepage.requests, "get", refuse)
    assert homepage.load_homepage_announcements() == homepage.DEFAULT_ANNOUNCEMENTS

