from fastapi.testclient import TestClient

import Backends.backend.main as main
import flet as ft

import frontend.admin.app as admin_app
from frontend import navigation
from tests.test_account_menu_ui import click, texts
from tests.test_employee_panel import reset_db
from tests.test_session_revocation import AppPage, BackendSession, login, sidebar_tile


def test_addresses_and_screens():
    assert navigation.screen_route("Today's Documents") == "/app/today-s-documents"
    assert navigation.route_screen("/app/today-s-documents") == "today-s-documents"
    assert navigation.route_screen("/app") is None and navigation.route_screen("/") is None


def test_set_address_works_with_or_without_flets_quiet_option():
    class Quiet(AppPage):
        def go(self, route, skip_route_change_event=False):
            self.route, self.quiet = route, skip_route_change_event

    quiet, plain = Quiet(), AppPage()
    navigation.set_address(quiet, "/app/documents")
    navigation.set_address(plain, "/app/documents")
    assert (quiet.route, quiet.quiet) == ("/app/documents", True)
    assert plain.route == "/app/documents"


def send(control, event_name, event=None):
    handler = getattr(control, event_name)
    for fn in [handler] if callable(handler) else list(handler._EventHandler__handlers):  # Flet 0.21 wraps them
        fn(event)


def test_a_pull_of_the_bar_refreshes_only_past_the_distance():
    refreshed = []
    bar = navigation.pull_to_refresh(ft.Container(), lambda: refreshed.append(1), distance=70)
    drag = lambda dy: type("Drag", (), {"delta_y": dy})()
    send(bar, "on_vertical_drag_start")
    send(bar, "on_vertical_drag_update", drag(40))
    send(bar, "on_vertical_drag_end")
    assert refreshed == []
    send(bar, "on_vertical_drag_start")
    for _ in range(4):
        send(bar, "on_vertical_drag_update", drag(20))
    send(bar, "on_vertical_drag_end")
    assert refreshed == [1]


def signed_in(monkeypatch):
    reset_db([])
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    page = AppPage()
    admin_app.main(page, session=login(TestClient(main.app), "admin"))
    return page


def shown(page):
    return [t for control in page.controls for t in texts(control)]


def back_to(page, route):
    page.route = route
    page.on_route_change(None)


def test_back_returns_to_the_screen_before_and_stays_on_the_first(monkeypatch):
    page = signed_in(monkeypatch)
    assert page.route == "/app/dashboard"

    click(sidebar_tile(page, "Analytics"))
    assert page.route == "/app/analytics"

    back_to(page, "/app/dashboard")
    assert "Total Documents" in shown(page) and page.route == "/app/dashboard"

    back_to(page, "/app")  # past the first screen: stay on it
    assert page.route == "/app/dashboard" and "Total Documents" in shown(page)

    back_to(page, "/")  # an address from before signing in: never draw the homepage over the workspace
    assert page.route == "/app/dashboard" and "Welcome to the" not in shown(page)


def test_back_closes_an_open_dialog_before_leaving_the_screen(monkeypatch):
    page = signed_in(monkeypatch)
    click(sidebar_tile(page, "Analytics"))
    dialog = ft.AlertDialog(open=True)
    page.overlay.append(dialog)

    back_to(page, "/app/dashboard")

    assert dialog.open is False
    assert page.route == "/app/analytics"


def test_a_reload_reopens_the_screen_in_the_address(monkeypatch):
    reset_db([])
    monkeypatch.setattr(admin_app.requests, "Session", BackendSession)
    page = AppPage()
    page.route = "/app/analytics"
    admin_app.main(page, session=login(TestClient(main.app), "admin"))
    assert page.route == "/app/analytics"
    assert "Document Status" in shown(page) and "Total Documents" not in shown(page)


class Scroll:
    def __init__(self, event_type, pixels=0.0, overscroll=None, scroll_delta=None):
        self.event_type, self.pixels, self.overscroll, self.scroll_delta = event_type, pixels, overscroll, scroll_delta
        self.min_scroll_extent = 0.0


def pull_setup():
    refreshed = []
    pull = navigation.PullToRefresh(AppPage(), lambda: refreshed.append(1), distance=70)
    pull.MIN_SPIN = 0
    return pull, refreshed


def test_android_pull_past_the_top_refreshes_and_pushing_back_cancels():
    pull, refreshed = pull_setup()
    for _ in range(4):
        pull.on_scroll(Scroll("over", overscroll=-20))
    assert pull.ring.value == 1.0 and pull.spinner.opacity == 1.0  # the circle has come down full
    pull.on_scroll(Scroll("end"))
    assert refreshed == [1] and pull.indicator.top == pull.HIDDEN  # spun, then slid away

    for _ in range(4):
        pull.on_scroll(Scroll("over", overscroll=-20))
    pull.on_scroll(Scroll("update", pixels=30, scroll_delta=30))  # pushed back up first
    pull.on_scroll(Scroll("end"))
    assert refreshed == [1]


def test_iphone_bounce_refreshes_once_it_went_far_enough():
    pull, refreshed = pull_setup()
    for pixels in (-20, -50, -80, -40, -5):  # pulled down, then the bounce back
        pull.on_scroll(Scroll("update", pixels=pixels))
    pull.on_scroll(Scroll("end"))
    assert refreshed == [1]

    pull.on_scroll(Scroll("update", pixels=-30))
    pull.on_scroll(Scroll("end"))
    assert refreshed == [1]


def test_plain_scrolling_never_shows_the_circle():
    pull, refreshed = pull_setup()
    for pixels in (40, 120, 60, 0):
        pull.on_scroll(Scroll("update", pixels=pixels, scroll_delta=10))
    pull.on_scroll(Scroll("end"))
    assert refreshed == [] and pull.indicator.top == pull.HIDDEN and pull.spinner.opacity == 0


def test_dragging_a_short_screen_refreshes_only_on_phones():
    pull, refreshed = pull_setup()
    phone = {"on": False}
    wrapped = pull.wrap(ft.Container(), when=lambda: phone["on"])
    drag = lambda dy: type("Drag", (), {"delta_y": dy})()
    for on in (False, True):
        phone["on"] = on
        send(wrapped, "on_vertical_drag_start")
        for _ in range(4):
            send(wrapped, "on_vertical_drag_update", drag(20))
        send(wrapped, "on_vertical_drag_end")
    assert refreshed == [1]
