import base64

import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.two_step import login_needs_code, open_turn_off_dialog, open_turn_on_dialog, two_step_row
from tests.test_account_menu_ui import DummyPage, find, texts, walk

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")


class Api:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail or {}

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path in self.fail:
            raise Exception(self.fail[path])
        if path == "/auth/two-step/setup":
            return {"secret": "ABCDEFGHIJKLMNOP", "uri": "otpauth://totp/x", "qr_png_base64": PNG}
        if path == "/auth/two-step/enable":
            return {"recovery_codes": ["aaaaa-11111", "bbbbb-22222"]}
        return {"two_step_enabled": False}


def press(dialog, label):
    button = next(b for b in walk(dialog) if label in texts(b) or getattr(b, "text", None) == label)
    button.on_click(None)


def test_turning_on_shows_the_qr_then_the_recovery_codes():
    page, dialog, api, done = DummyPage(), ft.AlertDialog(), Api(), []
    open_turn_on_dialog(page, dialog, api, on_done=lambda: done.append(True))

    assert dialog.open is True
    assert find(dialog.content, ft.Image)
    assert "ABCDEFGHIJKLMNOP" in " ".join(texts(dialog))
    code = find(dialog.content, ft.TextField)[0]
    code.value = " 123 456 "
    press(dialog, "Turn on")

    assert api.calls[-1] == ("POST", "/auth/two-step/enable", {"json": {"code": "123456"}})
    shown = " ".join(texts(dialog))
    assert "aaaaa-11111" in shown and "bbbbb-22222" in shown
    assert done == []
    press(dialog, "I saved them")
    assert dialog.open is False
    assert done == [True]


def test_turning_on_checks_the_code_and_shows_the_backend_reason():
    page, dialog = DummyPage(), ft.AlertDialog()
    api = Api(fail={"/auth/two-step/enable": "That code is not right."})
    open_turn_on_dialog(page, dialog, api, on_done=lambda: None)

    press(dialog, "Turn on")
    assert "Enter the 6-digit code from your app." in texts(dialog)
    assert [c[1] for c in api.calls] == ["/auth/two-step/setup"]

    find(dialog.content, ft.TextField)[0].value = "654321"
    press(dialog, "Turn on")
    assert "That code is not right." in texts(dialog)
    assert dialog.open is True


def test_setup_failure_is_explained():
    page, dialog = DummyPage(), ft.AlertDialog()
    open_turn_on_dialog(page, dialog, Api(fail={"/auth/two-step/setup": "Two-step login is available to Super Admins."}), on_done=lambda: None)
    assert "Two-step login is available to Super Admins." in texts(dialog)
    assert not find(dialog.content, ft.Image)


def test_turning_off_needs_the_password_and_a_code():
    page, dialog, api, done = DummyPage(), ft.AlertDialog(), Api(), []
    open_turn_off_dialog(page, dialog, api, on_done=lambda: done.append(True))
    password, code = find(dialog.content, ft.TextField)

    press(dialog, "Turn off")
    assert "Enter your password and a code." in texts(dialog)
    assert api.calls == []

    password.value, code.value = "pw123", "123456"
    press(dialog, "Turn off")
    assert api.calls == [("POST", "/auth/two-step/disable", {"json": {"password": "pw123", "code": "123456"}})]
    assert dialog.open is False
    assert done == [True]


def test_the_security_row_says_whether_it_is_on():
    page, dialog = DummyPage(), ft.AlertDialog()
    off = two_step_row(page, dialog, Api(), {"two_step_enabled": False}, on_changed=lambda: None)
    assert "Off" in texts(off) and "Turn on" in " ".join(texts(off) + [getattr(b, "text", "") or "" for b in walk(off)])

    on = two_step_row(page, dialog, Api(), {"two_step_enabled": True, "two_step_recovery_codes_left": 3}, on_changed=lambda: None)
    assert "On · 3 recovery codes left" in texts(on)


class Response:
    def __init__(self, status, headers):
        self.status_code, self.headers = status, headers


def test_login_knows_when_the_backend_asks_for_a_code():
    assert login_needs_code(Response(401, {"X-Two-Step": "required"}))
    assert not login_needs_code(Response(401, {}))
    assert not login_needs_code(Response(200, {}))
