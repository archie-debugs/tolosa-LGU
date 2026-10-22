import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.council_sessions import build_sessions_view, quorum_text
from tests.test_account_menu_ui import DummyPage, click, clickable
from tests.test_council_page import TERMS, button, dialog, texts, walk
from tests.test_settings_pages import surface_card

QUORUM = {"present": 0, "in_office": 3, "needed": 2, "has_quorum": False, "unmarked": 3}
LISTED = [{"id": 4, "title": "2nd Regular Session", "kind": "Regular", "number": 2, "held_on": "2026-10-20", "status": "Scheduled",
           "quorum": {"present": 1, "in_office": 3, "needed": 2, "has_quorum": False, "unmarked": 0}},
          {"id": 3, "title": "1st Regular Session", "kind": "Regular", "number": 1, "held_on": "2026-10-13", "status": "Held",
           "quorum": {"present": 3, "in_office": 3, "needed": 2, "has_quorum": True, "unmarked": 0}}]


def detail(status="Draft", marks=None, history=None):
    marks = marks or {}
    rows = [{"member_id": member_id, "full_name": name, "position": "Regular Member", "mark": marks.get(member_id),
             "note": None, "history": (history or {}).get(member_id, [])}
            for member_id, name in [(10, "Hon. Santos"), (11, "Hon. Cruz"), (12, "Hon. Lim")]]
    return {"id": 4, "term_id": 2, "term_name": "13th Sangguniang Bayan", "title": "2nd Regular Session", "kind": "Regular",
            "number": 2, "held_on": "2026-10-20", "status": status, "quorum": dict(QUORUM),
            "next_statuses": {"Draft": ["Scheduled", "Held"], "Scheduled": ["Draft", "Held"], "Held": []}[status],
            "attendance": rows}


SECTIONS = [("call_to_order", "Call to order"), ("roll_call", "Roll call"), ("minutes", "Approval of the previous minutes"),
            ("first_reading", "First reading and referral"), ("committee_reports", "Committee reports"),
            ("unfinished", "Unfinished business"), ("second_third", "Business for second and third reading"),
            ("other", "Other matters and communications"), ("adjournment", "Adjournment")]


def business(editable=True, items=None, without_outcome=0):
    items = items or {}
    return {"session_id": 4, "editable": editable, "without_outcome": without_outcome,
            "sections": [{"key": key, "label": label, "items": items.get(key, [])} for key, label in SECTIONS]}


class FakeApi:
    def __init__(self, session=None, business_payload=None):
        self.calls = []
        self.session = session or detail()
        self.business = business_payload or business(editable=self.session["status"] != "Held")

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        if "/business" in path:
            return self.business
        if path == "/council/terms":
            return TERMS
        if path.startswith("/council/sessions?term_id="):
            return {"sessions": LISTED, "next_numbers": {"Regular": 3, "Special": 1}}
        if path == "/council/sessions" and method == "POST":
            return {**detail(), "title": "3rd Regular Session"}
        return self.session


def build(api, can_manage=True):
    page = DummyPage()
    return page, build_sessions_view(page, surface_card, api, can_manage=can_manage)


def save(form, label="Save"):
    next(action for action in form.actions if getattr(action, "text", None) == label or getattr(action, "content", None) == label).on_click(None)


def open_first_session(view):
    click(next(item for item in walk(view) if isinstance(item, ft.Container) and clickable(item)))


def test_the_list_shows_the_current_terms_sessions_with_status_and_quorum():
    api = FakeApi()
    page, view = build(api)
    shown = texts(view)

    assert ("GET", "/council/sessions?term_id=2", None) in api.calls
    assert "2nd Regular Session" in shown and "Scheduled" in shown
    assert "October 20, 2026 · 1 of 3 present · no quorum (2 needed)" in shown
    assert "October 13, 2026 · 3 of 3 present · quorum" in shown


