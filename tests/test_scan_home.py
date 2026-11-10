import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.scan_home import build_scan_home
from tests.test_document_details_pass import PhonePage, walk


def test_after_a_scan_the_phone_waits_for_the_next_scan_instead_of_opening_the_workspace():
    logged_out = []
    view = build_scan_home(PhonePage(), username="clerk", office="Records Office",
                           on_logout=lambda: logged_out.append(True))

    controls = list(walk(view))
    texts = [c.value for c in controls if isinstance(c, ft.Text)]
    assert "Ready to scan" in texts
    assert any("clerk" in (t or "") and "Records Office" in (t or "") for t in texts)
    logout = next(c for c in controls if isinstance(c, (ft.OutlinedButton, ft.FilledButton, ft.TextButton))
                  and (c.text == "Log out" or c.content == "Log out"))
    logout.on_click(None)
    assert logged_out == [True]


def test_done_on_a_scanned_document_goes_to_the_scan_screen():
    from pathlib import Path

    source = Path(frontend.admin.app.__file__).read_text(encoding="utf-8")
    leave = source.split("def leave_qr_document():", 1)[1].split("\n    def ", 1)[0]

    assert "build_scan_home(" in leave
    assert "show_shell(" not in leave and "sb_member_main" not in leave


def test_a_scan_that_cannot_open_a_document_says_why_and_offers_a_way_on():
    retried, logged_out = [], []
    view = build_scan_home(PhonePage(), username="clerk", office="Records Office", on_logout=lambda: logged_out.append(True),
                           problem=("Document Not Found", "This QR code does not correspond to an available document."),
                           on_retry=lambda: retried.append(True))
    controls = list(walk(view))
    texts = " ".join(c.value or "" for c in controls if isinstance(c, ft.Text))
    assert "Document Not Found" in texts and "Ready to scan" not in texts and "scan its QR label" in texts
    buttons = {(c.text or c.content): c for c in controls if isinstance(c, (ft.OutlinedButton, ft.FilledButton))}
    buttons["Try again"].on_click(None)
    buttons["Log out"].on_click(None)
    assert retried == [True] and logged_out == [True]


def test_scan_states_lead_somewhere_and_the_browser_forgets_an_answered_code():
    from pathlib import Path

    source = Path(frontend.admin.app.__file__).read_text(encoding="utf-8")
    render = source.split("def _render_qr_authorization_state(qr_state):", 1)[1].split("\n    def ", 1)[0]
    # Every outcome but "checking" and "authorized" is the scan screen, with Log out.
    assert "build_scan_home(" in render and "on_logout=logout_user" in render and "forget_scanned_code()" in render
    opened = source.split("def _open_authorized_qr_document(qr_state):", 1)[1].split("\n    def ", 1)[0]
    assert "forget_scanned_code()" in opened
    # The scanned document is a page with Done on every device, not a dialog over an empty page.
    assert 'on_done=leave_qr_document if doc.get("scanned") else None,' in source
