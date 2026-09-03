import flet as ft

if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors
if not hasattr(ft, "Icons") and hasattr(ft, "icons"):
    ft.Icons = ft.icons


def build_audit_logs_view(
    audit_logs_table,
    load_audit_logs_view,
    surface_card,
    section_header,
    summary_cards=None,
    filter_bar=None,
    action_bar=None,
    pagination_bar=None,
    details_dialog=None,
):
    if callable(load_audit_logs_view):
        load_audit_logs_view()

    page_header = section_header(
        "Audit Logs",
        "Monitor and review system activities and administrative actions.",
        ft.Icons.HISTORY_OUTLINED,
        ft.Colors.BLUE_700,
    )

    table_container = ft.Container(
        content=audit_logs_table,
        width="100%",
        padding=12,
        border_radius=18,
        border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
        bgcolor=ft.Colors.BLUE_GREY_50,
        expand=False,
    )

    if summary_cards is None:
        summary_cards = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Column([
                        ft.Text("Total Activities", size=11, color=ft.Colors.BLUE_GREY_600),
                        ft.Text("0", size=22, weight=ft.FontWeight.BOLD),
                    ], spacing=3),
                    width=170,
                    padding=12,
                    border_radius=14,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    bgcolor=ft.Colors.BLUE_GREY_50,
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Today", size=11, color=ft.Colors.BLUE_GREY_600),
                        ft.Text("0", size=22, weight=ft.FontWeight.BOLD),
                    ], spacing=3),
                    width=170,
                    padding=12,
                    border_radius=14,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    bgcolor=ft.Colors.BLUE_GREY_50,
                ),
            ],
            spacing=12,
            wrap=True,
        )

    if filter_bar is None:
        filter_bar = surface_card(
            ft.Column([
                ft.Text("Filters", size=13, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.TextField(label="Search", hint_text="Search audit logs...", width=220),
                    ft.Dropdown(label="Date Range", width=170, value="last_30_days"),
                    ft.Dropdown(label="User", width=170, value="All Users"),
                    ft.Dropdown(label="Module", width=170, value="All Modules"),
                    ft.Dropdown(label="Action", width=170, value="All Actions"),
                    ft.Dropdown(label="Status", width=150, value="All Status"),
                    ft.ElevatedButton("Apply Filters"),
                    ft.TextButton("Clear Filters"),
                ], wrap=True, spacing=10),
            ], spacing=10, tight=True),
            padding=14,
            expand=False,
        )

    if action_bar is None:
        action_bar = surface_card(
            ft.Row([
                ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH),
                ft.OutlinedButton("Export", icon=ft.Icons.DOWNLOAD),
            ], spacing=8, wrap=True),
            padding=10,
            expand=False,
        )

    final_controls = [
        surface_card(
            ft.Column(
                controls=[
                    page_header,
                    ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                ],
                spacing=12,
                tight=True,
            ),
            padding=18,
            expand=False,
        )
    ]

    final_controls.append(summary_cards)
    final_controls.append(filter_bar)
    final_controls.append(action_bar)

    final_controls.append(
        surface_card(
            ft.Column(
                controls=[
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.TABLE_ROWS_OUTLINED, size=18, color=ft.Colors.BLUE_700),
                            ft.Text("Recent Activity", size=15, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    table_container,
                ],
                spacing=10,
                tight=True,
            ),
            padding=12,
            expand=False,
        )
    )

    if pagination_bar is not None:
        final_controls.append(pagination_bar)

    return ft.Column(
        controls=final_controls,
        spacing=12,
        tight=True,
        expand=False,
    )
