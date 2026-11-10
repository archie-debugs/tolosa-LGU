"""The scan screen: where a device waits after a scanned document is done, or a scan could not open one.

A QR scan is only for receiving and passing documents on, so finishing one does not open the
workspace. The next document is opened by scanning its label.
"""

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets
from frontend.theme import PRIMARY


def build_scan_home(page, *, username, office, on_logout, problem=None, on_retry=None):
    """`problem` is a (title, message) shown instead of "Ready to scan" when a scan could not open
    a document; `on_retry` adds a Try again button."""
    widgets = TrackingWidgets(page)
    signed_in = f"Signed in as {username or '-'}" + (f" · {office}" if office else "")
    title, message = problem or ("Ready to scan", "Scan a document's QR label to receive it or pass it on.")
    icon, color = (ft.Icons.ERROR_OUTLINE, ft.Colors.RED_700) if problem else (ft.Icons.QR_CODE_SCANNER, PRIMARY)
    if problem:
        message += "\nTo open another document, scan its QR label."
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Icon(icon, size=56, color=color),
                    padding=18,
                    bgcolor=ft.Colors.with_opacity(0.1, color),
                    border_radius=60,
                ),
                ft.Text(title, size=22, weight=ft.FontWeight.BOLD, color=widgets.heading_color(), text_align=ft.TextAlign.CENTER),
                ft.Text(message, size=14, color=widgets.body_color(), text_align=ft.TextAlign.CENTER),
                ft.Text(signed_in, size=12, color=widgets.muted_color(), text_align=ft.TextAlign.CENTER),
                ft.Container(height=8),
                *([ft.FilledButton("Try again", icon=ft.Icons.REFRESH, height=48, on_click=lambda _: on_retry())] if on_retry else []),
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
