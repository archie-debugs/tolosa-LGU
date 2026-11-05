import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.screen import DIALOG_INSET, dialog_width


class Page:
    def __init__(self, width):
        self.width = width


def test_every_dialog_keeps_a_narrow_margin_from_the_screen_edge():
    # Flutter's default 40px a side left a phone's dialogs too narrow and clipped their content.
    assert ft.AlertDialog().inset_padding.left == DIALOG_INSET


def test_a_dialog_given_its_own_margin_keeps_it():
    assert ft.AlertDialog(inset_padding=ft.padding.all(40)).inset_padding.left == 40


def test_a_phone_dialog_is_the_screen_less_its_margins_and_padding():
    assert dialog_width(Page(390), 680) == 390 - 2 * DIALOG_INSET - 2 * 24
    assert dialog_width(Page(390), 680, padding=16) == 390 - 2 * DIALOG_INSET - 2 * 16


def test_a_wider_screen_keeps_the_desktop_width():
    assert dialog_width(Page(800), 680) == 680
