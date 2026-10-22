import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.definition_fields import OTHER
from frontend.admin.document_edit import open_edit_document_dialog

DOCUMENT = {
    "id": 7, "tracking_number": "DOC-000007", "title": "Ordinance No. 7", "document_number": "7", "series_year": 2025,
    "description": None, "category": "Old Category", "document_type": "Ordinance", "current_office": "Records Office",
    "assigned_to": None, "author": "Hon. Cruz", "priority": "High", "remarks": None, "session": None,
}


class DummyPage:
    def __init__(self):
        self.overlay = []
        self.theme_mode = None
        self.width = 1200

    def update(self, *args):
        pass


class FakeApi:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/documents/edit-options":
            return {"categories": ["Finance", "Health"], "document_types": ["Ordinance", "Resolution"],
                    "other_document_types": ["Memorandum"]}
        if self.error:
            raise Exception(self.error)
        return {"id": 7}


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", None) or []:
        yield from walk(child)
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)
    for action in getattr(control, "actions", None) or []:
        yield from walk(action)


def texts(control):
    return [c.value for c in walk(control) if isinstance(c, ft.Text) and c.value and c.visible is not False]


def field(dialog, label):
    return next(c for c in walk(dialog.content) if isinstance(c, (ft.TextField, ft.Dropdown)) and c.label == label)


def other_type(dialog):
    return next(c for c in walk(dialog.content) if isinstance(c, ft.TextField) and c.data == "Other document type")


def picks(dialog):
    return [c.data for c in walk(dialog.content) if isinstance(c, ft.TextButton)]


def options(dropdown):
    return [o.key or o.text for o in dropdown.options]


def press(dialog, label):
    button = next(b for b in walk(dialog) if getattr(b, "text", None) == label or getattr(b, "content", None) == label
                  or (isinstance(getattr(b, "content", None), ft.Text) and b.content.value == label))
    while getattr(button, "on_click", None) is None and getattr(button, "content", None) is not None:
        button = button.content
    button.on_click(None)


def open_dialog(api, saved=None):
    page = DummyPage()
    dialog = ft.AlertDialog()
    open_edit_document_dialog(page, dialog, api, DOCUMENT, on_saved=(lambda: saved.append(True)) if saved is not None else None)
    return dialog


def test_dialog_offers_the_standard_types_and_categories_used_before():
    dialog = open_dialog(FakeApi())

    assert dialog.open is True
    assert options(field(dialog, "Document Type")) == ["Ordinance", "Resolution", OTHER]
    assert field(dialog, "Document Type").value == "Ordinance"
    assert other_type(dialog).visible is False
    assert field(dialog, "Category").value == "Old Category"
    assert picks(dialog) == ["Finance", "Health"]
    assert field(dialog, "Priority").value == "High"


def test_dialog_shows_a_non_standard_type_in_the_other_box():
    dialog = ft.AlertDialog()
    open_edit_document_dialog(DummyPage(), dialog, FakeApi(), {**DOCUMENT, "document_type": "Executive Order"})

    assert field(dialog, "Document Type").value == OTHER
    assert (other_type(dialog).visible, other_type(dialog).value) == (True, "Executive Order")


def test_dialog_has_no_office_field_and_points_to_pass():
    dialog = open_dialog(FakeApi())

    labels = [c.label for c in walk(dialog.content) if isinstance(c, (ft.TextField, ft.Dropdown))]
    assert not any("Office" in (label or "") for label in labels)
    assert any("Records Office" in text and "Pass" in text for text in texts(dialog.content))


def test_saving_sends_the_edited_fields_without_offices():
    api = FakeApi()
    saved = []
    dialog = open_dialog(api, saved)
    field(dialog, "Title").value = "Ordinance No. 7, amended"
    field(dialog, "Category").value = ""
    field(dialog, "Document Type").value = OTHER
    other_type(dialog).value = "  Executive   Order "

    press(dialog, "Save changes")

    method, path, kwargs = api.calls[-1]
    assert (method, path) == ("PUT", "/documents/7")
    payload = kwargs["json"]
    assert payload["title"] == "Ordinance No. 7, amended"
    assert payload["category"] is None
    assert payload["document_type"] == "Executive Order"
    assert payload["series_year"] == "2025"
    assert "current_office" not in payload and "originating_office" not in payload
    assert saved == [True]
    assert dialog.open is False


def test_saving_needs_a_title_and_shows_the_backend_reason():
    api = FakeApi(error="Category 'X' is not an active entry in Reference Data.")
    dialog = open_dialog(api)

    field(dialog, "Title").value = "  "
    press(dialog, "Save changes")
    assert "Title is required." in texts(dialog.content)
    assert [c for c in api.calls if c[0] == "PUT"] == []

    field(dialog, "Title").value = "Ordinance No. 7"
    field(dialog, "Document Type").value = OTHER
    other_type(dialog).value = ""
    press(dialog, "Save changes")
    assert "Type the document type, or choose Ordinance or Resolution." in texts(dialog.content)
    assert [c for c in api.calls if c[0] == "PUT"] == []

    other_type(dialog).value = "Memorandum"
    press(dialog, "Save changes")
    assert "Category 'X' is not an active entry in Reference Data." in texts(dialog.content)
    assert dialog.open is True


def test_due_date_is_shown_edited_and_cleared():
    api = FakeApi()
    page = DummyPage()
    dialog = ft.AlertDialog()
    open_edit_document_dialog(page, dialog, api, {**DOCUMENT, "due_date": "2026-11-05"})
    due = field(dialog, "Due date")
    assert due.value == "2026-11-05"

    due.value = "05-11-2026"
    press(dialog, "Save changes")
    assert "Enter the due date as YYYY-MM-DD, for example 2026-11-05." in texts(dialog.content)
    assert [c for c in api.calls if c[0] == "PUT"] == []

    due.value = ""
    press(dialog, "Save changes")
    assert api.calls[-1][2]["json"]["due_date"] is None


def test_placeholder_dashes_from_the_details_screen_count_as_blank():
    # Document details passes the normalized record, where missing values are "-".
    api = FakeApi()
    page = DummyPage()
    dialog = ft.AlertDialog()
    open_edit_document_dialog(page, dialog, api, {**DOCUMENT, "category": "-", "document_type": "-", "author": "-"})

    assert field(dialog, "Category").value == ""
    assert field(dialog, "Document Type").value is None
    press(dialog, "Save changes")
    payload = api.calls[-1][2]["json"]
    assert (payload["category"], payload["document_type"], payload["author"]) == (None, None, None)
