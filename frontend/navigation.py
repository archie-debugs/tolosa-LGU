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
