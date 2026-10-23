"""Change password: the signed-in user replaces their own password."""

import flet as ft

from frontend.admin.registration import (
    _Notice, _dialog_width, _field_style, _labelled, _primary_button, _section, _style_dialog, error_detail,
)
from frontend.admin.tracking_ui import TrackingWidgets

MIN_LENGTH = 8


def open_change_password_dialog(page, dialog, api):
    """Fill `dialog` with the change-password form and open it.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    """
    ui = TrackingWidgets(page)
    field_style = _field_style(ui)
    width = min(520, _dialog_width(page, False))
    current = ft.TextField(hint_text="Your password now", password=True, can_reveal_password=True, autofocus=True, **field_style)
    new = ft.TextField(hint_text=f"At least {MIN_LENGTH} characters", password=True, can_reveal_password=True, **field_style)
    confirm = ft.TextField(hint_text="Type it again", password=True, can_reveal_password=True, **field_style)
    message = _Notice()
    cancel_button = ft.TextButton("Cancel", on_click=lambda _: close())
    change_button = _primary_button("Change password", ft.Icons.LOCK_RESET, lambda _: submit())

    def close():
        dialog.open = False
        page.update()

    def show_error(text):
        message.value = text
        page.update()

    def problem():
        if not current.value:
            return "Enter your current password."
        if not new.value:
            return "Enter a new password."
        if new.value != confirm.value:
            return "The new passwords do not match."
        if len(new.value) < MIN_LENGTH:
            return f"Use at least {MIN_LENGTH} characters."
        return None

    def submit():
        reason = problem()
        if reason:
            show_error(reason)
            return
        try:
            api("POST", "/auth/me/password", json={
                "current_password": current.value, "new_password": new.value, "confirm_password": confirm.value,
            })
        except Exception as exc:
            show_error(error_detail(exc)[0])
            return
        done = ft.Column(
            [
                ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=ft.Colors.GREEN_600), ft.Text("Your password has been changed.", size=14, color=ui.heading_color())], spacing=8),
                ui.hint("You stay signed in here; your other sessions were signed out."),
            ],
            tight=True,
            spacing=8,
        )
        _style_dialog(dialog, ui, "Change password", done, [ft.TextButton("Close", on_click=lambda _: close())], width,
                      subtitle="Your account is secured with the new password.", icon=ft.Icons.LOCK_RESET, on_close=close)
        page.update()

    half = {"xs": 12, "sm": 6}
    content = ft.Column(
        [
            _section(ui, ft.Icons.LOCK_OUTLINE, "Password", [
                _labelled(ui, current, "Current password", ft.Icons.KEY, required=True),
                ft.ResponsiveRow([
                    _labelled(ui, new, "New password", ft.Icons.PASSWORD, required=True, col=half),
                    _labelled(ui, confirm, "Confirm new password", ft.Icons.PASSWORD, required=True, col=half),
                ], spacing=14, run_spacing=12),
                ui.hint("Changing it signs you out everywhere else."),
            ]),
            message.box,
        ],
        tight=True,
        spacing=14,
    )
    _style_dialog(dialog, ui, "Change password", content, [cancel_button, change_button], width,
                  subtitle=f"Choose a new password of at least {MIN_LENGTH} characters.", icon=ft.Icons.LOCK_RESET, on_close=close)
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()
