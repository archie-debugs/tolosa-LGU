"""Screen sizes the admin screens lay themselves out for.

A phone is narrower than PHONE_WIDTH, a tablet narrower than DESKTOP_WIDTH (an upright
tablet), and anything wider is a desktop (including a tablet held sideways). Screens read
the size when they are built; the shell rebuilds the open screen when the size changes.
"""

PHONE_WIDTH = 600
DESKTOP_WIDTH = 1024

# A dialog's margin from the screen's edge; frontend/admin/app.py sets it on every ft.AlertDialog.
DIALOG_INSET = 12

PHONE = "phone"
TABLET = "tablet"
DESKTOP = "desktop"


def screen_size(page) -> str:
    width = getattr(page, "width", None) or DESKTOP_WIDTH
    if width < PHONE_WIDTH:
        return PHONE
    if width < DESKTOP_WIDTH:
        return TABLET
    return DESKTOP


def is_phone(page) -> bool:
    return screen_size(page) == PHONE


def dialog_width(page, desktop_width, padding=24):
    """A dialog content's width: `desktop_width`, or on a phone the screen less the dialog's
    margins and its `padding` on each side (24 is Flutter's default content padding)."""
    if not is_phone(page):
        return desktop_width
    return max(240, (page.width or PHONE_WIDTH) - 2 * DIALOG_INSET - 2 * padding)
