"""Building blocks shared by the document tracking screens (QR Tracking, Office Dashboard)."""

from datetime import date, datetime, timezone

import flet as ft

from frontend.admin.screen import DESKTOP, is_phone, screen_size

# Served from the shared assets folder; banners show plain colour when it is missing.
BANNER_IMAGE = "sb_tolosa_homepage.jpg"

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


def remark_list(widgets, history):
    """A document's remarks, newest first, each with who wrote it and when."""
    rows = []
    for item in history or []:
        when = parse_time(item.get("created_at"))
        byline = " · ".join(part for part in (
            item.get("author"), when.astimezone().strftime("%b %d, %Y %I:%M %p") if when else None,
        ) if part)
        rows.append(ft.Container(
            content=ft.Column(
                [ft.Text(item.get("text") or "", size=13, color=widgets.body_color(), selectable=True),
                 *([widgets.hint(byline)] if byline else [])],
                spacing=2,
            ),
            data="remark",
            padding=ft.Padding(10, 8, 10, 8),
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.05, widgets.body_color()),
        ))
    return ft.Column(rows, spacing=6)


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
# A measure's stage (GLOSSARY.md: Stage): enacted stages green, endings their own colour, the rest blue.
STAGE_COLORS = {
    "Withdrawn": ft.Colors.BLUE_GREY_600, "Tabled": ft.Colors.AMBER_800, "Lost": ft.Colors.RED_700,
    "Vetoed": ft.Colors.RED_700, "Posted": ft.Colors.GREEN_700, "Signed": ft.Colors.GREEN_700,
    "Approved": ft.Colors.GREEN_700, "Adopted": ft.Colors.GREEN_700, "Lapsed into Law": ft.Colors.GREEN_700,
}


def stage_color(stage):
    return STAGE_COLORS.get(stage, ft.Colors.BLUE_700)


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


def compact_col(col):
    """`col` for a ResponsiveRow child, made two to a row on a phone.

    A full-width phone column (xs 10 or 12, matching the row's column count) is halved;
    a narrower one is kept.
    """
    col = dict(col) if isinstance(col, dict) else {}
    xs = col.get("xs", 12)
    col["xs"] = xs // 2 if xs in (10, 12) else xs
    col["sm"] = col["xs"]
    return col


