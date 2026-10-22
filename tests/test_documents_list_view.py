import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.documents import build_documents_view

LONG_TITLE = "Request Letter from the Department of Health thru Secretary Teodoro Herbosa for the Construction of a Second Level Hospital"
ITEM = {
    "id": 1, "tracking_number": "DOC-000001", "title": LONG_TITLE, "document_type": "Request Letter", "assigned_to": "SB Secretary",
    "action_required": "For Agenda", "status": "Approved", "remarks": "Approved by LCE 12/10/2024", "current_office": "SB Office",
    "archived_by": "admin", "archived_at": "2026-10-20T08:00:00+00:00",
}


class DummyPage:
    def __init__(self, width=1600):
        self.theme_mode = None
        self.width = width

    def update(self, *args):
        pass


def api(method, path, **kwargs):
    return {"items": [ITEM], "total": 1, "total_pages": 1}


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", None) or []:
        yield from walk(child)
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)


def build(archived=False, width=1600):
    view, _ = build_documents_view(
        DummyPage(width), api, lambda content, **_: ft.Container(content), normalize=lambda item: dict(item),
        selection=set(), loaded=[], archived=archived,
    )
    return view


def texts(view):
    return [c.value for c in walk(view) if isinstance(c, ft.Text) and c.value]


def test_both_lists_show_the_tracking_sheet_columns():
    for archived in (False, True):
        shown = texts(build(archived=archived))
        for header in ("TYPE", "REFERRED TO", "ACTION", "STATUS", "REMARKS"):
            assert header in shown
        for value in ("Request Letter", "SB Secretary", "For Agenda", "Approved", "Approved by LCE 12/10/2024"):
            assert value in shown


def test_the_title_takes_one_line_and_shows_whole_on_hover():
    title = next(c for c in walk(build()) if isinstance(c, ft.Text) and c.value == LONG_TITLE)

    assert (title.max_lines, title.overflow, title.tooltip) == (1, ft.TextOverflow.ELLIPSIS, LONG_TITLE)


def test_the_table_scrolls_sideways_in_a_narrow_window():
    narrow = next(c for c in walk(build(width=1000)) if isinstance(c, ft.Row) and c.scroll == ft.ScrollMode.AUTO)
    table = narrow.controls[0]

    assert table.width > 1000 - 370
    wide = next(c for c in walk(build(width=2000)) if isinstance(c, ft.Row) and c.scroll == ft.ScrollMode.AUTO)
    assert wide.controls[0].width == 2000 - 370
