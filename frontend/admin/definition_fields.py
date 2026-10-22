"""The Document type and Category fields of the registration and edit forms.

Document type offers Ordinance and Resolution, or "Other" with a box to type any other type. The
type decides whether a document is a measure (one containing "ordinance" or "resolution" is).
Category is typed freely, with the categories already in use offered as quick picks.
"""

import flet as ft

STANDARD_TYPES = ["Ordinance", "Resolution"]
OTHER = "Other"
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
    """A Dropdown of the standard types plus "Other", which shows a box to type the type in."""

    def __init__(self, style=None, *, value=None, used_before=(), label=None, width=None):
        style = style or {}
        sizing = {"width": width} if width else {}
        current = (value or "").strip()
        standard = next((name for name in STANDARD_TYPES if name.lower() == current.lower()), None)
        self.choice = ft.Dropdown(
            data="Document type", hint_text="Choose the type", label=label,
            options=[ft.dropdown.Option(name) for name in STANDARD_TYPES] + [ft.dropdown.Option(key=OTHER, text="Other (type it)")],
            value=standard or (OTHER if current else None), **style, **sizing,
        )
        examples = ", ".join(list(used_before)[:4])
        self.other = ft.TextField(
            data="Other document type", hint_text="e.g. " + (examples or "Memorandum, Letter, Executive Order"),
            value="" if standard else current, visible=bool(current) and not standard, **style, **sizing,
        )
        self.width = width
        self._handlers = []
        _on_select(self.choice, lambda _: self._changed(show_other=True))
        self.other.on_change = lambda _: self._changed()

    @property
    def value(self):
        """The type to save, or None when nothing is chosen."""
        if self.choice.value == OTHER:
            return " ".join((self.other.value or "").split()) or None
        return self.choice.value or None

    def on_change(self, handler):
        self._handlers.append(handler)

    def _changed(self, show_other=False):
        if show_other:
            self.other.visible = self.choice.value == OTHER
        for handler in self._handlers:
            handler(None)
        page = _page_of(self.choice)
        if page:
            page.update()

    def problem(self, required=True):
        if self.choice.value == OTHER and not self.value:
            return "Type the document type, or choose Ordinance or Resolution."
        if required and not self.value:
            return "Choose the document type."
        return None

    def lock(self, locked):
        self.choice.disabled = self.other.disabled = locked

    def control(self):
        return ft.Column([self.choice, self.other], spacing=8, tight=True, width=self.width)


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
