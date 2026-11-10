"""Documents open on iPhones, iPads and Macs: there the link opens in the same tab, which Safari allows."""

import frontend.app  # noqa: F401  (applies frontend.open_links, as the running app does)
import flet as ft


class Browser:
    """Stands in for a page: the device it reports, and what gets sent to it."""

    def __init__(self, platform):
        self.platform, self.sent = platform, []

    def _get_attr(self, name):
        return self.platform if name == "platform" else None

    def _invoke_method(self, name, args, **_):
        self.sent.append((name, args))


def sent_for(platform, **kwargs):
    browser = Browser(platform)
    ft.Page.launch_url(browser, "https://example.test/doc.pdf", **kwargs)
    return browser.sent


def test_apple_devices_open_the_link_in_the_same_tab():
    for platform in ("ios", "macos"):
        assert sent_for(platform) == [("launchUrl", {"url": "https://example.test/doc.pdf", "web_window_name": "_self", "web_popup_window": "False"})]


def test_other_devices_still_get_a_new_tab():
    for platform in ("android", "windows", None):
        assert "web_window_name" not in sent_for(platform)[0][1]


def test_a_chosen_window_is_kept():
    assert sent_for("ios", web_window_name="_blank")[0][1]["web_window_name"] == "_blank"


def test_every_app_entry_point_installs_it():
    from pathlib import Path

    for app in ("frontend/app.py", "frontend/admin/app.py", "frontend/sb_member/app.py"):
        assert "import frontend.open_links" in Path(app).read_text(encoding="utf-8")
