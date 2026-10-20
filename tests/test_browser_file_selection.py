import importlib.util
from pathlib import Path


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


def test_extract_browser_file_bytes_uses_selected_browser_file():
    payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    browser_file = BrowserFile(payload, "upload.pdf")

    data = MODULE._read_selected_file_bytes(browser_file)

    assert data == payload
