import flet as ft
import requests
import traceback


BACKEND_URL = "http://127.0.0.1:8001"


def build_analytics_view(
    current_user,
    headers,
    backend_url=None,
    open_documents_view=None,
    open_archived_view=None,
    page=None,
):
    backend_url = backend_url or BACKEND_URL
    is_dark = page is not None and page.theme_mode == ft.ThemeMode.DARK
    primary_text = ft.Colors.BLUE_GREY_100 if is_dark else ft.Colors.BLUE_GREY_900
    secondary_text = ft.Colors.BLUE_GREY_300 if is_dark else ft.Colors.BLUE_GREY_600
    panel_color = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
    soft_panel_color = "#26343a" if is_dark else ft.Colors.BLUE_GREY_50
    border_color = ft.Colors.BLUE_GREY_700 if is_dark else ft.Colors.BLUE_GREY_100

    metric_cards = ft.Row([], spacing=12, wrap=True)
    status_chart = ft.Column([], spacing=8)
    type_distribution = ft.Column([], spacing=8)
    office_distribution = ft.Column([], spacing=8)
    processing_panel = ft.Column([], spacing=8)
    monthly_panel = ft.Column([], spacing=8)
    recent_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Tracking #")),
            ft.DataColumn(ft.Text("Title")),
            ft.DataColumn(ft.Text("Document Type")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("Priority")),
            ft.DataColumn(ft.Text("Current Office")),
            ft.DataColumn(ft.Text("Date Registered")),
        ],
        rows=[],
        width=900,
    )

    def build_status_bar(max_value, count, label):
        bar_width = 160
        if max_value:
            bar_width = max(16, int((count / max_value) * 180))
        return ft.Row([
            ft.Container(
                content=ft.Text(label, size=11, weight=ft.FontWeight.BOLD, width=110),
                width=110,
            ),
            ft.Container(
                content=ft.Container(
                    content=ft.Text(" "),
                    bgcolor=ft.Colors.BLUE_400,
                    height=10,
                    width=bar_width,
                    border_radius=5,
                ),
                width=bar_width + 20,
            ),
            ft.Text(str(count), size=11, color=secondary_text),
        ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def load_analytics():
        try:
            response = requests.get(
                f"{backend_url}/analytics",
                headers=headers,
                verify=False,
                timeout=10,
            )
            if response.status_code != 200:
                raise Exception(response.text)
            payload = response.json()

            overview = payload.get("overview") or {}
            processing = payload.get("processing") or {}
            monthly_activity = payload.get("monthly_activity") or []
            recent_documents = payload.get("recent_documents") or []

            cards = [
                ("Total Documents", overview.get("total_documents", 0), "All tracked records", ft.Icons.DESCRIPTION_OUTLINED, ft.Colors.BLUE_700, "total"),
                ("Active Documents", overview.get("active_documents", 0), "Currently active", ft.Icons.LIBRARY_ADD_CHECK_OUTLINED, ft.Colors.GREEN_700, "active"),
                ("Pending Documents", overview.get("pending_documents", 0), "Awaiting action", ft.Icons.SCHEDULE_OUTLINED, ft.Colors.RED_700, "pending"),
                ("Completed Documents", overview.get("completed_documents", 0), "Successfully completed", ft.Icons.CHECK_CIRCLE_OUTLINED, ft.Colors.TEAL_700, "completed"),
                ("Archived Documents", overview.get("archived_documents", 0), "Closed / archived", ft.Icons.ARCHIVE_OUTLINED, ft.Colors.ORANGE_700, "archived"),
                ("Documents Added This Month", overview.get("added_this_month", 0), "Registered during current month", ft.Icons.CALENDAR_MONTH_OUTLINED, ft.Colors.DEEP_PURPLE_700, "month"),
            ]

            metric_cards.controls.clear()
            for title, value, detail, icon, color, card_type in cards:
                card_on_click = None
                if card_type == "total" and open_documents_view is not None:
                    card_on_click = lambda e: open_documents_view()
                elif card_type == "archived" and open_archived_view is not None:
                    card_on_click = lambda e: open_archived_view()

                metric_cards.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row([
                                    ft.Icon(icon, color=color, size=28),
                                    ft.Text(
                                        title,
                                        size=13,
                                        weight=ft.FontWeight.BOLD,
                                        color=primary_text,
                                        width=135,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                ft.Text(str(value), size=26, weight=ft.FontWeight.BOLD, color=primary_text),
                                ft.Text(detail, size=11, color=secondary_text),
                            ],
                            spacing=4,
                        ),
                        width=195,
                        padding=12,
                        bgcolor=panel_color,
                        border_radius=12,
                        border=ft.border.all(1, border_color),
                        on_click=card_on_click,
                    )
                )

            status_data = payload.get("status_breakdown") or {}
            max_status = max(status_data.values()) if status_data else 0
            status_chart.controls = [ft.Text("Document Status", size=14, weight=ft.FontWeight.BOLD)]
            for label, count in status_data.items():
                status_chart.controls.append(build_status_bar(max_status, count, str(label)))

            type_data = payload.get("document_types") or {}
            if type_data:
                type_distribution.controls = [ft.Text("Documents by Document Type", size=13, weight=ft.FontWeight.BOLD)]
                for label, count in type_data.items():
                    type_distribution.controls.append(ft.Text(f"{label}: {count}", size=11))
            else:
                type_distribution.controls = [ft.Text("Documents by Document Type", size=13, weight=ft.FontWeight.BOLD), ft.Text("No document types found", size=11)]

            office_data = payload.get("offices") or {}
            if office_data:
                office_distribution.controls = [ft.Text("Documents by Current Office", size=13, weight=ft.FontWeight.BOLD)]
                for label, count in office_data.items():
                    office_distribution.controls.append(ft.Text(f"{label}: {count}", size=11))
            else:
                office_distribution.controls = [ft.Text("Documents by Current Office", size=13, weight=ft.FontWeight.BOLD), ft.Text("No office distribution found", size=11)]

            longest = processing.get("longest_pending") or {}
            longest_label = longest.get("tracking_number") or "N/A"
            longest_days = longest.get("days") or "Insufficient data"

            processing_controls = [
                ft.Text("Document Processing Analytics", size=14, weight=ft.FontWeight.BOLD),
                ft.Text(f"Average Processing Time: {processing.get('average_processing_days') if processing.get('average_processing_days') is not None else 'N/A'} days", size=11),
                ft.Text(f"Documents Awaiting Action: {processing.get('awaiting_action', 'N/A')}", size=11),
                ft.Text(f"Longest Pending: {longest_label} ({longest_days})", size=11),
                ft.Text(f"Completed This Month: {processing.get('completed_this_month', 0)}", size=11),
                ft.Text(f"Archived This Month: {processing.get('archived_this_month', 0)}", size=11),
            ]
            processing_panel.controls = processing_controls

            monthly_bar_max = max((row.get("count") or 0) for row in monthly_activity) if monthly_activity else 0
            monthly_panel.controls = [ft.Text("Monthly Document Activity", size=14, weight=ft.FontWeight.BOLD)]
            for row in monthly_activity:
                count = row.get("count") or 0
                bar_width = 160 if monthly_bar_max == 0 else max(12, int((count / monthly_bar_max) * 160))
                monthly_panel.controls.append(
                    ft.Row([
                        ft.Container(content=ft.Text(str(row.get("label") or "-"), size=11, width=60), width=60),
                        ft.Container(content=ft.Container(bgcolor=ft.Colors.GREEN_400, width=bar_width, height=10, border_radius=4), width=bar_width + 20),
                        ft.Text(str(count), size=11),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                )

            recent_rows = []
            for item in recent_documents:
                title_text = str(item.get("title") or "-")
                title_cell = ft.Tooltip(
                    message=title_text,
                    content=ft.Container(
                        content=ft.Text(
                            title_text,
                            size=11,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            no_wrap=True,
                        ),
                        width=240,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                )
                recent_rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(item.get("tracking_number") or "-"))),
                            ft.DataCell(title_cell),
                            ft.DataCell(ft.Text(str(item.get("document_type") or "-"))),
                            ft.DataCell(ft.Text(str(item.get("status") or "-"))),
                            ft.DataCell(ft.Text(str(item.get("priority") or "-"))),
                            ft.DataCell(ft.Text(str(item.get("current_office") or "-"))),
                            ft.DataCell(ft.Text(str(item.get("date_registered") or "-"))),
                        ]
                    )
                )
            recent_table.rows = recent_rows

        except Exception as exc:
            metric_cards.controls = []
            status_chart.controls = [
                ft.Text("Unable to load analytics", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700),
                ft.Text(str(exc), size=11, color=ft.Colors.RED_700),
            ]

    load_analytics()

    refresh_button = ft.Button("Refresh Analytics", on_click=lambda _: load_analytics())

    return ft.Column(
        controls=[
            ft.Row([
                ft.Column([
                    ft.Text("ANALYTICS", size=24, weight=ft.FontWeight.BOLD, color=primary_text),
                    ft.Text("Operational document insights", size=12, color=secondary_text),
                ], spacing=2),
                ft.Container(expand=True),
                refresh_button,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(height=4),
            metric_cards,
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Document Status", size=16, weight=ft.FontWeight.BOLD),
                        status_chart,
                    ],
                    spacing=8,
                ),
                padding=12,
                border_radius=12,
                bgcolor=soft_panel_color,
            ),
            ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Column([type_distribution], spacing=8),
                        expand=True,
                        padding=12,
                        border=ft.border.all(1, border_color),
                        bgcolor=panel_color,
                    ),
                    ft.Container(
                        content=ft.Column([office_distribution], spacing=8),
                        expand=True,
                        padding=12,
                        border=ft.border.all(1, border_color),
                        bgcolor=panel_color,
                    ),
                ], spacing=12),
                padding=0,
            ),
            ft.Container(
                content=ft.Column([processing_panel], spacing=8),
                padding=12,
                bgcolor=soft_panel_color,
                border_radius=12,
            ),
            ft.Container(
                content=ft.Column([monthly_panel], spacing=8),
                padding=12,
                bgcolor=soft_panel_color,
                border_radius=12,
            ),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Recent Documents", size=14, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=recent_table,
                            padding=8,
                            border_radius=10,
                            bgcolor=panel_color,
                            border=ft.border.all(1, border_color),
                        ),
                    ],
                    spacing=12,
                ),
                padding=12,
                border_radius=12,
                bgcolor=soft_panel_color,
            ),
        ],
        spacing=14,
        expand=True,
    )
