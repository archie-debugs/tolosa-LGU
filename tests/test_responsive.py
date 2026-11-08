import time

import frontend.responsive as responsive
import flet as ft


def test_tablet_splits_wait_for_a_desktop():
    assert responsive.stack_below_desktop({"xs": 12, "md": 6}) == {"xs": 12, "lg": 6}
    assert responsive.stack_below_desktop({"xs": 12, "sm": 6, "lg": 4}) == {"xs": 12, "lg": 4}
    assert responsive.stack_below_desktop({"sm": 6}) == {"xs": 12, "lg": 6}
    assert responsive.stack_below_desktop({"xs": 6, "md": 3, "xl": 2}) == {"xs": 6, "lg": 3, "xl": 2}
    # Phone-only and desktop-only layouts, and plain numbers, are left alone.
    for col in ({"xs": 6}, {"xs": 12, "lg": 6}, 4, None):
        assert responsive.stack_below_desktop(col) == col


def test_every_control_gets_the_rule():
    assert ft.Container(col={"xs": 12, "md": 5}).col == {"xs": 12, "lg": 5}
    box = ft.Column()
    box.col = {"sm": 6}
    assert box.col == {"xs": 12, "lg": 6}


class Page:
    def __init__(self, width):
        self.width, self.controls, self.updates = width, [], 0

    def clean(self):
        self.controls = []

    def add(self, control):
        self.controls.append(control)

    def update(self):
        self.updates += 1


def test_a_page_is_redrawn_once_its_width_changes_and_only_while_it_shows():
    page = Page(390)
    view = ft.Column()
    page.add(view)
    rebuilt = []
    responsive.redraw_on_resize(page, view, lambda: rebuilt.append(ft.Column()) or rebuilt[-1], settle=0.01)

    page.on_resize(None)  # same width: nothing to redo
    time.sleep(0.05)
    assert rebuilt == []

    page.width = 844  # phone turned sideways
    for _ in range(3):
        page.on_resize(None)
    time.sleep(0.05)
    assert len(rebuilt) == 1 and page.controls == rebuilt

    page.controls = [ft.Text("login")]  # another screen took over
    page.width = 390
    page.on_resize(None)
    time.sleep(0.05)
    assert len(rebuilt) == 1
