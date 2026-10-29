from datetime import date

import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.registration import open_multiple_register_dialog, open_register_dialog

TODAY = date(2026, 10, 20)
MAYOR = {"id": 2, "name": "Office of the Mayor"}


class DummyPage:
    def __init__(self):
        self.controls = []
        self.overlay = []
        self.theme_mode = None
        self.width = 1200
        self.height = 900
        self.launched = []

    def update(self, *args):
        pass

    def launch_url(self, url):
        self.launched.append(url)


class FakeFiles:
    def __init__(self):
        self.on_progress = None
        self.on_picked = None
        self.uploads = []

    def pick(self, multiple, on_picked):
        self.multiple = multiple
        self.on_picked = on_picked

    def upload(self, uploads, on_progress):
        self.uploads.append(uploads)
        self.on_progress = on_progress


class FakeApi:
    def __init__(self, options=None):
        self.calls = []
        self.options = options or {"offices": [MAYOR], "default_office_id": 2, "office_locked": True,
                                   "categories": ["Finance"], "document_types": ["Ordinance", "Resolution"]}
        self.duplicates = []  # tracking numbers the backend reports as having the same number
        self.confirm_results = []
        self.next_id = 1

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/documents/registration/options":
            return self.options
        if path == "/documents/register":
            if self.duplicates and kwargs["data"].get("allow_duplicate_number") != "true":
                raise Exception({"message": "used", "duplicate_number": True, "documents": self.duplicates})
            return self.document(kwargs["data"]["title"])
        if path == "/documents/uploads/create_tmp_uploads":
            return {"files": [
                {"filename": f["filename"], "ok": True, "tmp_name": f"tmp_{f['filename']}", "upload_url": f"http://backend/up/{f['filename']}"}
                if not f["filename"].endswith(".txt") else {"filename": f["filename"], "ok": False, "reason": "Unsupported extension"}
                for f in kwargs["json"]["files"]
            ]}
        if path == "/documents/bulk-register/confirm_tmp":
            return self.confirm_results.pop(0)(kwargs["json"]) if self.confirm_results else self.register_all(kwargs["json"])
        if path == "/documents/qr/labels/download-token":
            return {"download_url": "http://backend/labels.pdf"}
        raise AssertionError((method, path))

    def document(self, title):
        doc = {"id": self.next_id, "tracking_number": f"DOC-{self.next_id:06d}", "title": title}
        self.next_id += 1
        return doc

    def register_all(self, payload):
        docs = [{**self.document(spec["title"]), "tmp_name": spec["tmp_name"]} for spec in payload["documents"]]
        return {"registered": len(docs), "documents": docs, "errors": []}

    def posted(self, path):
        return [kwargs for method, called, kwargs in self.calls if called == path and method == "POST"]


def walk(control, seen=None):
    seen = seen if seen is not None else set()
    if control is None or id(control) in seen:
        return
    seen.add(id(control))
    yield control
    for attribute in ("controls", "content", "actions", "title"):
        child = getattr(control, attribute, None)
        for item in child if isinstance(child, list) else [child]:
            if item is not None and hasattr(item, "_get_control_name"):
                yield from walk(item, seen)


def texts(dialog):
    return [c.value for c in walk(dialog) if type(c).__name__ == "Text" and isinstance(c.value, str)]


def label(control):
    if isinstance(control, ft.Container) and control.content is not None and not isinstance(control.content, str):
        control = control.content
    return getattr(control, "text", None) or (control.content if isinstance(getattr(control, "content", None), str) else None)


def button(dialog, text):
    """The button as placed in the dialog: on Flet 0.21 app.py's ft.Button wraps it in a Container."""
    for control in walk(dialog):
        if label(control) == text:
            return control
    raise AssertionError(f"no button {text!r} in {[label(c) for c in walk(dialog) if label(c)]}")


def find_button(dialog, text):
    for control in walk(dialog):
        if label(control) == text:
            return control
    return None


def field(dialog, name):
    """A field by its name: the form draws names above the fields and keeps them in `data`."""
    return next(c for c in walk(dialog) if type(c).__name__ in ("TextField", "Dropdown") and name in (c.label, c.data))


def click(control):
    (control.content if isinstance(control, ft.Container) else control).on_click(None)


def press(dialog, text):
    click(button(dialog, text))


REQUIRED = {"Referred to": "SB Secretary", "Author": "Hon. Cruz"}
SENT = {"assigned_to": "SB Secretary", "action_required": "None", "author": "Hon. Cruz"}


def fill_required(dialog):
    """Fill the fields every registration needs, so a test only sets what it is about."""
    for name, value in REQUIRED.items():
        field(dialog, name).value = value


