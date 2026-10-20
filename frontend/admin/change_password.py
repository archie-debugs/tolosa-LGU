"""Change password: the signed-in user replaces their own password."""

import flet as ft

from frontend.admin.registration import error_detail
from frontend.admin.tracking_ui import TrackingWidgets

MIN_LENGTH = 8


def open_change_password_dialog(page, dialog, api):
    """Fill `dialog` with the change-password form and open it.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    """
    ui = TrackingWidgets(page)
    current = ft.TextField(label="Current password", password=True, can_reveal_password=True, autofocus=True)
    new = ft.TextField(label="New password", password=True, can_reveal_password=True)
    confirm = ft.TextField(label="Confirm new password", password=True, can_reveal_password=True)
    message = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)
    cancel_button = ft.TextButton("Cancel", on_click=lambda _: close())
    change_button = ft.Button("Change password", icon=ft.Icons.LOCK_RESET, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda _: submit())

    def close():
        dialog.open = False
        page.update()

    def show_error(text):
        message.value = text
        message.visible = True
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
        dialog.content = ft.Column(
            [
                ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=ft.Colors.GREEN_700), ft.Text("Your password has been changed.", size=14, color=ui.heading_color())], spacing=8),
                ui.hint("You stay signed in here; your other sessions were signed out."),
            ],
            tight=True,
            spacing=8,
            width=360,
        )
        dialog.actions = [ft.TextButton("Close", on_click=lambda _: close())]
        page.update()

    dialog.modal = True
    dialog.title = ft.Text("Change password")
    dialog.content = ft.Column(
        [ui.hint(f"At least {MIN_LENGTH} characters."), current, new, confirm, message],
        tight=True,
        spacing=10,
        width=360,
    )
    dialog.actions = [cancel_button, change_button]
    dialog.actions_alignment = ft.MainAxisAlignment.END
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()
