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
    assert 'show_document_details({"id": document_id, "qr_token": qr_state.get("token"), "scanned": True}, allow_pass=True)' in source
    assert "open_details=lambda doc: show_document_details(doc, allow_pass=True),\n            open_pass=open_pass_document_dialog," in source
    assert "open_pass=open_pass_document_dialog if allow_pass else None," in source


class PhonePage(DummyPage):
    def __init__(self):
        super().__init__()
        self.width = 390
        self.controls = []

    def clean(self):
        self.controls = []

    def add(self, *controls):
        self.controls.extend(controls)


SCANNED = {**HELD, "can": {"pass": True, "receive": True, "record_action": False}}


def scanned_on_a_phone(open_pass, on_done=lambda: None):
    page, dialog = PhonePage(), ft.AlertDialog()
    open_document_details(page, dialog, lambda method, path, **kw: SCANNED, 7, normalize=lambda doc: doc,
                          qr_token="tok", open_pass=open_pass, on_done=on_done)
    return page, dialog


def button(page, label):
    return next(c for root in page.controls for c in walk(root)
                if isinstance(c, ft.FilledButton) and (c.text == label or c.content == label))


def test_a_scan_on_a_phone_fills_the_page_instead_of_opening_a_dialog():
    page, dialog = scanned_on_a_phone(open_pass=lambda doc, **kw: None)

    assert not dialog.open
    for label in ("Receive", "Pass on", "Done"):
        assert button(page, label)
    assert button(page, "Receive").height == 48


def test_done_leaves_the_scanned_document():
    done = []
    page, _ = scanned_on_a_phone(open_pass=lambda doc, **kw: None, on_done=lambda: done.append(True))

    button(page, "Done").on_click(None)

    assert done == [True]


def test_passing_on_from_the_phone_page_reloads_it_afterwards():
    calls = []
    page, _ = scanned_on_a_phone(open_pass=lambda doc, **kw: calls.append((doc["id"], kw)))

    button(page, "Pass on").on_click(None)

    assert calls[0][0] == 7 and callable(calls[0][1]["on_passed"])


WITH_FILE = {**SCANNED, "document": {**SCANNED["document"], "document_type": "Ordinance",
             "attachments": [{"id": 3, "original_filename": "ordinance.pdf", "mime_type": "application/pdf"}]}}


def scanned_with_file(monkeypatch, payload=WITH_FILE):
    import frontend.admin.document_details as details

    stage_calls = []
    monkeypatch.setattr(details, "build_stage_section", lambda page, api, document_id, *, can_change, on_saved: stage_calls.append(can_change) or ft.Text("stage"))
    page, dialog = PhonePage(), ft.AlertDialog()
    open_document_details(page, dialog, lambda method, path, **kw: payload, 7, normalize=lambda doc: doc,
                          qr_token="tok", open_pass=lambda doc, **kw: None, on_done=lambda: None,
                          can_download=True, can_print=True, can_edit=True, can_change_stage=True,
                          preview=lambda doc: None, download=lambda doc: None, open_edit=lambda doc: None,
                          load_qr_image=lambda document_id: None)
    return page, stage_calls


def labels(page):
    controls = [c for root in page.controls for c in walk(root)]
    buttons = [c.text if isinstance(getattr(c, "text", None), str) else getattr(c, "content", None)
               for c in controls if isinstance(c, (ft.FilledButton, ft.OutlinedButton, ft.TextButton))]
    return buttons, [c.value for c in controls if isinstance(c, ft.Text)]


def test_a_scan_is_only_for_receiving_and_passing_so_the_file_cannot_be_opened(monkeypatch):
    page, stage_calls = scanned_with_file(monkeypatch)

    buttons, _ = labels(page)
    for label in ("Preview", "Download", "Edit"):
        assert label not in buttons
    assert stage_calls == [False]  # the stage is shown, not changed, from a scan


def test_a_scan_shows_the_action_first_and_the_details_only_on_request(monkeypatch):
    page, _ = scanned_with_file(monkeypatch)

    buttons, texts = labels(page)
    assert "Receive" in buttons and "Pass on" in buttons
    assert "Document type" not in texts
    assert "View full details" in buttons

    next(c for root in page.controls for c in walk(root)
         if isinstance(c, ft.TextButton) and (c.text == "View full details" or c.content == "View full details")).on_click(None)

    buttons, texts = labels(page)
    assert "Document type" in texts and "Hide details" in buttons
    assert "Download" not in buttons and "Preview" not in buttons
