"""The phone's own Back (an edge swipe or its ◁ button) and pull-down-to-refresh.

In a browser the phone's Back is the browser's Back. The workspace swaps screens in place, so
without addresses of its own Back left the app, or went to an earlier address (`/`) and drew the
public homepage over a signed-in screen. The workspace now gives each screen an address
(`/app/<screen>`) and handles Back itself: an open dialog or the menu closes first, then the
screen before; on the first screen Back stays put.

Flet has one route-change handler per page: the public router (frontend/app.py) and the
workspace shell both hand theirs to `install`, and the workspace's sees each change first.
"""
import re
import time

import flet as ft

APP_PREFIX = "/app"

# id(page) -> handler. shortcut: kept for the life of the server process (one small entry per
# browser tab ever opened); drop them on disconnect if that ever matters.
_public = {}
_workspace = {}


def slug(label):
    return re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")


def screen_route(label):
    return f"{APP_PREFIX}/{slug(label)}"


def route_screen(route):
    """The screen slug in `/app/<slug>`, or None."""
    match = re.fullmatch(rf"{APP_PREFIX}/([a-z0-9-]+)", (route or "").split("?", 1)[0])
    return match.group(1) if match else None


def set_address(page, route):
    """Show `route` in the address bar (a new history entry) without it counting as a Back."""
    if getattr(page, "route", None) == route or not hasattr(page, "go"):
        return
    try:
        page.go(route, skip_route_change_event=True)
    except TypeError:
        page.go(route)  # a Flet without that option: the change comes back to the workspace, which keeps its screen


def _route_changed(page):
    handler = _workspace.get(id(page))
    if handler and handler(page.route):
        return
    public = _public.get(id(page))
    if public:
        public()


def install(page, *, public=None, workspace=None):
    """Route changes go to `workspace(route) -> handled?` first, then to `public()`."""
    if public is not None:
        _public[id(page)] = public
    if workspace is not None:
        _workspace[id(page)] = workspace
    page.on_route_change = lambda _=None: _route_changed(page)


def close_open_dialog(page):
    """Close the dialog on top, if one is open; True when one was."""
    candidates = [getattr(page, "dialog", None), *reversed(list(getattr(page, "overlay", None) or []))]
    for control in candidates:
        if control is not None and getattr(control, "open", False) and hasattr(control, "modal"):
            control.open = False
            page.update()
            return True
    return False


def pull_to_refresh(content, on_refresh, distance=70):
    """Wrap `content` (a bar that doesn't scroll) so pulling it down `distance` px calls `on_refresh()`."""
    pulled = {"y": 0.0}

    def update(e):
        pulled["y"] += getattr(e, "delta_y", 0) or 0

    def end(_):
        if pulled["y"] >= distance:
            on_refresh()
        pulled["y"] = 0.0

    return ft.GestureDetector(content=content, on_vertical_drag_update=update, on_vertical_drag_end=end,
                              on_vertical_drag_start=lambda _: pulled.update(y=0.0))


class PullToRefresh:
    """Pull-to-refresh for a signed-in screen, with the spinner other phone apps show.

    A white circle slides down with the finger and fills as it is pulled; let go past `distance`
    and it spins at the top while `on_refresh()` reloads the screen, then slides away. Pulling back
    up before letting go cancels. The pull reaches it three ways:
    - `on_scroll` (a scrolling Column's handler): pulling past the top of a screen that scrolls.
      Android reports this as overscroll; an iPhone bounces the content below the top (pixels < 0).
    - `wrap(control)`: a drag on something that doesn't scroll (a short screen, the top bar).
    """
    HIDDEN, REST, SIZE = -48, 12, 40  # spinner top (px) out of sight, while spinning; its size
    MIN_SPIN = 0.6  # seconds: a refresh too quick to see still shows the spin

    def __init__(self, page, on_refresh, distance=70):
        self.page, self.on_refresh, self.distance = page, on_refresh, distance
        self.pulled, self.armed, self.busy = 0.0, False, False
        self.ring = ft.ProgressRing(value=0, width=22, height=22, stroke_width=2.5)
        self.spinner = ft.Container(
            content=self.ring, width=self.SIZE, height=self.SIZE, padding=9, border_radius=self.SIZE / 2,
            bgcolor="white", shadow=ft.BoxShadow(blur_radius=6, color="#40000000"), opacity=0,
        )
        # Lay this over the content (the last control of an ft.Stack); outside the circle taps pass through.
        self.indicator = ft.Row([self.spinner], alignment=ft.MainAxisAlignment.CENTER,
                                top=self.HIDDEN, left=0, right=0, animate_position=150)

    def _show(self):
        reach = min(self.pulled, self.distance * 1.5)
        self.indicator.top = self.HIDDEN + reach * (self.REST - self.HIDDEN + 10) / self.distance
        self.spinner.opacity = min(1.0, reach / self.distance)
        self.ring.value = min(1.0, reach / self.distance)
        self.page.update()

    def drag(self, dy):
        if self.busy or not (self.pulled or dy > 0):
            return
        self.pulled = max(0.0, self.pulled + dy)
        self._show()

    def release(self):
        if self.busy:
            return
        if self.pulled >= self.distance or self.armed:
            self._refresh()
        elif self.pulled:
            self._hide()

    def _refresh(self):
        self.busy, started = True, time.monotonic()
        self.indicator.top, self.spinner.opacity, self.ring.value = self.REST, 1.0, None  # None: spins
        self.page.update()
        try:
            self.on_refresh()
        finally:
            time.sleep(max(0.0, self.MIN_SPIN - (time.monotonic() - started)))
            self.busy = False
            self._hide()

    def _hide(self):
        self.pulled, self.armed = 0.0, False
        self.indicator.top, self.spinner.opacity, self.ring.value = self.HIDDEN, 0, 0
        self.page.update()

    def on_scroll(self, e):
        kind, pixels = getattr(e, "event_type", None), getattr(e, "pixels", None) or 0.0
        top = getattr(e, "min_scroll_extent", None) or 0.0
        if kind == "over" and (getattr(e, "overscroll", None) or 0) < 0 and pixels <= top:
            self.drag(-e.overscroll)  # Android: pulled past the top
        elif kind == "update" and pixels < top and not self.busy:
            # iPhone: the content bounces below the top. Once far enough it counts, as on iOS,
            # since the bounce back also arrives as updates.
            self.pulled = top - pixels
            self.armed = self.armed or self.pulled >= self.distance
            self._show()
        elif kind == "update" and self.pulled and (getattr(e, "scroll_delta", None) or 0) > 0:
            self.drag(-e.scroll_delta)  # Android: pushed back up before letting go
        elif kind == "end":
            self.release()

    def wrap(self, control, when=lambda: True):
        """Pulling `control` down refreshes too (only while `when()`; it needs a bgcolor to feel drags)."""
        def start(_):
            if when() and not self.busy:
                self.pulled = 0.0

        def update(e):
            if when():
                self.drag(getattr(e, "delta_y", 0) or 0)

        return ft.GestureDetector(content=control, on_vertical_drag_start=start, on_vertical_drag_update=update,
                                  on_vertical_drag_end=lambda _: self.release(), expand=getattr(control, "expand", None))
