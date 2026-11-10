import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

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


def name(control):
    """A field's name: drawn above it and kept in `data`, or its own label."""
    return str(control.label or control.data or "")


def field(dialog, label):
    return next(c for c in walk(dialog.content) if isinstance(c, (ft.TextField, ft.Dropdown)) and name(c).lower() == label.lower())


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


def test_dialog_offers_the_standard_types():
    dialog = open_dialog(FakeApi())

    assert dialog.open is True
    assert options(field(dialog, "Document Type")) == ["Ordinance", "Resolution", "Letter Request"]
    assert field(dialog, "Document Type").value == "Ordinance"


def test_number_category_priority_and_due_date_are_not_edited_so_saving_keeps_them():
    # The backend only changes the fields it is sent, so leaving these out keeps their current values.
    api = FakeApi()
    dialog = open_dialog(api)

    labels = {name(c).lower() for c in walk(dialog.content) if isinstance(c, (ft.TextField, ft.Dropdown))}
    assert not labels & {"document number", "category", "priority", "due date"}
    assert not picks(dialog)
    press(dialog, "Save changes")
    payload = api.calls[-1][2]["json"]
    assert not payload.keys() & {"document_number", "category", "category_id", "priority", "due_date"}


def test_dialog_offers_only_the_three_types_so_another_type_must_be_replaced():
    dialog = ft.AlertDialog()
    open_edit_document_dialog(DummyPage(), dialog, FakeApi(), {**DOCUMENT, "document_type": "Executive Order"})

    assert field(dialog, "Document Type").value is None
    assert options(field(dialog, "Document Type")) == ["Ordinance", "Resolution", "Letter Request"]


def test_dialog_has_no_office_field_and_points_to_pass():
    dialog = open_dialog(FakeApi())

    labels = [name(c) for c in walk(dialog.content) if isinstance(c, (ft.TextField, ft.Dropdown))]
    assert not any("Office" in label for label in labels)
    assert any("Records Office" in text and "Pass" in text for text in texts(dialog.content))


def test_saving_sends_the_edited_fields_without_offices():
    api = FakeApi()
    saved = []
    dialog = open_dialog(api, saved)
    field(dialog, "Title").value = "Ordinance No. 7, amended"
    field(dialog, "Document Type").value = "Letter Request"

    press(dialog, "Save changes")

    method, path, kwargs = api.calls[-1]
    assert (method, path) == ("PUT", "/documents/7")
    payload = kwargs["json"]
    assert payload["title"] == "Ordinance No. 7, amended"
    assert payload["document_type"] == "Letter Request"
    assert payload["series_year"] == "2025"
    assert "current_office" not in payload and "originating_office" not in payload
    assert saved == [True]
    assert dialog.open is False


def test_saving_needs_a_title_and_shows_the_backend_reason():
    api = FakeApi(error="Series year must be a four-digit year.")
    dialog = open_dialog(api)

    field(dialog, "Title").value = "  "
    press(dialog, "Save changes")
    assert "Title is required." in texts(dialog.content)
    assert [c for c in api.calls if c[0] == "PUT"] == []

    field(dialog, "Title").value = "Ordinance No. 7"
    press(dialog, "Save changes")
    assert "Series year must be a four-digit year." in texts(dialog.content)
    assert dialog.open is True


def test_placeholder_dashes_from_the_details_screen_count_as_blank():
    # Document details passes the normalized record, where missing values are "-".
    api = FakeApi()
    page = DummyPage()
    dialog = ft.AlertDialog()
    open_edit_document_dialog(page, dialog, api, {**DOCUMENT, "document_type": "-", "author": "-"})

    assert field(dialog, "Document Type").value is None
    press(dialog, "Save changes")
    payload = api.calls[-1][2]["json"]
    assert (payload["document_type"], payload["author"]) == (None, None)


def test_status_and_action_required_are_chosen_and_saved():
    api = FakeApi()
    dialog = open_dialog(api)
    assert field(dialog, "Referred To").value == ""
    assert options(field(dialog, "Status")) == ["For information", "Approved", "Completed", "Posted"]
    assert field(dialog, "Action Required").value is None

    field(dialog, "Status").value = "Completed"
    field(dialog, "Action Required").value = "For Agenda"
    field(dialog, "Referred To").value = "Vice Mayor"
    press(dialog, "Save changes")

    payload = api.calls[-1][2]["json"]
    assert (payload["status"], payload["action_required"], payload["assigned_to"]) == ("Completed", "For Agenda", "Vice Mayor")


def test_a_status_outside_the_choices_is_kept():
    dialog = ft.AlertDialog()
    open_edit_document_dialog(DummyPage(), dialog, FakeApi(), {**DOCUMENT, "status": "Archived"})

    assert field(dialog, "Status").value == "Archived"
    assert "Archived" in options(field(dialog, "Status"))


