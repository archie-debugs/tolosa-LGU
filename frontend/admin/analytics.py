"""Analytics: document volume, status, where documents sit and how fast they move, from GET /analytics."""

import flet as ft
import requests

from frontend.admin.tracking_ui import TrackingWidgets

BACKEND_URL = "http://127.0.0.1:8001"

# Colours for the statuses the backend normalises to (routes/analytics._norm_status).
STATUS_COLORS = {
    "Pending": ft.Colors.AMBER_800,
    "In Progress": ft.Colors.BLUE_700,
    "Completed": ft.Colors.GREEN_700,
    "Archived": ft.Colors.BROWN_400,
    "Returned": ft.Colors.DEEP_ORANGE_700,
    "Rejected": ft.Colors.RED_700,
}
# How many rows each "by type / category / office" breakdown shows before folding the rest into "Others".
BREAKDOWN_ROWS = 6
MONTH_CHART_HEIGHT = 130


def status_color(status):
    return STATUS_COLORS.get(str(status or "").strip().title(), ft.Colors.BLUE_GREY_500)


def top_counts(counts, limit=BREAKDOWN_ROWS):
    """`counts` largest first, with everything past `limit` added up as "Others"."""
    ranked = sorted(((str(label), int(count or 0)) for label, count in (counts or {}).items()), key=lambda pair: -pair[1])
    if len(ranked) <= limit:
        return ranked
    return ranked[:limit - 1] + [("Others", sum(count for _, count in ranked[limit - 1:]))]