def test_adding_a_session_suggests_the_next_number_and_opens_the_new_draft():
    api = FakeApi()
    page, view = build(api)

    button(view, "Add session").on_click(None)
    form = dialog(page)
    number, held_on = [item for item in walk(form.content) if isinstance(item, ft.TextField)]
    assert number.value == "3"
    held_on.value = "2026-10-27"
    save(form)

    assert ("POST", "/council/sessions", {"kind": "Regular", "number": 3, "held_on": "2026-10-27", "term_id": 2}) in api.calls
    assert form.open is False and "3rd Regular Session" in texts(view)


def test_attendance_is_saved_with_unmarked_members_sent_as_none():
    api = FakeApi()
    page, view = build(api)
    open_first_session(view)

    marks = [item for item in walk(view) if isinstance(item, ft.Dropdown) and item.width == 170]
    marks[0].value = "Present"
    marks[1].value = "On leave"
    button(view, "Save attendance").on_click(None)

    sent = next(call[2]["marks"] for call in api.calls if call[0] == "PUT")
    assert [(row["member_id"], row["mark"]) for row in sent] == [(10, "Present"), (11, "On leave"), (12, None)]


def test_mark_the_rest_present_fills_only_the_unmarked():
    page, view = build(FakeApi(detail(marks={11: "Absent"})))
    open_first_session(view)

    button(view, "Mark the rest present").on_click(None)

    marks = [item.value for item in walk(view) if isinstance(item, ft.Dropdown) and item.width == 170]
    assert marks == ["Present", "Absent", "Present"]


def test_marking_held_warns_about_unmarked_members_and_no_quorum_first():
    api = FakeApi()
    page, view = build(api)
    open_first_session(view)

    button(view, "Mark as held").on_click(None)
    form = dialog(page)
    assert "3 member(s) are not marked." in texts(form.content)
    assert not [call for call in api.calls if call[1].endswith("/status")]
    save(form, "Mark as held")

    assert ("POST", "/council/sessions/4/status", {"status": "Held"}) in api.calls


def test_a_held_session_is_corrected_with_a_reason_and_shows_the_correction():
    history = {11: [{"mark": "Present", "is_correction": True, "note": "Arrived late", "recorded_by": "clerk"},
                    {"mark": "Absent", "is_correction": False, "note": None, "recorded_by": "clerk"}]}
    api = FakeApi(detail("Held", marks={10: "Present", 11: "Present"}, history=history))
    page, view = build(api)
    open_first_session(view)

    assert "Corrected to Present by clerk: Arrived late" in texts(view)
    assert not [item for item in walk(view) if isinstance(item, ft.Dropdown) and item.width == 170]
    next(item for item in walk(view) if isinstance(item, ft.IconButton) and item.tooltip == "Correct").on_click(None)
    form = dialog(page)
    reason = next(item for item in walk(form.content) if isinstance(item, ft.TextField))
    save(form, "Save correction")
    assert form.open is True and not [call for call in api.calls if call[1].endswith("/corrections")]

    reason.value = "Roll call was misread"
    save(form, "Save correction")
    assert ("POST", "/council/sessions/4/attendance/corrections",
            {"member_id": 10, "mark": "Present", "reason": "Roll call was misread"}) in api.calls


def test_readers_get_no_buttons_or_fields():
    page, view = build(FakeApi(), can_manage=False)
    assert not [item for item in walk(view) if isinstance(item, ft.Row) and item.visible and any(
        isinstance(child, ft.ElevatedButton) for child in item.controls)]
    open_first_session(view)

    assert not [item for item in walk(view) if isinstance(item, (ft.Dropdown, ft.IconButton, ft.ElevatedButton, ft.OutlinedButton))]
    assert "Not marked" in texts(view)


def test_quorum_text():
    assert quorum_text({"in_office": 0}) == "No members in office on this date"
    assert quorum_text(QUORUM) == "Attendance not taken yet"
