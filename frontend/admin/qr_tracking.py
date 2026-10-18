"""QR Tracking screen: scan a document to see where it is, and watch documents move between offices."""

from datetime import datetime, timezone
from urllib.parse import quote

import flet as ft

# How each kind of tracking event is shown: (label, icon, colour).
EVENT_STYLES = {
    "sent": ("Sent", ft.Icons.SEND_OUTLINED, ft.Colors.BLUE_700),
    "received": ("Received", ft.Icons.MOVE_TO_INBOX_OUTLINED, ft.Colors.GREEN_700),
    "action": ("Action", ft.Icons.TASK_ALT, ft.Colors.INDIGO_600),
    "scan": ("Scanned", ft.Icons.QR_CODE_SCANNER, ft.Colors.TEAL_700),
    "unrecognized": ("Unrecognized scan", ft.Icons.ERROR_OUTLINE, ft.Colors.RED_700),
    "registered": ("Registered", ft.Icons.NOTE_ADD_OUTLINED, ft.Colors.BLUE_GREY_600),
}

# Where a scanned document is now: (headline, icon, colour).
LOCATION_STYLES = {
    "in_transit": ("In transit", ft.Icons.LOCAL_SHIPPING_OUTLINED, ft.Colors.AMBER_800),
    "held": ("At office", ft.Icons.APARTMENT, ft.Colors.GREEN_700),
    "archived": ("Archived", ft.Icons.ARCHIVE_OUTLINED, ft.Colors.BLUE_GREY_600),
    "unrouted": ("Not routed yet", ft.Icons.HOURGLASS_EMPTY, ft.Colors.BLUE_GREY_600),
}


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
    if kind in ("received", "registered"):
        return office
    if kind == "action":
        return f"{event.get('detail') or 'Action'} · {office}"
    return event.get("detail") or ""