def test_earlier_remarks_are_shown_and_a_new_remark_is_sent_on_its_own():
    api = FakeApi()
    page = DummyPage()
    dialog = ft.AlertDialog()
    document = {**DOCUMENT, "remarks": "Returned for signature", "remark_history": [
        {"text": "Returned for signature", "author": "TolosaAdmin", "created_at": "2026-11-01T07:10:00+00:00"},
        {"text": "Received by SB Secretary", "author": "TolosaAdmin", "created_at": "2026-10-30T01:02:00+00:00"},
    ]}
    open_edit_document_dialog(page, dialog, api, document)
    shown = texts(dialog.content)
    assert shown.index("Returned for signature") < shown.index("Received by SB Secretary")
    assert any(t.startswith("TolosaAdmin · ") and "2026" in t for t in shown)
    assert field(dialog, "New remark").value in (None, "")

    field(dialog, "New remark").value = "  Signed by the Vice Mayor "
    press(dialog, "Save changes")

    payload = api.calls[-1][2]["json"]
    assert payload["new_remark"] == "Signed by the Vice Mayor"
    assert "remarks" not in payload


def test_an_empty_new_remark_sends_none():
    api = FakeApi()
    dialog = open_dialog(api)

    press(dialog, "Save changes")

    assert api.calls[-1][2]["json"]["new_remark"] is None


def test_a_row_without_history_fetches_it():
    class HistoryApi(FakeApi):
        def __call__(self, method, path, **kwargs):
            if method == "GET" and path == "/documents/7":
                self.calls.append((method, path, kwargs))
                return {"remark_history": [{"text": "From the server", "author": "admin", "created_at": None}]}
            return super().__call__(method, path, **kwargs)

    dialog = open_dialog(HistoryApi())

    assert "From the server" in texts(dialog.content)


class Files:
    """Stands in for registration.PickerFiles: picks `name` and finishes its upload at once."""

    def __init__(self, name="Ordinance No. 12 - Market Fees.pdf"):
        self.name, self.uploads = name, []

    def pick(self, multiple, on_picked):
        on_picked([{"name": self.name, "size": 1234}])

    def upload(self, uploads, on_progress):
        self.uploads.append(uploads)
        for name, _ in uploads:
            on_progress(name, 1.0, None)


class AttachApi(FakeApi):
    def __init__(self, fail_on=None):
        super().__init__()
        self.fail_on = fail_on

    def __call__(self, method, path, **kwargs):
        if path.endswith("create_tmp_uploads"):
            self.calls.append((method, path, kwargs))
            return {"files": [{"ok": True, "tmp_name": "tmp_1", "upload_url": "http://backend/documents/uploads/tmp/tmp_1?upload_token=x"}]}
        if path == self.fail_on:
            self.calls.append((method, path, kwargs))
            raise Exception("Duplicate file content detected in document RES-000002")
        return super().__call__(method, path, **kwargs)


def attach_dialog(api, files=None, saved=None):
    dialog = ft.AlertDialog()
    open_edit_document_dialog(DummyPage(), dialog, api, DOCUMENT, files=files or Files(),
                              on_saved=(lambda: saved.append(True)) if saved is not None else None)
    return dialog


def test_attaching_fills_the_title_from_the_file_and_keeps_the_other_details():
    api, saved = AttachApi(), []
    dialog = attach_dialog(api, saved=saved)
    assert "Attach File" in texts(dialog.title) and "No file chosen" in texts(dialog.content)
    assert field(dialog, "Author").value == "Hon. Cruz" and field(dialog, "Series Year").value == "2025"

    press(dialog, "Attach File")
    assert "Choose the file to attach." in texts(dialog.content)
    assert not [c for c in api.calls if c[0] in ("PUT", "POST")]

    press(dialog, "Choose file")
    assert field(dialog, "Title").value == "Ordinance No. 12 - Market Fees"
    press(dialog, "Attach File")

    puts = [c for c in api.calls if c[0] == "PUT"]
    assert puts[-1][2]["json"]["title"] == "Ordinance No. 12 - Market Fees"
    assert puts[-1][2]["json"]["author"] == "Hon. Cruz"
    assert api.calls[-1] == ("POST", "/documents/7/attachments", {"data": {"tmp_name": "tmp_1"}})
    assert dialog.open is False and saved == [True]


def test_a_shortened_file_name_leaves_the_title_and_says_why():
    dialog = attach_dialog(AttachApi(), files=Files("MUNICI~3.PDF"))
    press(dialog, "Choose file")
    assert field(dialog, "Title").value == "Ordinance No. 7"
    assert any("Windows shortened" in t for t in texts(dialog.content))


def test_a_refused_file_keeps_the_form_open_and_trying_again_reuses_the_upload():
    api, files, saved = AttachApi(fail_on="/documents/7/attachments"), Files(), []
    dialog = attach_dialog(api, files=files, saved=saved)
    press(dialog, "Choose file")
    press(dialog, "Attach File")
    assert "Duplicate file content detected in document RES-000002" in texts(dialog.content)
    assert dialog.open is True and saved == []

    # A browser sends a picked file only once, so the retry uses the file already uploaded.
    api.fail_on = None
    press(dialog, "Attach File")
    assert len(files.uploads) == 1
    assert api.calls[-1] == ("POST", "/documents/7/attachments", {"data": {"tmp_name": "tmp_1"}})
    assert saved == [True] and dialog.open is False
