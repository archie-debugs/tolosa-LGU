"""Two-step login in My Account: turn it on with an authenticator app, or turn it off."""

import base64

import flet as ft

from frontend.admin.document_details import IMAGE_TAKES_BASE64
from frontend.admin.registration import error_detail
from frontend.admin.tracking_ui import TrackingWidgets


def login_needs_code(response):
    """True when POST /auth/login accepted the password and now wants the 6-digit code."""
    return response.status_code == 401 and response.headers.get("X-Two-Step") == "required"


def _code(field):
    return "".join((field.value or "").split())


def _open(page, dialog, title, body, actions):
    dialog.modal = True
    dialog.title = ft.Text(title)
    dialog.content = ft.Column(body, tight=True, spacing=10, width=360, scroll=ft.ScrollMode.AUTO)
    dialog.actions = actions
    dialog.actions_alignment = ft.MainAxisAlignment.END
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()


def _close(page, dialog):
    dialog.open = False
    page.update()


def _error_text():
    return ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)


def _show(page, message, text):
    message.value = text
    message.visible = True
    page.update()


def open_turn_on_dialog(page, dialog, api, *, on_done):
    """Scan the QR, confirm one code, then show the recovery codes once.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    """
    ui = TrackingWidgets(page)
    cancel = ft.TextButton("Cancel", on_click=lambda _: _close(page, dialog))
    try:
        setup = api("POST", "/auth/two-step/setup")
    except Exception as exc:
        _open(page, dialog, "Turn on two-step login", [ft.Text(error_detail(exc)[0], size=12, color=ft.Colors.RED_700)], [cancel])
        return

    image = (ft.Image(src_base64=setup["qr_png_base64"], width=180, height=180) if IMAGE_TAKES_BASE64
             else ft.Image(src=base64.b64decode(setup["qr_png_base64"]), width=180, height=180))
    code = ft.TextField(label="6-digit code", autofocus=True, max_length=6, keyboard_type=ft.KeyboardType.NUMBER)
    message = _error_text()

    def show_recovery_codes(codes):
        def finish():
            _close(page, dialog)
            on_done()

        _open(page, dialog, "Save your recovery codes", [
            ui.hint("Each code works once, in place of the 6-digit code, if you lose your phone. "
                    "Write them down or print them now: they will not be shown again."),
            ft.Container(
                ft.Column([ft.Text(value, size=15, weight=ft.FontWeight.W_600, font_family="Consolas", selectable=True) for value in codes], spacing=4, tight=True),
                padding=12,
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.BLUE_GREY_500),
            ),
        ], [ft.Button("I saved them", icon=ft.Icons.CHECK, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda _: finish())])

    def turn_on():
        value = _code(code)
        if len(value) != 6 or not value.isdigit():
            _show(page, message, "Enter the 6-digit code from your app.")
            return
        try:
            body = api("POST", "/auth/two-step/enable", json={"code": value})
        except Exception as exc:
            _show(page, message, error_detail(exc)[0])
            return
        show_recovery_codes(body.get("recovery_codes") or [])

    _open(page, dialog, "Turn on two-step login", [
        ui.hint("1. Scan this with an authenticator app such as Google Authenticator or Microsoft Authenticator."),
        ft.Row([image], alignment=ft.MainAxisAlignment.CENTER),
        ui.hint("Can't scan? Type this key into the app:"),
        ft.Text(setup["secret"], size=13, weight=ft.FontWeight.W_600, font_family="Consolas", selectable=True),
        ui.hint("2. Enter the 6-digit code the app shows."),
        code,
        message,
    ], [cancel, ft.Button("Turn on", icon=ft.Icons.SHIELD_OUTLINED, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda _: turn_on())])


def open_turn_off_dialog(page, dialog, api, *, on_done):
    ui = TrackingWidgets(page)
    password = ft.TextField(label="Password", password=True, can_reveal_password=True, autofocus=True)
    code = ft.TextField(label="6-digit code or recovery code")
    message = _error_text()

    def turn_off():
        if not password.value or not _code(code):
            _show(page, message, "Enter your password and a code.")
            return
        try:
            api("POST", "/auth/two-step/disable", json={"password": password.value, "code": _code(code)})
        except Exception as exc:
            _show(page, message, error_detail(exc)[0])
            return
        _close(page, dialog)
        on_done()

    _open(page, dialog, "Turn off two-step login", [
        ui.hint("You will log in with your password alone."),
        password,
        code,
        message,
    ], [
        ft.TextButton("Cancel", on_click=lambda _: _close(page, dialog)),
        ft.Button("Turn off", icon=ft.Icons.REMOVE_MODERATOR_OUTLINED, bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, on_click=lambda _: turn_off()),
    ])


def two_step_row(page, dialog, api, account, *, on_changed, label_color=None):
    """The My Account security row: on or off, and the button to change it."""
    enabled = bool(account.get("two_step_enabled"))
    if enabled:
        left = account.get("two_step_recovery_codes_left") or 0
        status = f"On · {left} recovery code{'' if left == 1 else 's'} left"
        button = ft.OutlinedButton("Turn off", icon=ft.Icons.REMOVE_MODERATOR_OUTLINED,
                                   on_click=lambda _: open_turn_off_dialog(page, dialog, api, on_done=on_changed))
    else:
        status = "Off"
        button = ft.OutlinedButton("Turn on", icon=ft.Icons.SHIELD_OUTLINED,
                                   on_click=lambda _: open_turn_on_dialog(page, dialog, api, on_done=on_changed))
    return ft.Row([
        ft.Text("Two-step login", size=12, color=label_color, width=120),
        ft.Text(status, size=13, weight=ft.FontWeight.W_500,
                color=ft.Colors.GREEN_700 if enabled else None),
        button,
    ], spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