def build_qr_tracking_view(page, api, surface_card, section_header):
    """`api(method, path, **kwargs)` calls the main backend and returns parsed JSON or raises."""

    # The shell themes a view once when it opens; rows rendered later pick night-mode colours here.
    def tone(light, dark):
        return dark if page.theme_mode == ft.ThemeMode.DARK else light

    def heading_color():
        return tone(ft.Colors.BLUE_GREY_900, ft.Colors.BLUE_GREY_50)

    def body_color():
        return tone(ft.Colors.BLUE_GREY_800, ft.Colors.BLUE_GREY_200)

    def muted_color():
        return tone(ft.Colors.BLUE_GREY_500, ft.Colors.BLUE_GREY_400)

    def link_color():
        return tone(ft.Colors.BLUE_900, ft.Colors.BLUE_200)

    def line_color():
        return tone(ft.Colors.BLUE_GREY_100, ft.Colors.BLUE_GREY_700)

    updated_text = ft.Text("", size=11, color=muted_color())
    error_text = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)
    kpi_row = ft.ResponsiveRow(spacing=12, run_spacing=12)
    transit_title = ft.Text("In transit", size=15, weight=ft.FontWeight.BOLD, color=heading_color())
    transit_list = ft.Column(spacing=0)
    activity_list = ft.Column(spacing=0)

    scan_field = ft.TextField(
        hint_text="Scan a QR code or type a tracking number, then press Enter",
        prefix_icon=ft.Icons.QR_CODE_SCANNER,
        autofocus=True,
        expand=True,
        height=48,
        content_padding=ft.Padding(12, 4, 12, 4),
    )
    trail_panel = ft.Column(spacing=10, visible=False)

    def chip(text, color):
        return ft.Container(
            content=ft.Text(text, size=11, weight=ft.FontWeight.W_600, color=color),
            padding=ft.Padding(8, 3, 8, 3),
            bgcolor=ft.Colors.with_opacity(0.12, color),
            border_radius=10,
        )

    def kpi(title, value, detail, icon, accent):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=accent, size=18),
                            ft.Text(title, size=12, weight=ft.FontWeight.W_600, color=body_color()),
                        ],
                        spacing=6,
                    ),
                    ft.Text(str(value), size=26, weight=ft.FontWeight.BOLD, color=heading_color()),
                    ft.Text(detail, size=11, color=muted_color()),
                ],
                spacing=4,
            ),
            padding=14,
            bgcolor=tone(ft.Colors.WHITE, ft.Colors.GREY_900),
            border=ft.Border(
                left=ft.BorderSide(4, accent),
                top=ft.BorderSide(1, line_color()),
                right=ft.BorderSide(1, line_color()),
                bottom=ft.BorderSide(1, line_color()),
            ),
            border_radius=10,
            col={"xs": 6, "md": 4, "xl": 2},
        )

    def list_row(controls, on_click=None):
        return ft.Container(
            content=ft.Row(controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(4, 10, 4, 10),
            border=ft.Border(bottom=ft.BorderSide(1, line_color())),
            on_click=on_click,
            ink=on_click is not None,
        )

    def empty(message):
        return ft.Container(ft.Text(message, size=12, color=muted_color()), padding=ft.Padding(4, 12, 4, 12))

    def document_cell(item, expand=True):
        return ft.Column(
            [
                ft.Text(item.get("tracking_number") or "-", size=12, weight=ft.FontWeight.BOLD, color=link_color()),
                ft.Text(item.get("title") or "Untitled", size=12, color=body_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ],
            spacing=1,
            expand=expand,
        )

    def event_row(event, show_document):
        label, icon, color = EVENT_STYLES.get(event.get("type"), ("Event", ft.Icons.CIRCLE_OUTLINED, ft.Colors.BLUE_GREY_600))
        details = [ft.Row([chip(label, color), ft.Text(event_summary(event), size=12, color=body_color(), expand=True)], spacing=8)]
        if show_document and event.get("tracking_number"):
            details.append(ft.Text(f"{event['tracking_number']} · {event.get('title') or 'Untitled'}", size=11, color=muted_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
        details.append(ft.Text(f"{format_time(event.get('at'))}" + (f" · {event['actor']}" if event.get("actor") else ""), size=11, color=muted_color()))
        tracking_number = event.get("tracking_number") if show_document else None
        return list_row(
            [
                ft.Container(ft.Icon(icon, color=color, size=18), padding=7, bgcolor=ft.Colors.with_opacity(0.12, color), border_radius=8),
                ft.Column(details, spacing=3, expand=True),
            ],
            on_click=(lambda _, value=tracking_number: track(value)) if tracking_number else None,
        )

    def render_monitor(payload):
        summary = payload.get("summary") or {}
        overdue_hours = payload.get("overdue_hours") or 24
        kpi_row.controls = [
            kpi("In transit", summary.get("in_transit", 0), "Sent, awaiting receipt", ft.Icons.LOCAL_SHIPPING_OUTLINED, ft.Colors.AMBER_800),
            kpi("Overdue", summary.get("overdue", 0), f"Waiting {overdue_hours}h or more", ft.Icons.WARNING_AMBER_ROUNDED, ft.Colors.RED_700),
            kpi("Sent today", summary.get("sent_today", 0), "Handoffs started", ft.Icons.SEND_OUTLINED, ft.Colors.BLUE_700),
            kpi("Received today", summary.get("received_today", 0), "Receipts confirmed", ft.Icons.MOVE_TO_INBOX_OUTLINED, ft.Colors.GREEN_700),
            kpi("Actions today", summary.get("actions_today", 0), "Signed, reviewed, noted…", ft.Icons.TASK_ALT, ft.Colors.INDIGO_600),
            kpi("Scans today", summary.get("scans_today", 0), f"{summary.get('unrecognized_today', 0)} unrecognized", ft.Icons.QR_CODE_SCANNER, ft.Colors.TEAL_700),
        ]

        in_transit = payload.get("in_transit") or []
        transit_title.value = f"In transit ({len(in_transit)})"
        rows = []
        for item in in_transit:
            waiting = format_elapsed(item.get("sent_at"))
            rows.append(list_row(
                [
                    document_cell(item),
                    ft.Column(
                        [
                            ft.Text(f"{item.get('from_office') or '-'} → {item.get('to_office') or '-'}", size=12, color=body_color()),
                            ft.Text(f"Sent {format_time(item.get('sent_at'))}" + (f" by {item['sent_by']}" if item.get("sent_by") else ""), size=11, color=muted_color()),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    chip(f"Overdue · {waiting}" if item.get("overdue") else waiting, ft.Colors.RED_700 if item.get("overdue") else ft.Colors.AMBER_800),
                ],
                on_click=lambda _, value=item.get("tracking_number"): track(value),
            ))
        transit_list.controls = rows or [empty("Nothing in transit. Every handed-off document has been received.")]

        events = payload.get("recent_activity") or []
        activity_list.controls = [event_row(event, show_document=True) for event in events] or [empty("No tracking activity yet.")]
        updated_text.value = f"Updated {format_time(payload.get('generated_at'))}"

    def refresh(_=None, update=True):
        error_text.visible = False
        try:
            render_monitor(api("GET", "/documents/qr/monitor"))
        except Exception as exc:
            error_text.value = f"Unable to load QR tracking: {exc}"
            error_text.visible = True
        if update:
            page.update()

    def render_trail(payload):
        document = payload.get("document") or {}
        location = payload.get("location") or {}
        headline, icon, color = LOCATION_STYLES.get(location.get("state"), LOCATION_STYLES["unrouted"])
        if location.get("state") == "in_transit":
            where = f"{location.get('office') or '-'} → {location.get('to_office') or '-'}"
        else:
            where = location.get("office") or "No office recorded"
        since = f"for {format_elapsed(location.get('since'))} (since {format_time(location.get('since'))})" if location.get("since") else ""
        reference = " · ".join(part for part in [
            document.get("document_type"),
            f"No. {document['document_number']}" if document.get("document_number") else None,
            f"s. {document['series_year']}" if document.get("series_year") else None,
        ] if part)

        events = payload.get("events") or []
        trail_panel.controls = [
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(document.get("tracking_number") or "-", size=13, weight=ft.FontWeight.BOLD, color=link_color()),
                            ft.Text(document.get("title") or "Untitled", size=16, weight=ft.FontWeight.BOLD, color=heading_color()),
                            *([ft.Text(reference, size=12, color=muted_color())] if reference else []),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.IconButton(ft.Icons.CLOSE, tooltip="Clear", on_click=clear_trail),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, color=color, size=28),
                        ft.Column(
                            [
                                ft.Text(headline.upper(), size=11, weight=ft.FontWeight.BOLD, color=color),
                                ft.Text(where, size=16, weight=ft.FontWeight.BOLD, color=heading_color()),
                                *([ft.Text(since, size=12, color=muted_color())] if since else []),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=14,
                ),
                padding=14,
                bgcolor=ft.Colors.with_opacity(0.08, color),
                border=ft.Border(left=ft.BorderSide(4, color)),
                border_radius=10,
            ),
            ft.Text(f"Route history ({len(events)})", size=13, weight=ft.FontWeight.BOLD, color=body_color()),
            ft.Column([event_row(event, show_document=False) for event in events] or [empty("No movement recorded yet.")], spacing=0),
        ]
        trail_panel.visible = True

    def track(value=None):
        value = (value if isinstance(value, str) else scan_field.value or "").strip()
        if not value:
            return
        scan_field.value = value
        try:
            render_trail(api("GET", f"/documents/qr/{quote(value, safe='')}/trail"))
        except Exception as exc:
            message = "No document matches that QR code or tracking number." if "not recognized" in str(exc).lower() else f"Lookup failed: {exc}"
            trail_panel.controls = [ft.Row([ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.RED_700), ft.Text(message, size=13, color=ft.Colors.RED_700)], spacing=8)]
            trail_panel.visible = True
        # Refresh the counts too: the lookup itself is recorded as a scan.
        refresh(update=False)
        page.update()

    def clear_trail(_=None):
        scan_field.value = ""
        trail_panel.visible = False
        trail_panel.controls = []
        page.update()

    scan_field.on_submit = lambda _: track()

    refresh(update=False)
    return ft.Column(
        [
            ft.Row(
                [
                    ft.Container(section_header("QR Tracking", "Scan a document to see where it is, and watch documents move between offices.", ft.Icons.QR_CODE_2, ft.Colors.BLUE_700), expand=True),
                    updated_text,
                    ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=refresh),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            error_text,
            surface_card(
                ft.Column(
                    [
                        ft.Row([scan_field, ft.FilledButton("Track", icon=ft.Icons.SEARCH, on_click=lambda _: track(), height=48)], spacing=8),
                        trail_panel,
                    ],
                    spacing=14,
                ),
                padding=18,
            ),
            kpi_row,
            ft.ResponsiveRow(
                [
                    ft.Container(
                        surface_card(ft.Column([transit_title, ft.Text("Oldest first. Select a document to see its route.", size=11, color=muted_color()), transit_list], spacing=6), padding=18),
                        col={"xs": 12, "lg": 7},
                    ),
                    ft.Container(
                        surface_card(ft.Column([ft.Text("Recent activity", size=15, weight=ft.FontWeight.BOLD, color=heading_color()), activity_list], spacing=6), padding=18),
                        col={"xs": 12, "lg": 5},
                    ),
                ],
                spacing=16,
                run_spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ],
        spacing=16,
    )
