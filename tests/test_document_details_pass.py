import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.document_details import PASS_FROM_DASHBOARD, open_document_details

HELD = {
    "document": {"id": 7, "tracking_number": "ORD-2026-0001", "title": "Ordinance No. 7", "status": "Approved",
                 "current_office": "Records Office", "attachments": []},
    "location": {}, "events": [], "can": {"pass": True, "receive": False, "record_action": False},
}


class DummyPage:
    def __init__(self):
        self.overlay = []
        self.theme_mode = None
        self.width = 1200

    def update(self, *args):
        pass


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", None) or []:
        yield from walk(child)
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)


def shown(payload, open_pass):
    dialog = ft.AlertDialog()
    open_document_details(DummyPage(), dialog, lambda method, path, **kw: payload, 7,
                          normalize=lambda doc: doc, open_pass=open_pass)
    controls = list(walk(dialog.content))
    buttons = [c.text if isinstance(getattr(c, "text", None), str) else getattr(c, "content", None)
               for c in controls if isinstance(c, (ft.FilledButton, ft.OutlinedButton))]
    texts = [c.value for c in controls if isinstance(c, ft.Text)]
    return buttons, texts


def test_details_opened_from_the_office_dashboard_or_a_scan_can_pass_the_document_on():
    buttons, texts = shown(HELD, open_pass=lambda doc: None)

    assert "Pass on" in buttons
    assert PASS_FROM_DASHBOARD not in texts


def test_details_opened_elsewhere_point_to_the_office_dashboard_instead():
    buttons, texts = shown(HELD, open_pass=None)

    assert "Pass on" not in buttons
    assert PASS_FROM_DASHBOARD in texts


def test_no_hint_when_the_office_may_not_pass_the_document():
    payload = {**HELD, "can": {"pass": False}}

    buttons, texts = shown(payload, open_pass=None)

    assert "Pass on" not in buttons
    assert PASS_FROM_DASHBOARD not in texts


def test_only_the_office_dashboard_and_a_qr_scan_open_details_that_can_pass():
    from pathlib import Path

    source = Path(frontend.admin.app.__file__).read_text(encoding="utf-8")

    assert source.count("allow_pass=True") == 2
    assert 'show_document_details({"id": document_id, "qr_token": qr_state.get("token")}, allow_pass=True)' in source
    assert "open_details=lambda doc: show_document_details(doc, allow_pass=True),\n            open_pass=open_pass_document_dialog," in source
    assert "open_pass=open_pass_document_dialog if allow_pass else None," in source
