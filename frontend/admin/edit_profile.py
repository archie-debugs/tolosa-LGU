"""Edit profile: the signed-in user changes their own name and email."""

import flet as ft

from frontend.admin.registration import error_detail
from frontend.admin.tracking_ui import TrackingWidgets


def open_edit_profile_dialog(page, dialog, api, profile, *, on_saved=None):
    """Fill `dialog` with the profile form and open it.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    `on_saved(account)` gets the updated account.
    """
    ui = TrackingWidgets(page)
    name = ft.TextField(label="Full name", value=profile.get("full_name") or "", autofocus=True)
    email = ft.TextField(label="Email", value=profile.get("email") or "")
    message = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)

    def close():
        dialog.open = False
        page.update()

    def show_error(text):
        message.value = text
        message.visible = True
        page.update()

    def save():
        full_name = (name.value or "").strip()
        address = (email.value or "").strip()
        if not full_name:
            show_error("Full name is required.")
            return
        if not address:
            show_error("Email is required.")
            return
        try:
            account = api("PUT", "/auth/me", json={"full_name": full_name, "email": address})
        except Exception as exc:
            show_error(error_detail(exc)[0])
            return
        close()
        if on_saved:
            on_saved(account)

    dialog.modal = True
    dialog.title = ft.Text("Edit profile")
    dialog.content = ft.Column(
        [ui.hint("Your username, role and office are managed by the Super Admin."), name, email, message],
        tight=True,
        spacing=10,
        width=360,
    )
    dialog.actions = [
        ft.TextButton("Cancel", on_click=lambda _: close()),
        ft.Button("Save changes", icon=ft.Icons.SAVE_OUTLINED, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda _: save()),
    ]
    dialog.actions_alignment = ft.MainAxisAlignment.END
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()