def build_analytics_view(
    current_user,
    headers,
    backend_url=None,
    open_documents_view=None,
    open_archived_view=None,
    page=None,
):
    backend_url = backend_url or BACKEND_URL
    widgets = TrackingWidgets(page)
    card_tint = widgets.tone("#F7FAFE", "#1B2430")

    notice = ft.Container(visible=False)
    kpi_row = ft.ResponsiveRow(spacing=14, run_spacing=14)
    status_list = ft.Column(spacing=14)
    status_total = ft.Text("", size=13, color=widgets.body_color())
    month_chart = ft.Row(spacing=10, vertical_alignment=ft.CrossAxisAlignment.END)
    month_total = ft.Text("", size=13, color=widgets.body_color())
    breakdown_row = ft.ResponsiveRow(spacing=16, run_spacing=16, vertical_alignment=ft.CrossAxisAlignment.START)
    processing_row = ft.ResponsiveRow(columns=10, spacing=12, run_spacing=12)
    recent_list = ft.Column(spacing=10)

    def card(content):
        return ft.Container(
            content=content,
            padding=20,
            bgcolor=widgets.card_color(),
            border=ft.border.all(1, widgets.line_color()),
            border_radius=18,
        )

    def share_bar(count, largest, color):
        """A track filled in proportion to `count` out of `largest`."""
        filled = round(1000 * count / largest) if largest else 0
        parts = []
        if filled:
            parts.append(ft.Container(bgcolor=color, border_radius=5, expand=filled))
        if filled < 1000:
            parts.append(ft.Container(expand=1000 - filled))
        return ft.Container(
            content=ft.Row(parts, spacing=0),
            height=10,
            bgcolor=widgets.tone("#E6EDF7", "#26384A"),
            border_radius=5,
            expand=True,
        )

    def share_row(label, count, total, largest, color, dot=False):
        percent = f"{round(100 * count / total)}%" if total else "0%"
        label_controls = [ft.Container(width=10, height=10, border_radius=5, bgcolor=color)] if dot else []
        label_controls.append(ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=widgets.heading_color(), expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, tooltip=label))
        label_controls.append(ft.Text(f"{count:,}", size=13, weight=ft.FontWeight.BOLD, color=widgets.link_color()))
        label_controls.append(ft.Text(percent, size=12, color=widgets.muted_color(), width=40, text_align=ft.TextAlign.RIGHT))
        return ft.Column(
            [
                ft.Row(label_controls, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([share_bar(count, largest, color)]),
            ],
            spacing=6,
        )

    def render_kpis(overview):
        cards = [
            ("Total Documents", "total_documents", "All tracked records", ft.Icons.DESCRIPTION_OUTLINED, ft.Colors.BLUE_700, open_documents_view),
            ("Active", "active_documents", "Not yet completed or archived", ft.Icons.LIBRARY_ADD_CHECK_OUTLINED, ft.Colors.GREEN_700, None),
            ("Pending", "pending_documents", "Awaiting action", ft.Icons.SCHEDULE_OUTLINED, ft.Colors.AMBER_800, None),
            ("Completed", "completed_documents", "Finished or approved", ft.Icons.CHECK_CIRCLE_OUTLINED, ft.Colors.TEAL_700, None),
            ("Archived", "archived_documents", "Closed records", ft.Icons.ARCHIVE_OUTLINED, ft.Colors.BROWN_400, open_archived_view),
            ("Added This Month", "added_this_month", "Registered since the 1st", ft.Icons.CALENDAR_MONTH_OUTLINED, ft.Colors.DEEP_PURPLE_600, None),
        ]
        controls = []
        for title, key, detail, icon, color, open_view in cards:
            stat = widgets.stat_card(title, f"{int(overview.get(key) or 0):,}", detail, icon, color, col={"xs": 12, "sm": 6, "lg": 4, "xl": 2}, tile=True)
            if open_view is not None:
                stat.on_click = lambda _, open_view=open_view: open_view()
                stat.ink = True
                stat.tooltip = f"Open {title.lower()}"
            controls.append(stat)
        kpi_row.controls = controls

    def render_status(status_data):
        ranked = top_counts(status_data, limit=len(status_data or {}) or 1)
        total = sum(count for _, count in ranked)
        largest = max((count for _, count in ranked), default=0)
        status_total.value = f"{total:,} document{'s' if total != 1 else ''}"
        status_list.controls = [
            share_row(label, count, total, largest, status_color(label), dot=True) for label, count in ranked
        ] or [widgets.empty_box("No documents yet. Status counts appear once documents are registered.")]

    def render_months(months):
        largest = max((row.get("count") or 0 for row in months), default=0)
        total = sum(row.get("count") or 0 for row in months)
        month_total.value = f"{total:,} registered"
        columns = []
        for index, row in enumerate(months):
            count = row.get("count") or 0
            latest = index == len(months) - 1
            height = max(4, round(MONTH_CHART_HEIGHT * count / largest)) if largest else 4
            columns.append(
                ft.Column(
                    [
                        ft.Text(str(count), size=12, weight=ft.FontWeight.BOLD, color=widgets.link_color() if count else widgets.muted_color()),
                        ft.Container(
                            bgcolor=widgets.accent() if latest else ft.Colors.with_opacity(0.45, widgets.accent()),
                            height=height,
                            border_radius=ft.border_radius.only(top_left=6, top_right=6),
                            tooltip=f"{row.get('month') or row.get('label')}: {count} registered",
                        ),
                        ft.Text(str(row.get("label") or "-"), size=12, color=widgets.heading_color() if latest else widgets.muted_color(), weight=ft.FontWeight.W_600 if latest else None),
                    ],
                    spacing=6,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    alignment=ft.MainAxisAlignment.END,
                    expand=True,
                )
            )
        month_chart.controls = columns or [widgets.empty_box("No monthly activity recorded yet.")]

    def breakdown_card(title, icon, subtitle, counts, empty_message):
        ranked = top_counts(counts)
        total = sum(count for _, count in ranked)
        largest = max((count for _, count in ranked), default=0)
        rows = [share_row(label, count, total, largest, widgets.accent()) for label, count in ranked]
        return ft.Container(
            card(ft.Column([widgets.card_title(title, icon, subtitle=subtitle), *(rows or [widgets.empty_box(empty_message)])], spacing=16)),
            col={"xs": 12, "lg": 4},
        )

    def render_breakdowns(payload):
        breakdown_row.controls = [
            breakdown_card("By Document Type", ft.Icons.DESCRIPTION_OUTLINED, "Ordinances, resolutions and other kinds.",
                           payload.get("document_types"), "No document types recorded."),
            breakdown_card("By Category", ft.Icons.LOCAL_OFFER_OUTLINED, "How documents are classified.",
                           payload.get("document_categories"), "No categories recorded."),
            breakdown_card("By Current Office", ft.Icons.ACCOUNT_BALANCE_OUTLINED, "Where documents are right now.",
                           payload.get("offices"), "No documents are held by an office."),
        ]

    def processing_tile(label, value, detail, icon, color):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(icon, color=color, size=22),
                        width=44, height=44, border_radius=12,
                        alignment=ft.Alignment(0, 0),
                        bgcolor=ft.Colors.with_opacity(0.12, color),
                    ),
                    ft.Column(
                        [
                            ft.Text(label, size=12, color=widgets.muted_color()),
                            ft.Text(value, size=20, weight=ft.FontWeight.BOLD, color=widgets.link_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            *([ft.Text(detail, size=11, color=widgets.muted_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)] if detail else []),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(12, 12, 12, 12),
            bgcolor=card_tint,
            border=ft.border.all(1, widgets.line_color()),
            border_radius=12,
            col={"xs": 10, "sm": 5, "xl": 2},
        )

    def render_processing(processing):
        average = processing.get("average_processing_days")
        longest = processing.get("longest_pending") or {}
        longest_days = longest.get("days")
        longest_number = longest.get("tracking_number")
        if not longest_number or longest_number == "N/A":
            longest_value, longest_detail = "None", "Nothing is pending"
        else:
            longest_value = longest_number
            longest_detail = f"Pending {longest_days} days" if isinstance(longest_days, (int, float)) else "Pending, age not recorded"
        processing_row.controls = [
            processing_tile("Average processing time", f"{average} days" if average is not None else "N/A",
                            "Registration to completion", ft.Icons.TIMER_OUTLINED, ft.Colors.BLUE_700),
            processing_tile("Awaiting action", f"{int(processing.get('awaiting_action') or 0):,}",
                            "Pending or in progress", ft.Icons.HOURGLASS_TOP, ft.Colors.AMBER_800),
            processing_tile("Longest pending", longest_value, longest_detail, ft.Icons.REPORT_PROBLEM_OUTLINED, ft.Colors.RED_700),
            processing_tile("Completed this month", f"{int(processing.get('completed_this_month') or 0):,}",
                            None, ft.Icons.TASK_ALT, ft.Colors.GREEN_700),
            processing_tile("Archived this month", f"{int(processing.get('archived_this_month') or 0):,}",
                            None, ft.Icons.INVENTORY_2_OUTLINED, ft.Colors.BROWN_400),
        ]

    def render_recent(documents):
        rows = []
        for item in documents:
            status = str(item.get("status") or "-")
            meta = [part for part in (item.get("document_type"), item.get("current_office"), item.get("date_registered")) if part]
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color=widgets.accent(), size=20),
                                width=40, height=40, border_radius=10,
                                alignment=ft.Alignment(0, 0),
                                bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.BLUE_700),
                            ),
                            ft.Column(
                                [
                                    ft.Text(item.get("tracking_number") or "-", size=13, weight=ft.FontWeight.BOLD, color=widgets.link_color()),
                                    ft.Text(item.get("title") or "Untitled", size=13, color=widgets.body_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, tooltip=item.get("title")),
                                    widgets.hint(" · ".join(str(part) for part in meta)),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            *([widgets.chip(str(item["priority"]), ft.Colors.RED_700 if str(item["priority"]).lower() in {"high", "urgent"} else ft.Colors.BLUE_GREY_600)] if item.get("priority") else []),
                            widgets.chip(status, status_color(status)),
                        ],
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(10, 8, 12, 8),
                    bgcolor=card_tint,
                    border=ft.border.all(1, widgets.line_color()),
                    border_radius=12,
                )
            )
        recent_list.controls = rows or [widgets.empty_box("No documents registered yet.")]

    def load_analytics(update=False):
        try:
            response = requests.get(f"{backend_url}/analytics", headers=headers, verify=False, timeout=10)
            if response.status_code != 200:
                raise Exception(response.text)
            payload = response.json()
        except Exception as exc:
            notice.content = widgets.empty_box(f"Unable to load analytics: {str(exc)[:200]}", icon=ft.Icons.ERROR_OUTLINE)
            notice.visible = True
            for target in (kpi_row, status_list, month_chart, breakdown_row, processing_row, recent_list):
                target.controls = []
        else:
            notice.visible = False
            render_kpis(payload.get("overview") or {})
            render_status(payload.get("status_breakdown") or {})
            render_months(payload.get("monthly_activity") or [])
            render_breakdowns(payload)
            render_processing(payload.get("processing") or {})
            render_recent(payload.get("recent_documents") or [])
        if update and page is not None:
            page.update()

    load_analytics()

    return ft.Column(
        controls=[
            widgets.banner(
                "Analytics", "Document volume, status and processing across every office.", ft.Icons.INSIGHTS,
                corner=ft.IconButton(ft.Icons.REFRESH, icon_color=ft.Colors.WHITE, tooltip="Refresh analytics", on_click=lambda _: load_analytics(update=True)),
            ),
            notice,
            kpi_row,
            ft.ResponsiveRow(
                [
                    ft.Container(
                        card(ft.Column([widgets.card_title("Document Status", ft.Icons.DONUT_LARGE, subtitle="Every document by its current status.", trailing=status_total), status_list], spacing=18)),
                        col={"xs": 12, "lg": 5},
                    ),
                    ft.Container(
                        card(ft.Column([widgets.card_title("Monthly Activity", ft.Icons.BAR_CHART, subtitle="Documents registered each month; the latest month is highlighted.", trailing=month_total), ft.Container(month_chart, padding=ft.Padding(4, 8, 4, 0))], spacing=18)),
                        col={"xs": 12, "lg": 7},
                    ),
                ],
                spacing=16,
                run_spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            card(ft.Column([widgets.card_title("Processing", ft.Icons.SPEED, subtitle="How quickly documents move from registration to completion."), processing_row], spacing=18)),
            breakdown_row,
            card(ft.Column([widgets.card_title("Recently Registered", ft.Icons.HISTORY, subtitle="The latest documents added to the system."), recent_list], spacing=16)),
        ],
        spacing=16,
    )
