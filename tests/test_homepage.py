import flet as ft

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
