import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.documents import build_documents_view
from tests.test_account_menu_ui import click, clickable
from tests.test_documents_list_view import DummyPage, ITEM, walk
from tests.test_document_details_visibility import button, document, open_details


def build(width=1600, can_view_details=True):
    opened, selection = [], set()
    view, _ = build_documents_view(
        DummyPage(width), lambda *a, **k: {"items": [{**ITEM, "attachments": [{"id": 1, "original_filename": "a.pdf"}]}], "total": 1, "total_pages": 1},
        lambda content, **_: ft.Container(content), normalize=dict, selection=selection, loaded=[],
        can_archive=True, can_edit=True, can_download=True, can_view_details=can_view_details, open_details=opened.append,
        open_edit=lambda d: None, download=lambda d: None, archive=lambda d: None,
    )
    return view, opened, selection


def holder_of(view, target):
    """The nearest clickable control around `target`, if any."""
    def search(control, around):
        if control is target:
            return around
        here = control if isinstance(control, ft.Container) and clickable(control) else around
        children = list(getattr(control, "controls", None) or [])
        if isinstance(getattr(control, "content", None), ft.Control):
            children.append(control.content)
        for child in children:
            found = search(child, here)
            if found is not False:
                return found
        return False
    return search(view, None)


def test_ticking_a_box_only_selects_and_clicking_the_row_opens_details():
    for width in (1600, 400):  # desktop table and phone cards
        view, opened, selection = build(width)
        box = next(c for c in walk(view) if isinstance(c, ft.Checkbox) and c.tooltip is None)
        assert holder_of(view, box) is None, "the checkbox must not sit inside the row's clickable area"
        box.on_change(type("E", (), {"control": type("C", (), {"value": True})()})())
        assert selection == {1} and opened == []

        title = next(c for c in walk(view) if isinstance(c, ft.Text) and c.value == ITEM["title"])
        click(holder_of(view, title))
        assert [d["id"] for d in opened] == [1]


def test_no_view_or_more_buttons_when_the_row_opens_details_but_kept_without_details():
    for width in (1600, 400):
        view, _, _ = build(width)
        assert not [c for c in walk(view) if isinstance(c, (ft.PopupMenuButton, ft.IconButton)) and c.tooltip in ("More actions", "View details")]
        assert not [c for c in walk(view) if isinstance(c, ft.TextButton) and c.text == "View"]

        view, _, _ = build(width, can_view_details=False)
        assert [c for c in walk(view) if isinstance(c, ft.PopupMenuButton)]


def test_details_carry_the_actions_the_menu_had():
    pdf = [{"id": 3, "original_filename": "a.pdf", "mime_type": "application/pdf"}]
    done = []
    handlers = {name: (lambda d, n=name: done.append(n)) for name in ("print_document", "replace_file", "archive", "restore", "keep_or_delete", "delete_permanently")}

    dialog, _, _ = open_details(document(attachments=pdf), can_edit=True, can_print=True, open_edit=lambda d: None, **handlers)
    for label in ("Print", "Replace file", "Archive"):
        button(dialog, label).on_click(None)
    assert done == ["print_document", "replace_file", "archive"]
    assert button(dialog, "Restore") is None

    done.clear()
    dialog, _, _ = open_details(document(archived=True, retain_until="2027-01-01"), **handlers)
    for label in ("Restore", "Keep longer or delete", "Delete permanently"):
        button(dialog, label).on_click(None)
    assert done == ["restore", "keep_or_delete", "delete_permanently"]
    assert button(dialog, "Archive") is None

    dialog, _, _ = open_details(document(archived=True), restore=handlers["restore"])
    assert button(dialog, "Restore") is not None and button(dialog, "Delete permanently") is None


def test_a_document_without_a_file_offers_attach_file_where_one_with_a_file_offers_replace():
    done = []
    dialog, _, _ = open_details(document(attachments=[]), can_edit=True, replace_file=done.append)
    assert button(dialog, "Replace file") is None
    button(dialog, "Attach file").on_click(None)
    assert len(done) == 1

    for attachments, label in (([], "Attach file"), ([{"id": 1, "original_filename": "a.pdf"}], "Replace file")):
        view, _ = build_documents_view(
            DummyPage(1600), lambda *a, **k: {"items": [{**ITEM, "attachments": attachments}], "total": 1, "total_pages": 1},
            lambda content, **_: ft.Container(content), normalize=dict, selection=set(), loaded=[],
            can_edit=True, open_edit=lambda d: None, open_replace_attachment=lambda d: None,
        )
        menu = next(c for c in walk(view) if isinstance(c, ft.PopupMenuButton))
        labels = [t.value for item in menu.items for t in walk(item.content) if isinstance(t, ft.Text)]
        assert label in labels and {"Attach file", "Replace file"} - {label} & set(labels) == set()
