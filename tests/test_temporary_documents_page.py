from datetime import date

import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.temporary_documents import TemporaryDocuments
from frontend.admin.tracking_ui import TrackingWidgets
from tests.test_account_menu_ui import DummyPage
from tests.test_todays_documents import _walk

TODAY = date(2026, 11, 7)
ORDINANCE = {"id": 7, "title": "Budget ordinance", "tracking_number": "ORD-000007", "document_number": "07", "series_year": 2026}


class FakeFiles:
    def pick(self, multiple, on_picked):
        on_picked([{"name": "MOA_health.pdf", "size": 9}])

    def upload(self, uploads, on_progress):
        on_progress(uploads[0][0], 1.0, None)


def build(archive=()):
    calls, entries = [], []

    def api(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/temporary-documents":
            return {"items": list(entries)}
        if path == "/temporary-documents/archive":
            return {"items": list(archive)}
        if path == "/documents":
            return {"items": [ORDINANCE]}
        if path == "/temporary-documents/ordinance":
            entries.append({"id": 1, "kind": "Ordinance", "title": ORDINANCE["title"], "document": ORDINANCE, "archived": False})
            return entries[-1]
        if path == "/documents/uploads/create_tmp_uploads":
            return {"files": [{"ok": True, "tmp_name": "tmp_1_MOA_health.pdf", "upload_url": "http://x/upload"}]}
        if path == "/temporary-documents/moa":
            entries.append({"id": 2, "kind": "MOA", "title": kwargs["json"]["title"], "filename": "MOA_health.pdf", "archived": False})
            return entries[-1]
        if path.endswith("/keep"):
            return {"due_on": "2026-12-07"}
        if method == "DELETE":
            return {}
        raise AssertionError((method, path))

    page = DummyPage()
    page.launch_url = lambda url: None
    widgets = TrackingWidgets(page)
    cards = TemporaryDocuments(page, api, widgets, FakeFiles(), lambda icon, title, *extra, subtitle=None: ft.Row([ft.Text(title), *extra]),
                               lambda message: ft.Text(message))
    return cards, calls


def find(card, kind, label):
    return next(c for c in _walk(card) if type(c).__name__ == kind and (getattr(c, "text", None) or getattr(c, "content", None)) == label)


def texts(card):
    return [c.value for c in _walk(card) if isinstance(c, ft.Text) and c.value]


def test_ordinance_search_lists_ordinances_only_and_adds_one_for_the_day():
    cards, calls = build()
    cards.load(TODAY, TODAY)
    listing = next(call for call in calls if call[1] == "/documents")
    assert listing[2]["params"]["document_type"] == "Ordinance"
    find(cards.day_card, "OutlinedButton", "Add").on_click(None)
    post = next(call for call in calls if call[1] == "/temporary-documents/ordinance")
    assert post[2]["json"] == {"scheduled_for": "2026-11-07", "document_id": 7}
    assert "1 for this day" in texts(cards.day_card) and "On this day" in texts(cards.day_card)


def test_an_moa_is_picked_titled_uploaded_and_saved_for_the_day():
    cards, calls = build()
    cards.load(TODAY, TODAY)
    find(cards.day_card, "OutlinedButton", "Upload a MOA").on_click(None)
    find(cards.day_card, "OutlinedButton", "Choose file…").on_click(None)
    assert cards.title_field.value == "MOA health"
    cards.title_field.value = "MOA with the Health Office"
    find(cards.day_card, "FilledButton", "Upload MOA").on_click(None)
    saved = next(call for call in calls if call[1] == "/temporary-documents/moa")
    assert saved[2]["json"] == {"scheduled_for": "2026-11-07", "tmp_name": "tmp_1_MOA_health.pdf", "title": "MOA with the Health Office"}
    assert "MOA with the Health Office" in texts(cards.day_card)


def test_a_past_day_is_read_only_and_the_archive_keeps_or_deletes_after_confirming():
    archived = {"id": 5, "kind": "MOA", "title": "Old MOA", "filename": "old.pdf", "scheduled_for": "2026-10-01",
                "archived": True, "due_on": "2026-11-01", "days_left": -6}
    cards, calls = build(archive=[archived])
    cards.load(date(2026, 11, 5), TODAY)
    assert cards.add_column.visible is False
    assert "Due for deletion" in texts(cards.archive_card) and "1 due" in texts(cards.archive_card)

    find(cards.archive_card, "OutlinedButton", "Keep 30 more days").on_click(None)
    assert ("POST", "/temporary-documents/5/keep") in [(m, p) for m, p, _ in calls]
    find(cards.archive_card, "TextButton", "Delete").on_click(None)
    assert not any(m == "DELETE" for m, _, _ in calls), "the first click only asks to confirm"
    find(cards.archive_card, "FilledButton", "Confirm delete").on_click(None)
    assert ("DELETE", "/temporary-documents/5") in [(m, p) for m, p, _ in calls]