class TrackingWidgets:
    """Controls styled for the current theme.

    The shell themes a view once when it opens, so rows a screen renders later
    pick their night-mode colours here instead.
    """

    def __init__(self, page):
        self.page = page

    @property
    def phone(self):
        """On a phone, screens are compact and leave out photos and explanations."""
        return is_phone(self.page)

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
                    ft.Text(str(value), size=20 if self.phone else 26, weight=ft.FontWeight.BOLD, color=self.heading_color()),
                    *([] if self.phone else [ft.Text(detail, size=11, color=self.muted_color())]),
                ],
                spacing=4,
            ),
            padding=10 if self.phone else 14,
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

    def accent(self):
        return self.tone(ft.Colors.BLUE_700, ft.Colors.BLUE_300)

    def tint(self):
        return self.tone("#EEF4FC", "#22303D")

    def stat_card(self, title, value, detail, icon, color, col=None, tile=False, active=False):
        """A count with a coloured strip on its left. `tile` puts the icon in a tinted square;
        `active` tints the card, for a count that is filtering the list below it."""
        if self.phone:
            return self._compact_stat_card(title, value, icon, color, col, active)
        if tile:
            badge = ft.Container(
                content=ft.Icon(icon, color=color, size=24),
                width=46, height=46, border_radius=12,
                alignment=ft.Alignment(0, 0),
                bgcolor=ft.Colors.with_opacity(0.14, color),
            )
        else:
            badge = ft.Icon(icon, color=color, size=22)
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [badge, ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=self.heading_color(), expand=True, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)],
                        spacing=14 if tile else 10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(str(value), size=26, weight=ft.FontWeight.BOLD, color=self.link_color()),
                    ft.Text(detail, size=13, color=self.accent() if tile else self.muted_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ],
                spacing=6,
            ),
            padding=ft.Padding(18, 14, 16, 16),
            bgcolor=ft.Colors.with_opacity(0.12 if active else 0.03, color),
            border=ft.Border(
                left=ft.BorderSide(4, color),
                top=ft.BorderSide(1, self.line_color()),
                right=ft.BorderSide(1, self.line_color()),
                bottom=ft.BorderSide(1, self.line_color()),
            ),
            border_radius=12,
            shadow=ft.BoxShadow(blur_radius=8, color=ft.Colors.with_opacity(0.06, ft.Colors.BLACK), offset=ft.Offset(0, 2)),
            col=col,
        )

    def _compact_stat_card(self, title, value, icon, color, col, active):
        """A phone's stat card: the count and its name, two to a row (see compact_col)."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, color=color, size=18),
                    ft.Column(
                        [
                            ft.Text(str(value), size=20, weight=ft.FontWeight.BOLD, color=self.link_color()),
                            ft.Text(title, size=12, color=self.body_color(), max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(10, 8, 8, 8),
            bgcolor=ft.Colors.with_opacity(0.12 if active else 0.03, color),
            border=ft.Border(
                left=ft.BorderSide(3, color),
                top=ft.BorderSide(1, self.line_color()),
                right=ft.BorderSide(1, self.line_color()),
                bottom=ft.BorderSide(1, self.line_color()),
            ),
            border_radius=10,
            col=compact_col(col),
        )

    def card_title(self, title, icon, subtitle=None, trailing=None):
        """A card's heading beside a round icon badge. `title` may be a Text, to change it later."""
        phone = self.phone
        heading = title if isinstance(title, ft.Text) else ft.Text(title, size=15 if phone else 17, weight=ft.FontWeight.BOLD, color=self.link_color())
        # A phone leaves out the explanation under the heading.
        lines = [heading, *([ft.Text(subtitle, size=12, color=self.muted_color())] if subtitle and not phone else [])]
        # On a phone a row of buttons goes underneath the heading, wrapping as needed.
        below = phone and isinstance(trailing, ft.Row)
        heading_row = ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, size=18 if phone else 24, color=self.accent()),
                    width=34 if phone else 50, height=34 if phone else 50, border_radius=17 if phone else 25,
                    alignment=ft.Alignment(0, 0),
                    bgcolor=ft.Colors.with_opacity(0.10, self.accent()),
                ),
                ft.Column(lines, spacing=3, expand=True),
                *([trailing] if trailing is not None and not below else []),
            ],
            spacing=10 if phone else 16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        if not below:
            return heading_row
        trailing.wrap = True
        trailing.run_spacing = 8
        return ft.Column([heading_row, trailing], spacing=10)

    def empty_box(self, message, icon=ft.Icons.INFO, centered=False):
        """An empty list's message in a tinted box; `centered` stacks the icon above it."""
        icon_control = ft.Icon(icon, color=self.tone(ft.Colors.BLUE_400, ft.Colors.BLUE_300), size=24)
        text = ft.Text(message, size=13, color=self.muted_color(), text_align=ft.TextAlign.CENTER if centered else None)
        content = (
            ft.Column([icon_control, text], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            if centered else
            ft.Row([icon_control, ft.Container(text, expand=True)], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        )
        return ft.Container(
            content=content,
            padding=ft.Padding(16, 22 if centered else 16, 16, 22 if centered else 16),
            bgcolor=self.tint(),
            border_radius=10,
            alignment=ft.Alignment(0, 0) if centered else None,
        )

    def style_field(self, control, hint=None):
        """Restyle a search box or filter the screen did not create, for the rounded look; its name
        moves above it (see labelled). Such controls outlive the screen, so the name is kept in `data`."""
        if control.data is None:
            control.data = control.label
        control.label = None
        if hint:
            control.hint_text = hint
        control.dense = True
        control.text_size = 14
        control.border_radius = 10
        control.border_color = self.line_color()
        control.focused_border_color = self.accent()
        control.filled = True
        control.bgcolor = self.card_color()
        control.content_padding = ft.Padding(14, 12, 10, 12)

    def labelled(self, control, width=None):
        """`control` under its name (from style_field). A search box shows its name as its placeholder instead."""
        if isinstance(control, ft.TextField):
            return ft.Container(control, expand=control.expand, width=width)
        return ft.Column(
            [ft.Text(control.data, size=13, weight=ft.FontWeight.W_600, color=self.heading_color()), control],
            spacing=6,
            width=width,
        )

    def banner(self, title, subtitle, icon, actions=None, corner=None):
        """A screen's blue heading banner, with the town hall on the right.

        `actions` are buttons placed at its bottom right; `corner` is one small control at its top right.
        A phone gets a slim banner without the photo or subtitle, with the buttons on a row underneath.
        """
        if self.phone:
            return self._phone_banner(title, icon, actions, corner)
        if actions and screen_size(self.page) != DESKTOP:
            # An upright tablet has no room beside the subtitle, so the buttons go underneath.
            return ft.Column([self.banner(title, subtitle, icon, corner=corner), ft.Row(actions, spacing=10, run_spacing=8, wrap=True)], spacing=10)
        blue = "#0D4FB0"
        layers = [
            ft.Container(
                content=ft.Image(src=BANNER_IMAGE, fit=ft.ImageFit.COVER, error_content=ft.Container()),
                right=0, top=0, bottom=0, width=700,
            ),
            # Blends the photo into the blue, so the heading sits on solid colour.
            ft.Container(
                gradient=ft.LinearGradient(
                    begin=ft.Alignment(-1, 0),
                    end=ft.Alignment(1, 0),
                    colors=[blue, ft.Colors.with_opacity(0.75, blue), ft.Colors.with_opacity(0.15, blue), ft.Colors.with_opacity(0.0, blue)],
                    stops=[0.0, 0.25, 0.6, 1.0],
                ),
                right=0, top=0, bottom=0, width=700,
            ),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(icon, size=32, color=ft.Colors.BLUE_700),
                            width=72, height=72, border_radius=16,
                            alignment=ft.Alignment(0, 0),
                            bgcolor=ft.Colors.with_opacity(0.92, ft.Colors.WHITE),
                        ),
                        ft.Column(
                            [
                                ft.Text(title, size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                ft.Text(subtitle, size=15, color=ft.Colors.with_opacity(0.92, ft.Colors.WHITE)),
                            ],
                            spacing=4,
                            alignment=ft.MainAxisAlignment.CENTER,
                            expand=True,
                        ),
                    ],
                    spacing=24,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(26, 0, 26, 0),
                alignment=ft.Alignment(-1, 0),
                left=0, right=0, top=0, bottom=0,
            ),
        ]
        if corner is not None:
            layers.append(ft.Container(content=corner, bgcolor=ft.Colors.with_opacity(0.25, ft.Colors.BLACK), border_radius=20, top=10, right=10))
        if actions:
            layers.append(ft.Container(content=ft.Row(actions, spacing=10, tight=True), right=16, bottom=14))
        return ft.Container(
            content=ft.Stack(layers, height=150 if actions else 132),
            gradient=ft.LinearGradient(begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0), colors=["#0B47A3", "#1565C0"]),
            border_radius=16,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    def _phone_banner(self, title, icon, actions, corner):
        heading = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(icon, size=20, color=ft.Colors.BLUE_700),
                        width=36, height=36, border_radius=10,
                        alignment=ft.Alignment(0, 0),
                        bgcolor=ft.Colors.with_opacity(0.92, ft.Colors.WHITE),
                    ),
                    ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE, expand=True,
                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    # Only a small button (like Refresh) fits beside the title; other corner items are left out.
                    *([corner] if isinstance(corner, ft.IconButton) else []),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(14, 10, 10, 10),
            gradient=ft.LinearGradient(begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0), colors=["#0B47A3", "#1565C0"]),
            border_radius=12,
        )
        if not actions:
            return heading
        return ft.Column([heading, ft.Row(actions, spacing=8, run_spacing=8, wrap=True)], spacing=8)

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
