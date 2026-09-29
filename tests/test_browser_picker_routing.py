import types

from frontend.admin import app as admin_app


class BrowserFileStub:
    def __init__(self, name="sample.pdf", path=None):
        self.name = name
        self.path = path


def test_single_registration_picker_context_routes_to_single_state():
    calls = []

    def single_handler(event):
        calls.append("single")

    def bulk_handler(event):
        calls.append("bulk")

    def replacement_handler(event):
        calls.append("replacement")

    event = types.SimpleNamespace(files=[BrowserFileStub("single.pdf")])
    admin_app._route_file_picker_result("single_registration", event, single_handler, bulk_handler, replacement_handler)

    assert calls == ["single"]


def test_bulk_registration_picker_context_routes_to_bulk_state():
    calls = []

    def single_handler(event):
        calls.append("single")

    def bulk_handler(event):
        calls.append("bulk")

    def replacement_handler(event):
        calls.append("replacement")

    event = types.SimpleNamespace(files=[BrowserFileStub("bulk.pdf")])
    admin_app._route_file_picker_result("bulk_registration", event, single_handler, bulk_handler, replacement_handler)

    assert calls == ["bulk"]


def test_replacement_picker_context_routes_to_replacement_state():
    calls = []

    def single_handler(event):
        calls.append("single")

    def bulk_handler(event):
        calls.append("bulk")

    def replacement_handler(event):
        calls.append("replacement")

    event = types.SimpleNamespace(files=[BrowserFileStub("replacement.pdf")])
    admin_app._route_file_picker_result("replacement", event, single_handler, bulk_handler, replacement_handler)

    assert calls == ["replacement"]


def test_browser_file_without_path_or_bytes_requires_picker_upload():
    browser_file = BrowserFileStub("single.pdf", path=None)
    assert admin_app._browser_selected_file_needs_upload(browser_file) is True

    local_file = BrowserFileStub("local.pdf", path="C:/tmp/local.pdf")
    assert admin_app._browser_selected_file_needs_upload(local_file) is False
