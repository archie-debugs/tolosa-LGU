from datetime import date

import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft
import pytest

from frontend.admin.tracking_ui import due_status

TODAY = date(2026, 10, 20)


@pytest.mark.parametrize("due, expected", [
    ("2026-10-18", ("Overdue · 2 days", "overdue")),
    ("2026-10-19", ("Overdue · 1 day", "overdue")),
    ("2026-10-20", ("Due today", "soon")),
    ("2026-10-21", ("Due tomorrow", "soon")),
    ("2026-10-23", ("Due in 3 days", "soon")),
    ("2026-10-24", ("Due Oct 24", "later")),
    ("2027-01-05", ("Due Jan 05, 2027", "later")),
])
def test_due_status_wording(due, expected):
    assert due_status(due, TODAY) == expected


@pytest.mark.parametrize("due", [None, "", "not a date"])
def test_no_due_status_without_a_date(due):
    assert due_status(due, TODAY) is None


def test_details_header_shows_the_due_chip():
    from frontend.admin.tracking_ui import TrackingWidgets

    class Page:
        theme_mode = ft.ThemeMode.LIGHT

    chip = TrackingWidgets(Page()).due_chip({"due_date": "2026-10-19"}, today=TODAY)
    assert chip.content.value == "Overdue · 1 day"
    assert TrackingWidgets(Page()).due_chip({"due_date": "2026-10-19", "archived": True}, today=TODAY) is None
