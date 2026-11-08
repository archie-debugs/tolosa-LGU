import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.document_details import open_document_details
from tests.test_document_details_pass import DummyPage, walk


def document(**extra):
    return {"document": {"id": 7, "tracking_number": "RES-000002", "title": "Resolution", "is_public": False, "attachments": [], **extra},
            "location": {}, "events": [], "can": {}}


def open_details(payload, can_change_visibility=True, **kwargs):
    calls, changes = [], []

    def api(method, path, **kw):
        calls.append((method, path, kw.get("json")))
        if method == "PUT":
            payload["document"]["is_public"] = kw["json"]["is_public"]
            return {}
        return payload

    dialog = ft.AlertDialog()
    open_document_details(DummyPage(), dialog, api, 7, normalize=lambda doc: doc,
                          can_change_visibility=can_change_visibility, on_change=lambda: changes.append(1), **kwargs)
    return dialog, calls, changes


def button(dialog, label):
    return next((c for c in walk(dialog.content) if isinstance(c, ft.OutlinedButton) and c.text == label), None)


def test_make_public_then_private_from_the_details():
    dialog, calls, changes = open_details(document())

    button(dialog, "Make public").on_click(None)
    assert ("PUT", "/documents/7", {"is_public": True}) in calls
    assert changes == [1]
    assert button(dialog, "Make private") is not None and button(dialog, "Make public") is None
    assert "RES-000002 is now public." in [c.value for c in walk(dialog.content) if isinstance(c, ft.Text)]

    button(dialog, "Make private").on_click(None)
    assert ("PUT", "/documents/7", {"is_public": False}) in calls
    assert button(dialog, "Make public") is not None


def test_no_visibility_button_without_the_permission_or_on_an_archived_document():
    assert button(open_details(document(), can_change_visibility=False)[0], "Make public") is None
    assert button(open_details(document(archived=True))[0], "Make public") is None
