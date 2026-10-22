"""Committees screen: the standing committee names used for document assignment and reporting."""

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets


def build_committees_view(page, committees, surface_card, open_committee_dialog, confirm_delete_committee):
    """`committees` is a list of {"name"}. `open_committee_dialog(index)` edits one, or adds one when
    index is None; `confirm_delete_committee(index)` asks before deleting it."""
    widgets = TrackingWidgets(page)

    def committee_row(index, committee):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(str(index + 1), size=14, weight=ft.FontWeight.BOLD, color=widgets.accent()),
                        width=40, height=40, border_radius=20,
                        alignment=ft.Alignment(0, 0),
                        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.BLUE_700),
                    ),
                    ft.Text(committee["name"], size=15, weight=ft.FontWeight.W_600, color=widgets.link_color(), expand=True),
                    ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_color=widgets.accent(), tooltip="Edit", on_click=lambda _, i=index: open_committee_dialog(i)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_600, tooltip="Delete", on_click=lambda _, i=index: confirm_delete_committee(i)),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(10, 6, 8, 6),
            bgcolor=widgets.tone("#F7FAFE", "#1B2430"),
            border=ft.border.all(1, widgets.line_color()),
            border_radius=12,
        )

    count = len(committees)
    rows = [committee_row(index, committee) for index, committee in enumerate(committees)] or [
        widgets.empty_box("No committees yet. Add one to use it for document assignment and reporting.")
    ]
    add_button = ft.FilledButton(
        "Add Committee", icon=ft.Icons.ADD, on_click=lambda _: open_committee_dialog(None), height=44,
        style=ft.ButtonStyle(shape=ft.StadiumBorder(), bgcolor=ft.Colors.WHITE, color=ft.Colors.BLUE_800, padding=ft.Padding(18, 0, 18, 0)),
    )
    return ft.Column(
        [
            widgets.banner("Committees", "Reference list of SB committee assignments and organization.", ft.Icons.GROUPS, actions=[add_button]),
            surface_card(
                ft.Column(
                    [
                        widgets.card_title(
                            "Standing committees", ft.Icons.GROUPS_OUTLINED,
                            subtitle="These are the standing committee names used for document assignment and reporting.",
                            trailing=ft.Text(f"{count} committee{'s' if count != 1 else ''}", size=13, color=widgets.body_color()),
                        ),
                        ft.Column(rows, spacing=12),
                    ],
                    spacing=18,
                ),
                padding=20,
            ),
        ],
        spacing=16,
    )
