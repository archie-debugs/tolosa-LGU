from datetime import date, timedelta

import frontend.admin.app  # noqa: F401  applies the flet compatibility shims
import flet as ft

from frontend.sb_member import dashboard
from tests.test_account_menu_ui import DummyPage, click, clickable, texts, walk

TODAY = date.today()


def day(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


COUNCIL = {
    "/council/members": [
        {"id": 7, "full_name": "Hon. Maria Santos", "position": "Regular Member", "term_name": "2025-2028", "username": "msantos", "is_active": True},
        {"id": 8, "full_name": "Hon. Other", "position": "Vice Mayor", "term_name": "2025-2028", "username": "other", "is_active": True},
    ],
    "/council/sessions": {"sessions": [
        {"id": 1, "title": "11th Regular Session", "held_on": day(-7), "status": "Held"},
        {"id": 3, "title": "13th Regular Session", "held_on": day(14), "status": "Scheduled"},
        {"id": 2, "title": "12th Regular Session", "held_on": day(7), "status": "Scheduled"},
        {"id": 4, "title": "Old draft", "held_on": day(-1), "status": "Draft"},
    ]},
    "/council/sessions/2/business": {"sections": [{"items": [{}, {}]}, {"items": [{}]}]},
}
DOCUMENTS = {"items": [{"id": n, "title": f"Doc {n}", "document_type": "Ordinance"} for n in range(1, 6)]}
PDF = [{"id": 9, "filename": "x.pdf"}]
UPCOMING = {"days": [
    {"date": day(7), "items": [
        *[{"id": 20 + n, "title": f"Upcoming {n}", "document_type": "Ordinance", "tracking_number": f"ORD-{n}", "attachments": PDF} for n in range(1, 4)],
        {"id": None, "temporary_id": 4, "kind": "MOA", "title": "Upcoming MOA", "attachments": [{"id": 4, "filename": "moa.pdf"}]},
        {"id": 30, "title": "Upcoming no file", "document_type": "Ordinance", "tracking_number": "ORD-9", "attachments": []}]},
    {"date": day(8), "items": [{"id": 40, "title": "Tomorrow plus one", "document_type": "Ordinance", "tracking_number": "ORD-40", "attachments": PDF}]},
    {"date": day(21), "items": [{"id": 50, "title": "Three weeks out", "document_type": "Ordinance", "tracking_number": "ORD-50", "attachments": PDF}]},
]}


def card(control, padding=18):
    return ft.Container(content=control, padding=padding)


def build(council=COUNCIL, documents=DOCUMENTS, opened=None, upcoming=UPCOMING):
    opened = [] if opened is None else opened
    def council_api(method, path):
        if path not in council:
            raise RuntimeError("down")
        return council[path]

    def api(method, path):
        if path == "/upcoming-documents":
            if upcoming is None:
                raise RuntimeError("down")
            return upcoming
        return documents

    def file_actions(document):
        return [ft.IconButton(ft.Icons.PICTURE_AS_PDF_OUTLINED, tooltip="View PDF", on_click=lambda _: opened.append(("view", document["id"])))]

    shown = dashboard.build(DummyPage(), card, api, council_api,
                            {"username": "MSantos"}, opened.append, opened.append, file_actions)
    return shown, texts(shown)


def test_the_dashboard_shows_position_next_session_and_todays_documents():
    shown, words = build()

    assert "Good day, Hon. Maria Santos" in words and "Regular Member" in words
    assert "12th Regular Session" in words and "In 7 days" in words and "Order of business: 3 items" in words
    assert "Committees I chair" not in words
    assert ["Doc 1", "Doc 2", "Doc 3"] == [w for w in words if w.startswith("Doc ")]
    assert "See all 5" in [c.text for c in walk(shown) if isinstance(c, ft.TextButton)]


def test_each_card_says_why_it_is_empty_when_a_call_fails_or_nothing_is_set():
    _, words = build(council={}, documents={"items": []})

    assert "Good day, MSantos" in words  # no member record: falls back to the account name
    assert any(w.startswith("Unable to load sessions") for w in words)
    assert "No documents have been set for today yet." in words


def test_see_all_and_a_document_row_open_the_right_place():
    opened = []
    shown, _ = build(opened=opened)
    controls = list(walk(shown))

    click(next(c for c in controls if isinstance(c, ft.TextButton) and c.text == "See all 5"))
    click(next(c for c in controls if isinstance(c, ft.Container) and clickable(c) and "Doc 2" in texts(c)))

    assert opened == ["Today's Documents", DOCUMENTS["items"][1]]


def test_next_sessions_documents_show_the_first_documents_of_the_next_two_days():
    opened = []
    shown, words = build(opened=opened)

    assert "Next Sessions Documents" in words
    assert ["Upcoming 1", "Upcoming 2", "Upcoming 3"] == [w for w in words if w.startswith("Upcoming ") and w[-1].isdigit()]
    assert "and 2 more" in words and "Tomorrow plus one" in words and "Three weeks out" not in words
    assert (TODAY + timedelta(days=7)).strftime("%A, %B %d, %Y") in words
    controls = list(walk(shown))
    click(next(c for c in controls if isinstance(c, ft.IconButton) and c.tooltip == "View PDF"))
    click(next(c for c in controls if isinstance(c, ft.TextButton) and c.text == "See all upcoming documents"))
    assert opened == [("view", 21), "Upcoming Documents"]


def test_the_next_sessions_card_says_why_it_is_empty():
    assert "No documents have been set for a later day yet." in build(upcoming={"days": []})[1]
    assert any(w.startswith("Unable to load upcoming documents") for w in build(upcoming=None)[1])
