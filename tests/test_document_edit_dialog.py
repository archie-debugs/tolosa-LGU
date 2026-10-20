import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.document_edit import NO_CATEGORY, NO_TYPE, open_edit_document_dialog

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
            return {"categories": ["Finance", "Health"], "document_types": ["Ordinance", "Resolution"]}
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


def test_dialog_offers_real_reference_data_and_keeps_a_retired_value():
    dialog = open_dialog(FakeApi())

    assert dialog.open is True
    assert options(field(dialog, "Category")) == [NO_CATEGORY, "Finance", "Health", "Old Category"]
    assert field(dialog, "Category").value == "Old Category"
    assert options(field(dialog, "Document Type")) == [NO_TYPE, "Ordinance", "Resolution"]
    assert field(dialog, "Document Type").value == "Ordinance"
    assert field(dialog, "Priority").value == "High"


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
    field(dialog, "Category").value = NO_CATEGORY
    field(dialog, "Document Type").value = "Resolution"

    press(dialog, "Save changes")

    method, path, kwargs = api.calls[-1]
    assert (method, path) == ("PUT", "/documents/7")
    payload = kwargs["json"]
    assert payload["title"] == "Ordinance No. 7, amended"
    assert payload["category"] is None
    assert payload["document_type"] == "Resolution"
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
    press(dialog, "Save changes")
    assert "Category 'X' is not an active entry in Reference Data." in texts(dialog.content)
    assert dialog.open is True
