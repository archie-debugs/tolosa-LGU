"""The Document details pop-up opens on the click with a spinner and pops in, then shows the details."""

import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft
import pytest

from frontend.admin.document_details import open_document_details
from tests.test_document_details_pass import HELD, DummyPage, walk


def test_it_opens_with_a_spinner_before_loading_then_pops_in_to_the_details():
    seen, dialog = [], ft.AlertDialog()

    def api(method, path, **kw):
        seen.append((dialog.open, any(isinstance(c, ft.ProgressRing) for c in walk(dialog.content))))
        return HELD

    open_document_details(DummyPage(), dialog, api, 7, normalize=lambda doc: doc)

    assert seen[0] == (True, True)  # already open, spinning, while the details load
    card = dialog.content
    assert (card.scale, card.opacity) == (1, 1) and card.animate_scale and card.animate_opacity
    controls = list(walk(card))
    assert not any(isinstance(c, ft.ProgressRing) for c in controls)
    assert "Ordinance No. 7" in [c.value for c in controls if isinstance(c, ft.Text)]
    close = next(c for c in controls if isinstance(c, ft.TextButton) and c.text == "Close")
    close.on_click(None)
    assert dialog.open is False


def test_a_failed_load_closes_the_pop_up_and_reports_the_error():
    def api(method, path, **kw):
        raise RuntimeError("server down")

    dialog = ft.AlertDialog()
    with pytest.raises(RuntimeError):
        open_document_details(DummyPage(), dialog, api, 7, normalize=lambda doc: doc)
    assert dialog.open is False
