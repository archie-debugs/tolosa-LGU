"""Two-step login in My Account: turn it on with an authenticator app, or turn it off."""

import base64

import flet as ft

from frontend.admin.document_details import IMAGE_TAKES_BASE64
from frontend.admin.registration import (
    _STATE, _Notice, _dialog_width, _field_style, _labelled, _primary_button, _section, _style_dialog, error_detail,
)
from frontend.admin.tracking_ui import TrackingWidgets


def login_needs_code(response):
    """True when POST /auth/login accepted the password and now wants the 6-digit code."""
    return response.status_code == 401 and response.headers.get("X-Two-Step") == "required"


def _code(field):
    return "".join((field.value or "").split())


def _open(page, dialog, title, body, actions, *, subtitle=None, icon=ft.Icons.SHIELD_OUTLINED, tall=False):
    """`tall` bodies scroll inside a fixed height, so the QR step fits short windows."""
    ui = TrackingWidgets(page)
    content = ft.Column(body, tight=True, spacing=14, scroll=ft.ScrollMode.AUTO)
    if tall:
        content.height = min(560, (page.height or 800) - 200)
    _style_dialog(dialog, ui, title, content, actions, min(520, _dialog_width(page, False)),
                  subtitle=subtitle, icon=icon, on_close=lambda: _close(page, dialog))
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()


def _close(page, dialog):
    dialog.open = False
    page.update()


def _show(page, message, text):
    message.value = text
    page.update()


def _danger_button(text, icon, on_click):
    """_primary_button in red, for turning protection off."""
    button = _primary_button(text, icon, on_click)
    button.style.bgcolor = {_STATE.DISABLED: ft.Colors.BLUE_GREY_200, _STATE.DEFAULT: ft.Colors.RED_700}
    return button


def _code_box(ui, values):
    """The setup key or the recovery codes, in a tinted box that is easy to copy from."""
    return ft.Container(
        ft.Column(
            [ft.Text(value, size=15, weight=ft.FontWeight.W_600, font_family="Consolas", selectable=True, color=ui.heading_color()) for value in values],
            spacing=4,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=12,
        border_radius=8,
        bgcolor=ui.tone("#E8F1FD", "#1E2B38"),
        border=ft.border.all(1, ui.line_color()),
        alignment=ft.Alignment(0, 0),
    )


def open_turn_on_dialog(page, dialog, api, *, on_done):
    """Scan the QR, confirm one code, then show the recovery codes once.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    """
    ui = TrackingWidgets(page)
    cancel = ft.TextButton("Cancel", on_click=lambda _: _close(page, dialog))
    try:
        setup = api("POST", "/auth/two-step/setup")
    except Exception as exc:
        problem = _Notice()
        problem.value = error_detail(exc)[0]
        _open(page, dialog, "Turn on two-step login", [problem.box], [cancel])
        return

    image = (ft.Image(src_base64=setup["qr_png_base64"], width=180, height=180) if IMAGE_TAKES_BASE64
             else ft.Image(src=base64.b64decode(setup["qr_png_base64"]), width=180, height=180))
    code = ft.TextField(hint_text="123456", autofocus=True, max_length=6, keyboard_type=ft.KeyboardType.NUMBER, **_field_style(ui))
    message = _Notice()

    def show_recovery_codes(codes):
        def finish():
            _close(page, dialog)
            on_done()

        _open(page, dialog, "Save your recovery codes", [
            _section(ui, ft.Icons.VPN_KEY_OUTLINED, "Recovery codes", [
                ui.hint("Each code works once, in place of the 6-digit code, if you lose your phone. "
                        "Write them down or print them now: they will not be shown again."),
                _code_box(ui, codes),
            ]),
        ], [_primary_button("I saved them", ft.Icons.CHECK, lambda _: finish())],
            subtitle="Two-step login is now on.", icon=ft.Icons.VERIFIED_USER_OUTLINED)

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
        _section(ui, ft.Icons.QR_CODE_SCANNER, "1 · Scan the QR code", [
            ui.hint("Scan this with an authenticator app such as Google Authenticator or Microsoft Authenticator."),
            ft.Row([ft.Container(image, padding=8, bgcolor=ft.Colors.WHITE, border_radius=8)], alignment=ft.MainAxisAlignment.CENTER),
            ui.hint("Can't scan? Type this key into the app:"),
            _code_box(ui, [setup["secret"]]),
        ]),
        _section(ui, ft.Icons.PIN_OUTLINED, "2 · Enter the code", [
            _labelled(ui, code, "6-digit code", ft.Icons.PIN_OUTLINED, required=True),
            ui.hint("The code the app shows for this account."),
        ]),
        message.box,
    ], [cancel, _primary_button("Turn on", ft.Icons.SHIELD_OUTLINED, lambda _: turn_on())],
        subtitle="Ask for a code from your phone each time you log in.", tall=True)


def open_turn_off_dialog(page, dialog, api, *, on_done):
    ui = TrackingWidgets(page)
    field_style = _field_style(ui)
    password = ft.TextField(hint_text="Your password", password=True, can_reveal_password=True, autofocus=True, **field_style)
    code = ft.TextField(hint_text="123456 or a recovery code", **field_style)
    message = _Notice()

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
        _section(ui, ft.Icons.LOCK_OUTLINE, "Confirm it's you", [
            _labelled(ui, password, "Password", ft.Icons.KEY, required=True),
            _labelled(ui, code, "6-digit code or recovery code", ft.Icons.PIN_OUTLINED, required=True),
        ]),
        message.box,
    ], [
        ft.TextButton("Cancel", on_click=lambda _: _close(page, dialog)),
        _danger_button("Turn off", ft.Icons.REMOVE_MODERATOR_OUTLINED, lambda _: turn_off()),
    ], subtitle="You will log in with your password alone.", icon=ft.Icons.REMOVE_MODERATOR_OUTLINED)


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
