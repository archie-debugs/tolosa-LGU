"""A dialog closed by clicking outside it or pressing Esc stays closed.

A page refresh reconnects to the same session, and Flet 0.21 redraws it from a snapshot of what
it last *sent* the browser. A dialog the browser closes by itself (outside click, Esc) is marked
closed on the server, but nothing is sent, so the snapshot still had it open and every refresh
showed it again, on whatever screen was up. The Close buttons send `open = False`, so they were fine.
Importing this module gives every AlertDialog and BottomSheet a dismiss handler that sends the
close too, then runs the dialog's own on_dismiss, if it has one.
"""
import functools

import flet as ft


def _mark_closed(own=None):
    def on_dismiss(e):
        e.control.open = False
        try:
            e.control.update()  # sends it, so a refresh's snapshot has the dialog closed
        except Exception:
            pass  # not on a page any more: nothing to redraw
        if own:
            own(e)
    return on_dismiss


def _install(cls):
    if getattr(cls, "_closes_on_dismiss", False):
        return
    original = cls.__init__

    @functools.wraps(original)
    def __init__(self, *args, **kwargs):
        kwargs["on_dismiss"] = _mark_closed(kwargs.get("on_dismiss"))
        original(self, *args, **kwargs)

    cls.__init__ = __init__
    cls._closes_on_dismiss = True


for _cls in (getattr(ft, "AlertDialog", None), getattr(ft, "BottomSheet", None)):
    if _cls is not None:
        _install(_cls)
