import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.office_dashboard import build_office_queue_view
from frontend.admin.tracking_ui import event_summary
from tests.test_account_menu_ui import DummyPage, find, texts


def queue_payload(own_office=True):
    return {
        "office": {"name": "Office A"},
        "own_office": own_office,
        "summary": {},
        "incoming": [{"handoff_id": 7, "document_id": 1, "tracking_number": "DOC-000001", "title": "Budget", "from_office": "Office B", "sent_at": None}],
        "holding": {"items": [], "total": 0, "total_pages": 0},
        "outgoing": [{"handoff_id": 9, "document_id": 2, "tracking_number": "DOC-000002", "title": "Permit", "to_office": "Office C", "sent_at": None}],
        "recent_activity": [],
    }


class FakeApi:
    def __init__(self, own_office=True):
        self.calls = []
        self.own_office = own_office

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        return queue_payload(self.own_office) if method == "GET" else {}

    def posts(self):
        return [(path, body) for method, path, body in self.calls if method == "POST"]


def build(**kwargs):
    # The backend answers own_office=False when a Super Administrator monitors another office.
    api = FakeApi(own_office="office_id" not in kwargs)
    options = {"can_receive": True, "can_pass": True, **kwargs}
    view, _ = build_office_queue_view(DummyPage(), api, lambda content, padding=0: ft.Container(content), lambda *a: ft.Text(a[0]), **options)
    return view, api


def button(view, label):
    matches = [c for c in find(view, ft.TextButton) + find(view, ft.FilledButton) + find(view, ft.OutlinedButton)
               if getattr(c, "text", None) == label or getattr(c, "content", None) == label]
    assert matches, f"no {label!r} button among {texts(view)}"
    return matches[0]


def click(control):
    control.on_click(None)


def test_returning_asks_for_a_reason_before_posting():
    view, api = build()
    click(button(view, "Return"))
    reason = next(c for c in find(view, ft.TextField) if c.label == "Why are you returning it?")

    click(button(view, "Return to sender"))
    assert api.posts() == []
    assert reason.error_text

    reason.value = "Wrong office"
    click(button(view, "Return to sender"))
    assert api.posts() == [("/documents/handoffs/7/return", {"reason": "Wrong office"})]
    assert any("Returned DOC-000001 to Office B" in text for text in texts(view))


def test_cancelling_a_sent_handoff_needs_a_confirmation():
    view, api = build()
    click(button(view, "Cancel"))
    assert api.posts() == []

    click(button(view, "Cancel handoff"))
    assert api.posts() == [("/documents/handoffs/9/cancel", {})]
    assert any("Cancelled the handoff of DOC-000002" in text for text in texts(view))


def test_no_return_or_cancel_without_the_permissions():
    view, _ = build(can_receive=False, can_pass=False)
    labels = {getattr(c, "text", None) or getattr(c, "content", None) for c in find(view, ft.TextButton) + find(view, ft.OutlinedButton)}
    assert not labels & {"Return", "Cancel", "Receive"}


def test_a_monitored_office_is_read_only():
    view, _ = build(office_id=5)
    labels = {getattr(c, "text", None) or getattr(c, "content", None) for c in find(view, ft.TextButton) + find(view, ft.OutlinedButton)}
    assert not labels & {"Return", "Cancel"}


def test_event_summaries_for_returned_and_cancelled_handoffs():
    assert event_summary({"type": "returned", "office": "Office B", "to_office": "Office A", "detail": "Wrong office"}) == "Office B returned it to Office A · Wrong office"
    assert event_summary({"type": "cancelled", "office": "Office A", "to_office": "Office B"}) == "Office A cancelled the handoff to Office B"
