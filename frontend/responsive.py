"""One column on phones and tablets, the same on every screen size below a desktop.

Screens give their controls `col={"xs": 12, "sm": 6, "md": 4, ...}` for ft.ResponsiveRow. Flet picks the
column count from the window's width, so a big phone sideways (576 px and up) or a tablet (768 px and
up) used to split into two or three narrow columns, squeezing their contents. Importing this module
makes every `col` keep its phone value (`xs`) until a desktop (Flet's `lg`, 992 px): below that,
screens stack their cards in one column, Facebook-style; desktops lay out exactly as before.

Flet 0.21 has no setting for the breakpoints, so this rewrites `col` as it is set. On a Flet whose
controls have no `col` property it does nothing.
"""
import threading

import flet as ft

DESKTOP_KEY = "lg"


def stack_below_desktop(col):
    """{"xs": 12, "md": 6} -> {"xs": 12, "lg": 6}: the tablet split only applies from a desktop."""
    if not isinstance(col, dict) or not ({"sm", "md"} & set(col)):
        return col
    result = {key: value for key, value in col.items() if key not in ("sm", "md")}
    desktop = col.get(DESKTOP_KEY, col.get("md", col.get("sm")))
    result.setdefault("xs", 12)
    result[DESKTOP_KEY] = desktop
    return result


def _install():
    owner = next((cls for cls in type.mro(ft.Control) if isinstance(cls.__dict__.get("col"), property)), None)
    if owner is None:
        return
    original = owner.__dict__["col"]
    if getattr(original.fset, "stacks_below_desktop", False):
        return

    def set_col(self, value):
        original.fset(self, stack_below_desktop(value))

    set_col.stacks_below_desktop = True
    owner.col = property(original.fget, set_col, original.fdel, original.__doc__)


_install()


def redraw_on_resize(page, view, rebuild, settle=0.3):
    """Redraw `view` with `rebuild()` once the window's width changes and settles: a page laid out
    for its width when built (the public pages) then follows a phone turned sideways or a resized
    window. Does nothing once `view` is no longer on the page."""
    if page is None:
        return
    built_width = getattr(page, "width", None)
    pending = []

    def redraw():
        if view not in page.controls or getattr(page, "width", None) == built_width:
            return
        page.clean()
        page.add(rebuild())
        page.update()

    def resized(_=None):
        for timer in pending:
            timer.cancel()
        pending[:] = [threading.Timer(settle, redraw)]
        pending[0].start()

    # Flet 0.28 names the resize event on_resized; other releases use on_resize.
    if hasattr(type(page), "on_resized"):
        page.on_resized = resized
    else:
        page.on_resize = resized
