"""Opening a document works on iPhones, iPads and Macs.

A click goes to the server and back before `page.launch_url` reaches the browser, and the browser
opens the link in a new tab. Safari (and every iPhone browser, which all run on Safari's engine)
only lets a new tab open during the click itself, so it dropped these as pop-ups and nothing opened.
Opening in the same tab isn't a pop-up, so on Apple devices the link opens there instead; Back
returns to the app. A download still just saves the file. Other devices keep the new tab.
Importing this module changes `ft.Page.launch_url` everywhere.
"""
import functools

import flet as ft

APPLE = {"ios", "macos"}  # an iPad's Safari reports macOS


def _platform(page):
    try:
        return page._get_attr("platform")  # the visitor's device on the web, not the server's
    except Exception:
        return None


def _install():
    if getattr(ft.Page, "_opens_on_apple", False):
        return
    original = ft.Page.launch_url

    @functools.wraps(original)
    def launch_url(self, url, web_window_name=None, *args, **kwargs):
        if web_window_name is None and _platform(self) in APPLE:
            web_window_name = "_self"
        return original(self, url, web_window_name, *args, **kwargs)

    ft.Page.launch_url = launch_url
    ft.Page._opens_on_apple = True


_install()
