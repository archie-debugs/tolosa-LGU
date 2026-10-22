"""Audit Logs screen: who did what, when, and whether it worked.

The admin app owns the table, filters and loading; this lays them out in the shared banner and card styling.
"""

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets

if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors
if not hasattr(ft, "Icons") and hasattr(ft, "icons"):
    ft.Icons = ft.icons


def style_audit_table(widgets, table):
    """Theme the table for the current mode; the app builds it once, before night mode can change."""
    table.heading_row_color = widgets.tint()
    table.heading_text_style = ft.TextStyle(size=12, weight=ft.FontWeight.BOLD, color=widgets.heading_color())
    table.data_text_style = ft.TextStyle(size=12, color=widgets.body_color())
    table.border = ft.border.all(1, widgets.line_color())
    table.horizontal_lines = ft.BorderSide(1, widgets.line_color())
    table.border_radius = 12
    table.heading_row_height = 42
    table.data_row_min_height = 48
    table.data_row_max_height = 56
    table.show_checkbox_column = False


def build_audit_logs_view(
    page,
    audit_logs_table,
    load_audit_logs_view,
    *,
    summary_cards,
    filter_fields,
    apply_filters,
    clear_filters,
    export,
    pagination_bar,
):
    """`filter_fields` are the search box and dropdowns, restyled here. `summary_cards` and `pagination_bar`
    are rows the app refills on every load, so they are placed as they are rather than copied."""
    widgets = TrackingWidgets(page)
    if callable(load_audit_logs_view):
        load_audit_logs_view()

    style_audit_table(widgets, audit_logs_table)
    search_field, *dropdowns = filter_fields
    widgets.style_field(search_field, hint="Search user, action or details")
    search_field.prefix_icon = ft.Icons.SEARCH
    search_field.width = None
    search_field.expand = True
    search_field.on_submit = lambda _: apply_filters()
    for dropdown in dropdowns:
        widgets.style_field(dropdown)
        dropdown.width = 170

    filters_card = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        widgets.labelled(search_field),
                        ft.FilledButton("Apply", icon=ft.Icons.FILTER_ALT_OUTLINED, height=44, on_click=lambda _: apply_filters()),
                        ft.TextButton("Clear", icon=ft.Icons.FILTER_ALT_OFF_OUTLINED, on_click=lambda _: clear_filters()),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row([widgets.labelled(dropdown) for dropdown in dropdowns], spacing=16, wrap=True, run_spacing=12),
            ],
            spacing=16,
            tight=True,
        ),
        padding=20,
        bgcolor=widgets.card_color(),
        border=ft.border.all(1, widgets.line_color()),
        border_radius=18,
        expand=False,
    )

    table_container = ft.Container(
        content=ft.Row([audit_logs_table], scroll=ft.ScrollMode.AUTO),
        padding=12,
        border_radius=18,
        bgcolor=widgets.card_color(),
        border=ft.border.all(1, widgets.line_color()),
        expand=False,
    )

    results_card = ft.Container(
        content=ft.Column(
            [
                widgets.card_title("Activity", ft.Icons.TABLE_ROWS_OUTLINED, subtitle="Newest first. Select a row to see its full details."),
                table_container,
                pagination_bar,
            ],
            spacing=14,
            tight=True,
        ),
        padding=20,
        bgcolor=widgets.card_color(),
        border=ft.border.all(1, widgets.line_color()),
        border_radius=18,
        expand=False,
    )

    export_button = ft.FilledButton(
        "Export", icon=ft.Icons.DOWNLOAD, on_click=export, height=44,
        style=ft.ButtonStyle(shape=ft.StadiumBorder(), bgcolor=ft.Colors.WHITE, color=ft.Colors.BLUE_800, padding=ft.Padding(18, 0, 18, 0)),
    )
    return ft.Column(
        controls=[
            widgets.banner(
                "Audit Logs", "Monitor and review system activity and administrative actions.", ft.Icons.HISTORY,
                actions=[export_button],
                corner=ft.IconButton(ft.Icons.REFRESH, icon_color=ft.Colors.WHITE, tooltip="Refresh", on_click=lambda _: load_audit_logs_view()),
            ),
            summary_cards,
            filters_card,
            results_card,
        ],
        spacing=16,
        tight=True,
        expand=False,
    )
