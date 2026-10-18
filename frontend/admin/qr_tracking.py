"""QR Tracking screen: scan a document to see where it is, and watch documents move between offices."""

from urllib.parse import quote

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets, document_reference, format_elapsed, format_time

# Where a scanned document is now: (headline, icon, colour).
LOCATION_STYLES = {
    "in_transit": ("In transit", ft.Icons.LOCAL_SHIPPING_OUTLINED, ft.Colors.AMBER_800),
    "held": ("At office", ft.Icons.APARTMENT, ft.Colors.GREEN_700),
    "archived": ("Archived", ft.Icons.ARCHIVE_OUTLINED, ft.Colors.BLUE_GREY_600),
    "unrouted": ("Not routed yet", ft.Icons.HOURGLASS_EMPTY, ft.Colors.BLUE_GREY_600),
}


def build_qr_tracking_view(page, api, surface_card, section_header):
    """`api(method, path, **kwargs)` calls the main backend and returns parsed JSON or raises."""

    widgets = TrackingWidgets(page)
    heading_color, body_color, muted_color, link_color = widgets.heading_color, widgets.body_color, widgets.muted_color, widgets.link_color
    kpi, list_row, empty = widgets.kpi, widgets.list_row, widgets.empty

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

    def event_row(event, show_document):
        return widgets.event_row(event, show_document, on_open=track)

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
            rows.append(list_row(
                [
                    widgets.document_cell(item),
                    ft.Column(
                        [
                            ft.Text(f"{item.get('from_office') or '-'} → {item.get('to_office') or '-'}", size=12, color=body_color()),
                            ft.Text(f"Sent {format_time(item.get('sent_at'))}" + (f" by {item['sent_by']}" if item.get("sent_by") else ""), size=11, color=muted_color()),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    widgets.waiting_chip(item),
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
        reference = document_reference(document)

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