def open_single(api=None, **kwargs):
    page, dialog, files, api = DummyPage(), ft.AlertDialog(), FakeFiles(), api or FakeApi()
    opened = []
    open_register_dialog(page, dialog, api, files, today=TODAY, open_details=opened.append, can_print_qr=True, **kwargs)
    if dialog.content is not None and any(type(c).__name__ == "TextField" and c.data == "Author" for c in walk(dialog)):
        fill_required(dialog)
    return page, dialog, files, api, opened


def test_an_employee_registers_a_record_into_their_own_office():
    page, dialog, files, api, opened = open_single()
    office = field(dialog, "Office")
    assert (office.value, office.disabled) == ("2", True)
    assert field(dialog, "Year").value == "2026"
    assert "Without a file, only the record is registered." in texts(dialog)

    field(dialog, "Title").value = "Market code"
    press(dialog, "Register")

    data = api.posted("/documents/register")[0]["data"]
    assert data == {"title": "Market code", "series_year": "2026", "document_type": "Ordinance", "office_id": "2", "stage": "Filed", **SENT}
    assert "DOC-000001" in texts(dialog) and "Document registered" in texts(dialog)
    press(dialog, "QR label")
    assert page.launched == ["http://backend/labels.pdf"]
    press(dialog, "View details")
    assert opened == [{"id": 1}] and dialog.open is False


def test_a_number_already_used_warns_and_can_be_registered_anyway():
    api = FakeApi()
    api.duplicates = ["DOC-000004"]
    page, dialog, files, api, _ = open_single(api)
    field(dialog, "Title").value = "Ordinance No. 7 on markets"
    press(dialog, "Register")

    assert "A document with the same number is already registered" in texts(dialog)
    assert "DOC-000004" in texts(dialog)
    press(dialog, "Register anyway")
    assert api.posted("/documents/register")[1]["data"]["allow_duplicate_number"] == "true"
    assert "Document registered" in texts(dialog)


def test_a_document_with_its_file_registers_once_the_upload_finishes():
    page, dialog, files, api, _ = open_single()
    press(dialog, "Choose file")
    files.on_picked([{"name": "Ordinance_on_parking.pdf", "size": 2048}])
    assert field(dialog, "Title").value == "Ordinance on parking"

    press(dialog, "Register")
    assert files.uploads == [[("Ordinance_on_parking.pdf", "http://backend/up/Ordinance_on_parking.pdf")]]
    register = button(dialog, "Uploading…")
    assert register.disabled is True
    press_again = api.posted("/documents/bulk-register/confirm_tmp")
    assert press_again == []

    files.on_progress("Ordinance_on_parking.pdf", 0.5, None)
    assert find_button(dialog, "Uploading 50%") is not None
    files.on_progress("Ordinance_on_parking.pdf", 1.0, None)
    payload = api.posted("/documents/bulk-register/confirm_tmp")[0]["json"]
    assert payload["documents"] == [{"tmp_name": "tmp_Ordinance_on_parking.pdf", "series_year": 2026, "title": "Ordinance on parking"}]
    assert payload["office_id"] == 2 and payload["allow_duplicate_number"] is False
    assert "DOC-000001" in texts(dialog)


def test_an_employee_without_an_office_is_told_why_they_cannot_register():
    api = FakeApi({"offices": [], "default_office_id": None, "office_locked": True, "categories": [], "document_types": []})
    page, dialog, files, api, _ = open_single(api)
    assert any("not assigned to an office" in text for text in texts(dialog))
    assert button(dialog, "Register").disabled is True


def open_multiple(api=None):
    page, dialog, files, api = DummyPage(), ft.AlertDialog(), FakeFiles(), api or FakeApi()
    registered = []
    open_multiple_register_dialog(page, dialog, api, files, today=TODAY, on_registered=lambda: registered.append(1), can_print_qr=True)
    fill_required(dialog)
    return page, dialog, files, api, registered


def test_several_files_register_after_their_uploads_with_their_own_titles():
    page, dialog, files, api, registered = open_multiple()
    press(dialog, "Choose files")
    files.on_picked([{"name": "ordinance-1.pdf", "size": 1}, {"name": "ordinance-2.pdf", "size": 1}, {"name": "notes.txt", "size": 1}])

    assert "Only PDF, DOC and DOCX files can be registered." in texts(dialog)
    assert button(dialog, "Waiting for uploads…").disabled is True
    files.on_progress("ordinance-1.pdf", 1.0, None)
    assert button(dialog, "Waiting for uploads…").disabled is True
    files.on_progress("ordinance-2.pdf", None, None)
    register = button(dialog, "Register 2 documents")
    assert register.disabled is False

    titles = [c for c in walk(dialog) if type(c).__name__ == "TextField" and c.label == "Title"]
    titles[0].value = "Ordinance on roads"
    titles[0].on_change(type("E", (), {"control": titles[0]})())
    press(dialog, "Register 2 documents")

    specs = api.posted("/documents/bulk-register/confirm_tmp")[0]["json"]["documents"]
    assert [spec["title"] for spec in specs] == ["Ordinance on roads", "ordinance 2"]
    assert "Registered DOC-000001" in texts(dialog) and "Registered DOC-000002" in texts(dialog)
    assert find_button(dialog, "QR labels").visible is True
    assert registered == [1]


