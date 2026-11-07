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
