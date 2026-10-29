"""The Document type and Category fields of the registration and edit forms.

Document type is chosen from Ordinance, Resolution and Letter Request, the only types a document can
have; each counts its own tracking numbers. The type decides whether a document is a measure (an
ordinance or resolution is). Category is typed freely, with the categories already in use offered
as quick picks.
"""

import flet as ft

STANDARD_TYPES = ["Ordinance", "Resolution", "Letter Request"]
MAX_SUGGESTIONS = 8


def _page_of(control):
    """The control's page once it is on screen; newer Flet raises before that."""
    try:
        return control.page
    except Exception:
        return None


def _on_select(dropdown, handler):
    """Flet 0.21-0.28 call a Dropdown's on_change; newer releases call on_select."""
    if hasattr(dropdown, "on_change"):
        dropdown.on_change = handler
    else:
        dropdown.on_select = handler


class DocumentTypeField:
    """A Dropdown of the three types; a document saved with any other type has to be given one."""

    def __init__(self, style=None, *, value=None, label=None, width=None):
        style = style or {}
        sizing = {"width": width} if width else {}
        current = " ".join((value or "").split())
        standard = next((name for name in STANDARD_TYPES if name.lower() == current.lower()), None)
        self.choice = ft.Dropdown(
            data="Document type", hint_text="Choose the type", label=label,
            options=[ft.dropdown.Option(name) for name in STANDARD_TYPES], value=standard, **style, **sizing,
        )
        self.width = width
        self._handlers = []
        _on_select(self.choice, lambda _: self._changed())

    @property
    def value(self):
        """The type to save, or None when nothing is chosen."""
        return self.choice.value or None

    def on_change(self, handler):
        self._handlers.append(handler)

    def _changed(self):
        for handler in self._handlers:
            handler(None)
        page = _page_of(self.choice)
        if page:
            page.update()

    def problem(self, required=True):
        if required and not self.value:
            return "Choose the document type."
        return None

    def lock(self, locked):
        self.choice.disabled = locked

    def control(self):
        return self.choice


class CategoryField:
    """A free-text category with the categories already in use as quick picks underneath."""

    def __init__(self, style=None, *, value=None, used_before=(), label=None, width=None):
        style = style or {}
        sizing = {"width": width} if width else {}
        self.width = width
        self.text = ft.TextField(data="Category", hint_text="Type a category", label=label,
                                 value=(value or "").strip(), **style, **sizing)
        pick_style = ft.ButtonStyle(shape=ft.StadiumBorder(), side=ft.BorderSide(1, ft.Colors.BLUE_100), padding=ft.Padding(10, 0, 10, 0))
        self.picks = [ft.TextButton(name, data=name, height=26, style=pick_style, on_click=lambda _, name=name: self.pick(name))
                      for name in list(used_before)[:MAX_SUGGESTIONS]]

    @property
    def value(self):
        return " ".join((self.text.value or "").split()) or None

    def pick(self, name):
        self.text.value = name
        page = _page_of(self.text)
        if page:
            page.update()

    def lock(self, locked):
        self.text.disabled = locked
        for button in self.picks:
            button.disabled = locked

    def control(self):
        rows = [self.text]
        if self.picks:
            rows.append(ft.Text("Used before:", size=11, color=ft.Colors.BLUE_GREY_500))
            rows.append(ft.Row(self.picks, spacing=6, run_spacing=6, wrap=True))
        return ft.Column(rows, spacing=6, tight=True, width=self.width)
