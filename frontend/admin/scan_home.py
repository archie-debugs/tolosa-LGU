"""The phone's scan screen: where a phone waits after a scanned document is done.

A QR scan is only for receiving and passing documents on, so finishing one does not open the
workspace. The next document is opened by scanning its label with the phone's camera.
"""

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets
from frontend.theme import PRIMARY


def build_scan_home(page, *, username, office, on_logout):
    widgets = TrackingWidgets(page)
    signed_in = f"Signed in as {username or '-'}" + (f" · {office}" if office else "")
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.QR_CODE_SCANNER, size=56, color=PRIMARY),
                    padding=18,
                    bgcolor=ft.Colors.with_opacity(0.1, PRIMARY),
                    border_radius=60,
                ),
                ft.Text("Ready to scan", size=22, weight=ft.FontWeight.BOLD, color=widgets.heading_color()),
                ft.Text(
                    "Point your phone's camera at a document's QR label to receive it or pass it on.",
                    size=14,
                    color=widgets.body_color(),
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(signed_in, size=12, color=widgets.muted_color(), text_align=ft.TextAlign.CENTER),
                ft.Container(height=8),
                ft.OutlinedButton("Log out", icon=ft.Icons.LOGOUT, height=48, on_click=lambda _: on_logout()),
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        ),
        padding=24,
        bgcolor=widgets.card_color(),
        expand=True,
    )