def test_files_whose_number_is_used_can_be_retried_on_their_own():
    api = FakeApi()

    def one_duplicate(payload):
        first, second = payload["documents"]
        doc = {**api.document(first["title"]), "tmp_name": first["tmp_name"]}
        return {"registered": 1, "documents": [doc], "errors": [
            {"tmp_name": second["tmp_name"], "filename": "ordinance b.pdf", "duplicate_number": True, "documents": ["DOC-000009"], "reason": "used"}]}

    api.confirm_results.append(one_duplicate)
    page, dialog, files, api, _ = open_multiple(api)
    press(dialog, "Choose files")
    files.on_picked([{"name": "ordinance a.pdf", "size": 1}, {"name": "ordinance b.pdf", "size": 1}])
    files.on_progress("ordinance a.pdf", 1.0, None)
    files.on_progress("ordinance b.pdf", 1.0, None)
    press(dialog, "Register 2 documents")

    assert "Number already used" in texts(dialog)
    assert "Same type, number and year as DOC-000009." in texts(dialog)
    retry = button(dialog, "Register the other 1")
    click(retry)
    assert len(api.posted("/documents/bulk-register/confirm_tmp")) == 1, "nothing is sent until the user decides"

    box = next(c for c in walk(dialog) if type(c).__name__ == "Checkbox")
    box.value = True
    box.on_change(type("E", (), {"control": box})())
    press(dialog, "Register the other 1")
    retried = api.posted("/documents/bulk-register/confirm_tmp")[1]["json"]
    assert retried["tmp_names"] == ["tmp_ordinance b.pdf"] and retried["allow_duplicate_number"] is True
    assert "Registered DOC-000001" in texts(dialog) and "Registered DOC-000002" in texts(dialog)
    assert all(c.disabled for c in walk(dialog) if type(c).__name__ == "TextField" and c.label == "Title")



def test_the_forms_ask_for_no_number_priority_due_date_or_stage():
    for opened in (open_single(FakeApi(MEASURE_OPTIONS)), open_multiple(FakeApi(MEASURE_OPTIONS))):
        dialog = opened[1]
        names = {c.data or c.label for c in walk(dialog) if type(c).__name__ in ("TextField", "Dropdown")}
        assert not names & {"Number", "Priority", "Due date", "Stage"}, names


MEASURE_OPTIONS = {"offices": [MAYOR], "default_office_id": 2, "office_locked": True, "categories": [],
                   "document_types": ["Ordinance", "Resolution"],
                   "measure_stages": {"ordinance": ["Filed", "First Reading", "Approved"], "resolution": ["Filed", "Adopted"]}}


def choose(dropdown, value):
    dropdown.value = value
    (getattr(dropdown, "on_change", None) or getattr(dropdown, "on_select", None))(None)


def test_a_measure_is_registered_at_filed_and_other_documents_have_no_stage():
    page, dialog, files, api, _ = open_single(FakeApi(MEASURE_OPTIONS))
    field(dialog, "Title").value = "Market code"
    press(dialog, "Register")
    assert api.posted("/documents/register")[0]["data"]["stage"] == "Filed"

    page, dialog, files, api, _ = open_single(FakeApi(MEASURE_OPTIONS))
    choose(field(dialog, "Document type"), "Letter Request")
    field(dialog, "Title").value = "Office memo"
    press(dialog, "Register")
    assert "stage" not in api.posted("/documents/register")[0]["data"]


def test_a_measure_registered_with_its_file_sends_its_stage():
    page, dialog, files, api, _ = open_single(FakeApi(MEASURE_OPTIONS))
    press(dialog, "Choose file")
    files.on_picked([{"name": "Parking.pdf", "size": 2048}])
    press(dialog, "Register")
    files.on_progress("Parking.pdf", 1.0, None)

    assert api.posted("/documents/bulk-register/confirm_tmp")[0]["json"]["stage"] == "Filed"


