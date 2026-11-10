"""A dialog closed by clicking outside it or pressing Esc is marked closed, so a refresh doesn't reopen it."""

import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims and frontend.dialogs)
import flet as ft


class Event:
    def __init__(self, control):
        self.control = control


def dismiss(control):
    """What Flet does when the browser closes the dialog on its own."""
    handler = control.on_dismiss
    (getattr(handler, "handler", None) or handler)(Event(control))


def test_dismissing_a_dialog_marks_it_closed_and_sends_that():
    # Sending it matters: a refresh redraws from what was last sent, not from the server's state.
    for dialog in (ft.AlertDialog(title=ft.Text("Document details")), ft.BottomSheet(content=ft.Text("Menu"))):
        sent = []
        dialog.update = lambda d=dialog, s=sent: s.append(d.open)
        dialog.open = True
        dismiss(dialog)
        assert dialog.open is False and sent == [False]


def test_a_dialog_no_longer_on_a_page_is_dismissed_without_error():
    dialog = ft.AlertDialog(title=ft.Text("Gone"))
    dialog.open = True
    dismiss(dialog)  # update() raises off a page; the dialog is still marked closed
    assert dialog.open is False


def test_a_dialogs_own_dismiss_handler_still_runs():
    seen = []
    dialog = ft.AlertDialog(title=ft.Text("Pass"), on_dismiss=lambda e: seen.append(e.control.open))
    dialog.open = True
    dismiss(dialog)
    assert dialog.open is False and seen == [False]


def test_the_document_details_dialog_is_one_of_them():
    import inspect

    source = inspect.getsource(frontend.admin.app)
    assert "import frontend.dialogs" in source
    assert "documents_details_dialog = ft.AlertDialog(" in source
