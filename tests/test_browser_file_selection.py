import importlib.util
from pathlib import Path
from unittest.mock import patch


APP_PATH = Path(__file__).resolve().parents[1] / "frontend" / "admin" / "app.py"
SPEC = importlib.util.spec_from_file_location("frontend_admin_app", APP_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BrowserFile:
    def __init__(self, data=None, filename="upload.pdf"):
        self._data = data
        self.name = filename
        self.path = None
        self.size = 123 if data is not None else 0

    def read(self):
        return self._data


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="ok"):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_extract_browser_file_bytes_uses_selected_browser_file():
    payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    browser_file = BrowserFile(payload, "upload.pdf")

    data = MODULE._read_selected_file_bytes(browser_file)

    assert data == payload


def test_prepare_single_registration_upload_uses_browser_temp_upload_flow():
    browser_file = BrowserFile(filename="single.pdf")

    fake_response = FakeResponse(
        payload={
            "files": [{
                "filename": "single.pdf",
                "ok": True,
                "tmp_name": "tmp_123_single.pdf",
                "upload_url": "http://backend.example/documents/uploads/tmp/tmp_123_single.pdf?upload_token=abc",
                "upload_token": "abc",
            }]
        }
    )

    with patch.object(MODULE.requests, "post", return_value=fake_response):
        info = MODULE._prepare_single_registration_upload(browser_file, "single.pdf")

    assert info["tmp_name"] == "tmp_123_single.pdf"
    assert info["upload_url"].endswith("/documents/uploads/tmp/tmp_123_single.pdf?upload_token=abc")
    assert info["upload_token"] == "abc"
    assert info["filename"] == "single.pdf"