def test_the_type_is_ordinance_resolution_or_letter_request_and_there_is_no_category():
    page, dialog, files, api, _ = open_single(FakeApi(MEASURE_OPTIONS | {"categories": ["Finance", "Health"]}))
    assert not any(c.data == "Category" for c in walk(dialog) if type(c).__name__ == "TextField")
    assert not any(c.data == "Other document type" for c in walk(dialog) if type(c).__name__ == "TextField")
    kind = field(dialog, "Document type")
    assert [option.key or option.text for option in kind.options] == ["Ordinance", "Resolution", "Letter Request"]

    choose(kind, "Letter Request")
    field(dialog, "Title").value = "Request for road repair"
    press(dialog, "Register")
    data = api.posted("/documents/register")[0]["data"]
    assert data["document_type"] == "Letter Request" and "category" not in data and "stage" not in data


def test_every_field_but_the_description_must_be_filled_before_registering():
    page, dialog, files, api, _ = open_single()
    field(dialog, "Title").value = "Market code"
    for name in ("Author", "Referred to"):
        field(dialog, name).value = " "
    press(dialog, "Register")
    assert "Fill in the required fields: Referred to, Author." in texts(dialog)
    assert api.posted("/documents/register") == []

    field(dialog, "Referred to").value, field(dialog, "Author").value = "SB Secretary", "Hon. Cruz"
    press(dialog, "Register")
    assert len(api.posted("/documents/register")) == 1


def test_several_files_of_a_non_measure_register_without_numbers():
    page, dialog, files, api, registered = open_multiple()
    choose(field(dialog, "Document type"), "Letter Request")
    press(dialog, "Choose files")
    files.on_picked([{"name": "request memo.pdf", "size": 10}])
    files.on_progress("request memo.pdf", 1.0, None)

    press(dialog, "Register 1 document")
    payload = api.posted("/documents/bulk-register/confirm_tmp")[0]["json"]
    assert payload["documents"] == [{"tmp_name": "tmp_request memo.pdf", "series_year": 2026, "title": "request memo"}]
    assert not {"priority", "due_date", "stage"} & set(payload)
    assert registered == [1]


def test_registering_from_a_type_page_starts_with_that_type_and_it_can_still_change():
    page, dialog, files, api, _ = open_single(FakeApi(MEASURE_OPTIONS), document_type="Resolution")
    kind = field(dialog, "Document type")
    assert kind.value == "Resolution"

    choose(kind, "Letter Request")
    field(dialog, "Title").value = "Request for road repair"
    press(dialog, "Register")
    assert api.posted("/documents/register")[0]["data"]["document_type"] == "Letter Request"

    open_multiple_register_dialog(DummyPage(), dialog, FakeApi(MEASURE_OPTIONS), FakeFiles(), today=TODAY, document_type="Letter Request")
    assert field(dialog, "Document type").value == "Letter Request"


def test_a_batch_leaves_out_a_file_named_for_another_type_and_asks_a_title_for_an_unnamed_one():
    page, dialog, files, api, _ = open_multiple()
    press(dialog, "Choose files")
    files.on_picked([{"name": "Ordinance No. 4.pdf", "size": 1}, {"name": "Resolution No. 5.pdf", "size": 1}, {"name": "scan_0012.pdf", "size": 1}])
    for name in ("Ordinance No. 4.pdf", "Resolution No. 5.pdf", "scan_0012.pdf"):
        files.on_progress(name, 1.0, None)

    press(dialog, "Register 3 documents")
    assert "Type a title that says Ordinance for: scan_0012.pdf" in texts(dialog)
    assert "Its name says Resolution, but this batch is Ordinances." in texts(dialog)
    assert api.posted("/documents/bulk-register/confirm_tmp") == []

    title = [c for c in walk(dialog) if type(c).__name__ == "TextField" and c.label == "Title"][2]
    title.value = "Ordinance on market fees"
    title.on_change(type("E", (), {"control": title})())
    press(dialog, "Register 3 documents")

    sent = api.posted("/documents/bulk-register/confirm_tmp")[0]["json"]
    assert sent["multiple"] is True
    assert [spec["title"] for spec in sent["documents"]] == ["Ordinance No. 4", "Ordinance on market fees"]
    assert field(dialog, "Document type").disabled is True, "the batch's type is fixed once a file registers"


def test_a_batch_opened_from_a_type_page_keeps_that_type():
    page, dialog, files, api = DummyPage(), ft.AlertDialog(), FakeFiles(), FakeApi(MEASURE_OPTIONS)
    open_multiple_register_dialog(page, dialog, api, files, today=TODAY, document_type="Resolution")

    kind = field(dialog, "Document type")
    assert (kind.value, kind.disabled) == ("Resolution", True)
    press(dialog, "Choose files")
    files.on_picked([{"name": "resolution-1.pdf", "size": 1}])
    files.on_progress("resolution-1.pdf", 1.0, None)
    fill_required(dialog)
    press(dialog, "Register 1 document")
    assert field(dialog, "Document type").disabled is True
