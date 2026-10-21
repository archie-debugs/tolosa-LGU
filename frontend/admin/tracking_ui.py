"""Building blocks shared by the document tracking screens (QR Tracking, Office Dashboard)."""

from datetime import date, datetime, timezone

import flet as ft

# How each kind of tracking event is shown: (label, icon, colour).
EVENT_STYLES = {
    "sent": ("Sent", ft.Icons.SEND_OUTLINED, ft.Colors.BLUE_700),
    "received": ("Received", ft.Icons.MOVE_TO_INBOX_OUTLINED, ft.Colors.GREEN_700),
    "returned": ("Returned", ft.Icons.UNDO, ft.Colors.DEEP_ORANGE_700),
    "cancelled": ("Cancelled", ft.Icons.CANCEL_OUTLINED, ft.Colors.BLUE_GREY_600),
    "action": ("Action", ft.Icons.TASK_ALT, ft.Colors.INDIGO_600),
    "scan": ("Scanned", ft.Icons.QR_CODE_SCANNER, ft.Colors.TEAL_700),
    "unrecognized": ("Unrecognized scan", ft.Icons.ERROR_OUTLINE, ft.Colors.RED_700),
    "registered": ("Registered", ft.Icons.NOTE_ADD_OUTLINED, ft.Colors.BLUE_GREY_600),
}


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def local_time(value):
    """An API timestamp in this computer's time zone (naive values are UTC), or None."""
    parsed = parse_time(value)
    return parsed.astimezone() if parsed else None


def format_time(value):
    parsed = parse_time(value)
    return parsed.astimezone().strftime("%b %d, %I:%M %p") if parsed else "-"


