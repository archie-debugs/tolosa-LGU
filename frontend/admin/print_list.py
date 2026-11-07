"""Print list: pick types, a year and optionally a month, then open the printable list in the browser.

The backend draws the page (Backends/backend/routes/print_list.py); the browser prints it or saves it as PDF.
"""

from datetime import date

import flet as ft

from frontend.admin.registration import (
    _Notice, _dialog_width, _field_style, _labelled, _primary_button, _section, _style_dialog, _year_dropdown, error_detail,
)
from frontend.admin.tracking_ui import TrackingWidgets

TYPES = ["Ordinance", "Resolution", "Letter Request"]
PLURALS = {"Ordinance": "Ordinances", "Resolution": "Resolutions", "Letter Request": "Letter Requests"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def open_print_list_dialog(page, dialog, api, *, document_type=None, today=None):
    """`document_type` starts with only that type ticked; otherwise all three are.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    """
    ui = TrackingWidgets(page)
    width = min(520, _dialog_width(page, False))
    boxes = {name: ft.Checkbox(label=PLURALS[name], value=document_type in (None, name)) for name in TYPES}
    year = _year_dropdown((today or date.today()).year, widgets=ui)
    month = ft.Dropdown(
        data="Month", value="",
        options=[ft.dropdown.Option(key="", text="All months"), *[ft.dropdown.Option(key=str(i), text=name) for i, name in enumerate(MONTHS, start=1)]],
        **_field_style(ui),
    )
    message = _Notice()

    def close():
        dialog.open = False
        page.update()

    def submit():
        types = [name for name, box in boxes.items() if box.value]
        if not types:
            message.value = "Tick at least one document type."
            page.update()
            return
        try:
            url = api("POST", "/print-list/link", json={"year": int(year.value), "month": int(month.value) if month.value else None, "types": types})["url"]
        except Exception as exc:
            message.value = error_detail(exc)[0]
            page.update()
            return
        page.launch_url(url)
        close()

    half = {"xs": 12, "sm": 6}
    content = ft.Column(
        [
            _section(ui, ft.Icons.PRINT_OUTLINED, "What to list", [
                ft.Row(list(boxes.values()), wrap=True, spacing=14),
                ft.ResponsiveRow([
                    _labelled(ui, year, "Year", ft.Icons.CALENDAR_TODAY, col=half),
                    _labelled(ui, month, "Month", ft.Icons.DATE_RANGE, col=half),
                ], spacing=14, run_spacing=12),
                ui.hint("The list opens in your browser, ready to print or save as PDF."),
            ]),
            message.box,
        ],
        tight=True,
        spacing=14,
    )
    _style_dialog(dialog, ui, "Print list", content,
                  [ft.TextButton("Cancel", on_click=lambda _: close()), _primary_button("Open list", ft.Icons.PRINT, lambda _: submit())],
                  width, subtitle="Title, date approved and proponents, by type and month.", icon=ft.Icons.PRINT, on_close=close)
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()
