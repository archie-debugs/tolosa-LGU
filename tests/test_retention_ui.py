import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.documents import build_documents_view
from frontend.admin.retention import due_for_deletion, open_retention_dialog
from tests.test_account_menu_ui import DummyPage, walk
from tests.test_settings_pages import admin_view, words

DUE = {"kind": "retention_due", "priority": True, "document_id": 7, "tracking_number": "LTR-000007",
       "title": "Request for a covered court", "message": "Letter Request retention ended Oct 01, 2026."}


class RecordingApi:
    def __init__(self, settings=None):
        self.calls = []
        self.settings = settings or {}

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        if path == "/system-settings":
            return {"settings": self.settings}
        return {}


def clickable(control, label):
    return next(c for c in walk(control) if isinstance(c, (ft.FilledButton, ft.OutlinedButton, ft.TextButton, ft.ElevatedButton))
                and label in words(c))


def open_dialog(items=(DUE,)):
    page, api, changed = DummyPage(), RecordingApi(), []
    dialog = open_retention_dialog(page, api, list(items), on_changed=lambda: changed.append(True))
    return page, api, changed, dialog


def test_only_documents_past_their_retention_pop_up():
    soon = {**DUE, "kind": "retention_soon", "priority": False}
    assert due_for_deletion({"items": [DUE, soon, {"kind": "incoming"}]}) == [DUE]
    assert open_retention_dialog(DummyPage(), RecordingApi(), []) is None


def test_delete_now_asks_once_more_then_deletes():
    page, api, changed, dialog = open_dialog()
    assert dialog.open and dialog.modal
    assert "LTR-000007" in words(dialog)

    clickable(dialog, "Delete now").on_click(None)
    assert api.calls == []
    assert "Its record, file and tracking history are deleted. This cannot be undone." in words(dialog)
    clickable(dialog, "Delete permanently").on_click(None)

    assert api.calls == [("DELETE", "/documents/7/permanent", None)]
    assert changed == [True]
    assert dialog.open is False


def test_extend_keeps_it_for_the_chosen_time():
    page, api, changed, dialog = open_dialog([DUE, {**DUE, "document_id": 8, "tracking_number": "LTR-000008"}])
    choice = next(c for c in walk(dialog) if isinstance(c, ft.Dropdown))
    choice.value = "12"
    clickable(dialog, "Extend").on_click(None)

    assert api.calls == [("POST", "/documents/7/retention/extend", {"months": 12})]
    # The other document still waits for an answer.
    assert dialog.open and "LTR-000008" in words(dialog) and "LTR-000007" not in words(dialog)


def test_a_failed_action_says_why_and_keeps_the_document():
    page, changed = DummyPage(), []

    def failing(method, path, **kwargs):
        raise Exception("Document not found")

    dialog = open_retention_dialog(page, failing, [DUE], on_changed=lambda: changed.append(True))
    clickable(dialog, "Extend").on_click(None)

    assert "Document not found" in words(dialog)
    assert dialog.open and changed == []


def test_archived_rows_say_when_they_are_due_for_deletion():
    items = [
        {"id": 1, "tracking_number": "LTR-000001", "title": "Old letter", "archived_at": "2025-01-01T00:00:00+00:00", "retain_until": "2025-11-01T00:00:00+00:00"},
        {"id": 2, "tracking_number": "ORD-000001", "title": "An ordinance", "archived_at": "2025-01-01T00:00:00+00:00", "retain_until": None},
    ]
    asked = []
    view, _ = build_documents_view(
        DummyPage(), lambda *a, **k: {"items": items, "total": 2, "total_pages": 1}, lambda content, **_: ft.Container(content),
        normalize=dict, selection=set(), loaded=[], archived=True, can_delete=True, keep_or_delete=asked.append,
        delete_permanently=lambda doc: None,
    )
    shown = words(view)
    assert "Kept permanently" in shown
    assert any(text.startswith("Delete after ") for text in shown)
    assert shown.count("Due for deletion") == 1

    menus = [c for c in walk(view) if isinstance(c, ft.PopupMenuButton)]
    labels = [[text for item in menu.items for text in words(item)] for menu in menus]
    assert "Keep longer or delete" in labels[0] and "Keep longer or delete" not in labels[1]


def test_settings_edit_how_long_each_type_is_kept():
    api = RecordingApi({"retention_months": {"Ordinance": None, "Resolution": 120, "Letter Request": 10}})
    view, _ = admin_view(api=api)
    assert "Document Retention" in words(view)
    fields = [c for c in walk(view) if isinstance(c, ft.TextField) and c.keyboard_type == ft.KeyboardType.NUMBER]
    units = [c for c in walk(view) if isinstance(c, ft.Dropdown) and c.value in ("Years", "Months", "Permanent")]
    assert [(f.value, f.disabled) for f in fields[-3:]] == [("", True), ("10", False), ("10", False)]
    assert [u.value for u in units] == ["Permanent", "Years", "Months"]

    fields[-1].value = "18"
    clickable(view, "Save retention periods").on_click(None)
    assert api.calls[-1] == ("PUT", "/system-settings", {"settings": {"retention_months": {"Ordinance": None, "Resolution": 120, "Letter Request": 18}}})
    assert "Retention periods saved." in words(view)

    fields[-1].value = ""
    clickable(view, "Save retention periods").on_click(None)
    assert "Type how long a Letter Request is kept, or choose Permanent." in words(view)
