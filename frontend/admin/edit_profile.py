"""Edit profile: the signed-in user changes their own name and email."""

import flet as ft

from frontend.admin.registration import (
    _Notice, _dialog_width, _field_style, _labelled, _primary_button, _section, _style_dialog, error_detail,
)
from frontend.admin.tracking_ui import TrackingWidgets


def open_edit_profile_dialog(page, dialog, api, profile, *, on_saved=None):
    """Fill `dialog` with the profile form and open it.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    `on_saved(account)` gets the updated account.
    """
    ui = TrackingWidgets(page)
    field_style = _field_style(ui)
    name = ft.TextField(hint_text="e.g. Juan Dela Cruz", value=profile.get("full_name") or "", autofocus=True, **field_style)
    email = ft.TextField(hint_text="name@example.com", value=profile.get("email") or "", **field_style)
    message = _Notice()

    def close():
        dialog.open = False
        page.update()

    def show_error(text):
        message.value = text
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

    content = ft.Column(
        [
            _section(ui, ft.Icons.PERSON_OUTLINE, "Your details", [
                _labelled(ui, name, "Full name", ft.Icons.PERSON, required=True),
                _labelled(ui, email, "Email", ft.Icons.EMAIL_OUTLINED, required=True),
            ]),
            ft.Row(
                [ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ui.muted_color()),
                 ft.Text("Your username, role and office are managed by the Super Admin.", size=11, color=ui.muted_color(), expand=True)],
                spacing=8,
            ),
            message.box,
        ],
        tight=True,
        spacing=14,
    )
    _style_dialog(
        dialog, ui, "Edit profile", content,
        [ft.TextButton("Cancel", on_click=lambda _: close()), _primary_button("Save changes", ft.Icons.SAVE_OUTLINED, lambda _: save())],
        min(520, _dialog_width(page, False)),
        subtitle=f"Signed in as {profile['username']}." if profile.get("username") else "Update your name and email.",
        icon=ft.Icons.MANAGE_ACCOUNTS, on_close=close,
    )
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()