def format_elapsed(value, now=None):
    """'2d 3h', '5h 12m' or '8m' since `value`."""
    parsed = parse_time(value)
    if not parsed:
        return "-"
    minutes = max(0, int(((now or datetime.now(timezone.utc)) - parsed).total_seconds() // 60))
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def event_summary(event):
    """One line describing a tracking event, e.g. 'Office A → Office B'."""
    office = event.get("office") or "-"
    kind = event.get("type")
    if kind == "sent":
        return f"{office} → {event.get('to_office') or '-'}"
    if kind in ("returned", "cancelled"):
        # Returned: the receiver sent it back to the sender. Cancelled: the sender called it back from the receiver.
        line = f"{office} returned it to {event.get('to_office') or '-'}" if kind == "returned" else f"{office} cancelled the handoff to {event.get('to_office') or '-'}"
        return line + (f" · {event['detail']}" if event.get("detail") else "")
    if kind in ("received", "registered"):
        return office
    if kind == "action":
        return f"{event.get('detail') or 'Action'} · {office}"
    return event.get("detail") or ""


# Due within this many days counts as "soon".
DUE_SOON_DAYS = 3
DUE_COLORS = {"overdue": ft.Colors.RED_700, "soon": ft.Colors.AMBER_800, "later": ft.Colors.BLUE_GREY_600}
DUE_DATE_HINT = "Enter the due date as YYYY-MM-DD, for example 2026-11-05."


def parse_due_date(value):
    """A date from 'YYYY-MM-DD', or None when blank or malformed."""
    text = str(value or "").strip()
    if len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def due_status(value, today=None):
    """('Due in 3 days', 'soon') for a due date, or None without one. Kinds: overdue, soon, later."""
    due = parse_due_date(value)
    if due is None:
        return None
    today = today or date.today()
    days = (due - today).days
    if days < 0:
        late = -days
        return f"Overdue · {late} day{'s' if late != 1 else ''}", "overdue"
    if days == 0:
        return "Due today", "soon"
    if days == 1:
        return "Due tomorrow", "soon"
    if days <= DUE_SOON_DAYS:
        return f"Due in {days} days", "soon"
    return f"Due {due.strftime('%b %d') if due.year == today.year else due.strftime('%b %d, %Y')}", "later"


def document_reference(item):
    """'Ordinance · No. 12 · s. 2025', leaving out what the document lacks."""
    return " · ".join(part for part in [
        item.get("document_type"),
        f"No. {item['document_number']}" if item.get("document_number") else None,
        f"s. {item['series_year']}" if item.get("series_year") else None,
    ] if part)


class TrackingWidgets:
    """Controls styled for the current theme.

    The shell themes a view once when it opens, so rows a screen renders later
    pick their night-mode colours here instead.
    """

    def __init__(self, page):
        self.page = page

    def tone(self, light, dark):
        return dark if self.page.theme_mode == ft.ThemeMode.DARK else light

    def heading_color(self):
        return self.tone(ft.Colors.BLUE_GREY_900, ft.Colors.BLUE_GREY_50)

    def body_color(self):
        return self.tone(ft.Colors.BLUE_GREY_800, ft.Colors.BLUE_GREY_200)

    def muted_color(self):
        return self.tone(ft.Colors.BLUE_GREY_500, ft.Colors.BLUE_GREY_400)

    def link_color(self):
        return self.tone(ft.Colors.BLUE_900, ft.Colors.BLUE_200)

    def line_color(self):
        return self.tone(ft.Colors.BLUE_GREY_100, ft.Colors.BLUE_GREY_700)

    def card_color(self):
        return self.tone(ft.Colors.WHITE, ft.Colors.GREY_900)

    def title(self, text):
        return ft.Text(text, size=15, weight=ft.FontWeight.BOLD, color=self.heading_color())

    def hint(self, text):
        return ft.Text(text, size=11, color=self.muted_color())

    def chip(self, text, color):
        return ft.Container(
            content=ft.Text(text, size=11, weight=ft.FontWeight.W_600, color=color),
            padding=ft.Padding(8, 3, 8, 3),
            bgcolor=ft.Colors.with_opacity(0.12, color),
            border_radius=10,
        )

    def kpi(self, title, value, detail, icon, accent, col=None):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=accent, size=18),
                            ft.Text(title, size=12, weight=ft.FontWeight.W_600, color=self.body_color()),
                        ],
                        spacing=6,
                    ),
                    ft.Text(str(value), size=26, weight=ft.FontWeight.BOLD, color=self.heading_color()),
                    ft.Text(detail, size=11, color=self.muted_color()),
                ],
                spacing=4,
            ),
            padding=14,
            bgcolor=self.card_color(),
            border=ft.Border(
                left=ft.BorderSide(4, accent),
                top=ft.BorderSide(1, self.line_color()),
                right=ft.BorderSide(1, self.line_color()),
                bottom=ft.BorderSide(1, self.line_color()),
            ),
            border_radius=10,
            col=col or {"xs": 6, "md": 4, "xl": 2},
        )

    def list_row(self, controls, on_click=None):
        return ft.Container(
            content=ft.Row(controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(4, 10, 4, 10),
            border=ft.Border(bottom=ft.BorderSide(1, self.line_color())),
            on_click=on_click,
            ink=on_click is not None,
        )

    def empty(self, message):
        return ft.Container(ft.Text(message, size=12, color=self.muted_color()), padding=ft.Padding(4, 12, 4, 12))

    def document_cell(self, item, expand=True):
        return ft.Column(
            [
                ft.Text(item.get("tracking_number") or "-", size=12, weight=ft.FontWeight.BOLD, color=self.link_color()),
                ft.Text(item.get("title") or "Untitled", size=12, color=self.body_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ],
            spacing=1,
            expand=expand,
        )

    def due_chip(self, item, today=None):
        """The document's due chip, or None when it has no due date or is archived."""
        status = None if item.get("archived") else due_status(item.get("due_date"), today)
        if status is None:
            return None
        text, kind = status
        return self.chip(text, DUE_COLORS[kind])

    def waiting_chip(self, item):
        """How long a handoff has waited for receipt, red once it is overdue."""
        waiting = format_elapsed(item.get("sent_at"))
        if item.get("overdue"):
            return self.chip(f"Overdue · {waiting}", ft.Colors.RED_700)
        return self.chip(waiting, ft.Colors.AMBER_800)

    def event_row(self, event, show_document, on_open=None):
        """A tracking event; selecting it calls `on_open(tracking_number)` when given."""
        label, icon, color = EVENT_STYLES.get(event.get("type"), ("Event", ft.Icons.CIRCLE_OUTLINED, ft.Colors.BLUE_GREY_600))
        details = [ft.Row([self.chip(label, color), ft.Text(event_summary(event), size=12, color=self.body_color(), expand=True)], spacing=8)]
        if show_document and event.get("tracking_number"):
            details.append(ft.Text(f"{event['tracking_number']} · {event.get('title') or 'Untitled'}", size=11, color=self.muted_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
        details.append(ft.Text(f"{format_time(event.get('at'))}" + (f" · {event['actor']}" if event.get("actor") else ""), size=11, color=self.muted_color()))
        tracking_number = event.get("tracking_number") if show_document else None
        return self.list_row(
            [
                ft.Container(ft.Icon(icon, color=color, size=18), padding=7, bgcolor=ft.Colors.with_opacity(0.12, color), border_radius=8),
                ft.Column(details, spacing=3, expand=True),
            ],
            on_click=(lambda _, value=tracking_number: on_open(value)) if tracking_number and on_open else None,
        )
