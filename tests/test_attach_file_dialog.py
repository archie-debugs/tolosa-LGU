"""The Replace file dialog: pick a file, upload it to a temporary spot, then store it on the document."""

import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.attach_file import open_attach_file_dialog
from tests.test_document_edit_dialog import DummyPage, press, texts


class Files:
    """Stands in for registration.PickerFiles: picks a file and finishes its upload at once."""

    def __init__(self, error=None):
        self.uploads, self.error = [], error

    def pick(self, multiple, on_picked):
        on_picked([{"name": "Signed.pdf", "size": 1234}])

    def upload(self, uploads, on_progress):
        self.uploads.append(uploads)
        for name, _ in uploads:
            on_progress(name, None if self.error else 1.0, self.error)


class Api:
    def __init__(self, fail_on=None):
        self.calls, self.fail_on = [], fail_on

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == self.fail_on:
            raise Exception("Duplicate file content detected in document RES-000002")
        if path.endswith("create_tmp_uploads"):
            return {"files": [{"ok": True, "tmp_name": "tmp_1_Signed.pdf", "upload_url": "http://backend/documents/uploads/tmp/tmp_1_Signed.pdf?upload_token=x"}]}
        return {}


def opened(document, api, files=None):
    dialog, saved = ft.AlertDialog(), []
    open_attach_file_dialog(DummyPage(), dialog, api, files or Files(), document, on_saved=saved.append)
    return dialog, saved


def choose(dialog):
    press(dialog, "Choose file")


def test_a_document_with_a_file_has_it_replaced():
    api = Api()
    dialog, saved = opened({"id": 7, "attachments": [{"id": 3, "original_filename": "Old.pdf"}]}, api)
    assert dialog.title.value == "Replace File" and "Old.pdf" in texts(dialog.content)

    choose(dialog)
    press(dialog, "Replace File")

    assert api.calls[-1] == ("POST", "/documents/7/attachments/3/replace", {"data": {"tmp_name": "tmp_1_Signed.pdf"}})
    assert saved == ["File replaced."]


def test_a_refusal_or_a_failed_upload_stays_in_the_dialog():
    with_file = {"id": 7, "attachments": [{"id": 3, "original_filename": "Old.pdf"}]}
    dialog, saved = opened(with_file, Api(fail_on="/documents/7/attachments/3/replace"))
    press(dialog, "Replace File")
    assert "Choose a file first." in texts(dialog.content)
    choose(dialog)
    press(dialog, "Replace File")
    assert "Duplicate file content detected in document RES-000002" in texts(dialog.content)
    assert dialog.open is True and saved == []

    dialog, saved = opened(with_file, Api(), Files(error="connection lost"))
    choose(dialog)
    press(dialog, "Replace File")
    assert "The upload failed: connection lost" in texts(dialog.content) and saved == []


def test_trying_again_after_a_refusal_reuses_the_upload():
    api, files = Api(fail_on="/documents/7/attachments/3/replace"), Files()
    dialog, saved = opened({"id": 7, "attachments": [{"id": 3, "original_filename": "Old.pdf"}]}, api, files)
    choose(dialog)
    press(dialog, "Replace File")
    api.fail_on = None
    press(dialog, "Replace File")

    assert len(files.uploads) == 1 and saved == ["File replaced."]
    assert api.calls[-1] == ("POST", "/documents/7/attachments/3/replace", {"data": {"tmp_name": "tmp_1_Signed.pdf"}})
