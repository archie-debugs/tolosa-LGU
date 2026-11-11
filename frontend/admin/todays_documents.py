"""Documents for SB Members: the temporary documents employees set for SB Members on a day."""

from datetime import date, datetime, timedelta

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets, document_reference


def document_label(document):
    reference = document_reference(document)
    return f"{document.get('tracking_number') or '-'} · {reference}" if reference else (document.get("tracking_number") or "-")


def picked_date(value):
    """The day a DatePicker returned; newer Flet releases send it as a zoned time."""
    if isinstance(value, datetime):
        return (value.astimezone() if value.tzinfo else value).date()
    return value if isinstance(value, date) else None


def build_todays_documents_view(page, api, surface_card, today=None, open_details=None, files=None):
    """The day's temporary documents (ordinances and MOAs) and their archive, by date.

    Regular documents reach SB Members through each session's order of business, not a day's list.
    `api(method, path, **kwargs)` calls the main backend and returns parsed JSON or raises.
    `open_details(document)` opens a document's details, when the user may see them.
    `files` is a PickerFiles for uploading temporary MOAs."""
    # Imported here: temporary_documents uses document_label from this module.
    from frontend.admin.temporary_documents import TemporaryDocuments

    widgets = TrackingWidgets(page)
    today = today or date.today()
    state = {"date": today, "today": today}

    date_text = ft.Text(size=16 if widgets.phone else 19, weight=ft.FontWeight.BOLD, color=widgets.link_color())
    date_hint = widgets.hint("")
    date_hint.size = 13
    date_picker = ft.DatePicker(first_date=datetime(2020, 1, 1), last_date=datetime(2100, 12, 31))

    accent, tint, card_title, empty_state = _card_parts(widgets)

    def boxed(control):
        """A date-bar button in its own framed tile."""
        return ft.Container(
            content=control,
            padding=ft.Padding(4, 2, 4, 2),
            bgcolor=tint(),
            border=ft.border.all(1, widgets.line_color()),
            border_radius=12,
        )

    def go_to(day, update=True):
        state["date"] = day
        date_text.value = day.strftime("%A, %B %d, %Y")
        if day == state["today"]:
            date_hint.value = "Today: SB Members see this day's temporary documents now."
        elif day > state["today"]:
            date_hint.value = "SB Members will see them on that day."
        else:
            date_hint.value = "A past day, shown for reference. It can no longer be changed."
        temporary.load(day, state["today"], update=update)

    def pick_date(_=None):
        date_picker.value = datetime.combine(state["date"], datetime.min.time())
        (getattr(page, "open", None) or page.show_dialog)(date_picker)

    def on_date_picked(e):
        day = picked_date(e.control.value)
        if day and day != state["date"]:
            go_to(day)

    date_picker.on_change = on_date_picked

    previous_day = ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_color=accent(), tooltip="Previous day", on_click=lambda _: go_to(state["date"] - timedelta(days=1)))
    next_day = ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_color=accent(), tooltip="Next day", on_click=lambda _: go_to(state["date"] + timedelta(days=1)))
    pick_button = boxed(ft.IconButton(ft.Icons.CALENDAR_MONTH, icon_color=accent(), tooltip="Pick a date", on_click=pick_date))
    today_button = boxed(ft.TextButton("Today", icon=ft.Icons.TODAY, on_click=lambda _: go_to(state["today"]), style=ft.ButtonStyle(color=accent())))
    # A phone puts the day on its own, with the day buttons in a row underneath.
    date_bar = ft.Column(
        [
            ft.Column([date_text, date_hint], spacing=6),
            ft.Row([previous_day, next_day, pick_button, today_button], spacing=8, wrap=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ],
        spacing=10,
    ) if widgets.phone else ft.Row(
        [
            previous_day,
            ft.Column([date_text, date_hint], spacing=6, expand=True),
            next_day,
            pick_button,
            today_button,
        ],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    temporary = TemporaryDocuments(page, api, widgets, files, card_title, empty_state, open_details=open_details)
    go_to(today, update=False)
    return ft.Column(
        [
            widgets.banner("Documents for SB Members", "Temporary ordinances and MOAs for a day. They appear right away in the SB Member app.", ft.Icons.DESCRIPTION),
            surface_card(date_bar, padding=ft.Padding(14, 18, 18, 18)),
            surface_card(temporary.day_card, padding=20),
            surface_card(temporary.archive_card, padding=20),
        ],
        spacing=16,
    )


def _card_parts(widgets):
    """The page's accent and tint colours, card titles with a round icon badge, and empty-list boxes."""

    def accent():
        return widgets.tone(ft.Colors.BLUE_700, ft.Colors.BLUE_300)

    def tint():
        return widgets.tone("#F4F8FE", "#1B2430")

    def card_title(icon, title, *extra, subtitle=None):
        """A card's title with its round icon badge."""
        heading = ft.Row(
            [ft.Text(title, size=17, weight=ft.FontWeight.BOLD, color=widgets.link_color()), *extra],
            spacing=20, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        badge = ft.Container(
            content=ft.Icon(icon, size=24, color=accent()),
            width=44, height=44, border_radius=22,
            alignment=ft.Alignment(0, 0),
            bgcolor=ft.Colors.with_opacity(0.10, accent()),
        )
        lines = [heading, widgets.hint(subtitle)] if subtitle and not widgets.phone else [heading]
        return ft.Row([badge, ft.Column(lines, spacing=4, expand=True)], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def empty_state(message):
        return ft.Container(
            content=ft.Row(
                [ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=20, color=widgets.muted_color()), ft.Text(message, size=13, color=widgets.muted_color(), expand=True)],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=18,
            bgcolor=tint(),
            border=ft.border.all(1, widgets.line_color()),
            border_radius=10,
        )

    return accent, tint, card_title, empty_state


def build_archived_temporary_view(page, api, surface_card, today=None, open_details=None):
    """Archived Documents → Temporary Docs: the temporary documents of Documents for SB Members whose day
    has passed, the same archive card as on that page (view, keep 30 more days, delete)."""
    from frontend.admin.temporary_documents import TemporaryDocuments

    widgets = TrackingWidgets(page)
    today = today or date.today()
    _, _, card_title, empty_state = _card_parts(widgets)
    temporary = TemporaryDocuments(page, api, widgets, None, card_title, empty_state, open_details=open_details)
    temporary.load(today, today)
    return ft.Column(
        [
            widgets.banner("Archived Temporary Docs", "MOAs from Documents for SB Members whose day has passed. Ordinances are not archived.",
                           ft.Icons.INVENTORY_2_OUTLINED),
            # The day card is not on this page, so its messages ("Deleted for good.") show here.
            surface_card(ft.Column([temporary.notice_text, temporary.archive_card], spacing=12), padding=20),
        ],
        spacing=16,
    )
