from datetime import date
import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)

import flet as ft

from frontend.admin.print_list import open_print_list_dialog
from tests.test_account_menu_ui import DummyPage, find


def test_print_list_dialog_sends_the_picked_options_and_opens_the_link():
    page, dialog, calls, opened = DummyPage(), ft.AlertDialog(), [], []
    page.launch_url = opened.append

    def api(method, path, **kwargs):
        calls.append((method, path, kwargs["json"]))
        return {"url": "https://example.test/print-list/page?download_token=t"}

    open_print_list_dialog(page, dialog, api, document_type="Resolution", today=date(2026, 11, 7))
    boxes = {box.label: box for box in find(dialog, ft.Checkbox)}
    assert [label for label, box in boxes.items() if box.value] == ["Resolutions"]
    boxes["Ordinances"].value = True
    year, month = find(dialog, ft.Dropdown)
    month.value = "3"
    next(b for b in find(dialog, ft.FilledButton) if "Open list" in str(b.content or b.text)).on_click(None)

    assert calls == [("POST", "/print-list/link", {"year": 2026, "month": 3, "types": ["Ordinance", "Resolution"]})]
    assert opened == ["https://example.test/print-list/page?download_token=t"] and dialog.open is False
