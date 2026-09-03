import flet as ft


def build_committees_view(
    committee_table,
    open_committee_dialog,
    surface_card,
    section_header,
):
    return ft.Column(
        [
            surface_card(
                ft.Column(
                    [
                        section_header(
                            "Committees",
                            "Reference list of SB committee assignments and organization.",
                            ft.Icons.GROUP,
                            ft.Colors.GREEN_700,
                        ),
                        ft.Divider(height=1),
                        ft.Row([
                            ft.Text(
                                "These are the standing committee names used for document assignment and reporting.",
                                size=13,
                                color=ft.Colors.BLUE_GREY_600,
                            ),
                            ft.Button("Add Committee", icon=ft.Icons.ADD, on_click=lambda _: open_committee_dialog(None)),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Container(
                            content=committee_table,
                            bgcolor=ft.Colors.BLUE_GREY_50,
                            border_radius=18,
                            padding=12,
                        ),
                    ],
                    spacing=14,
                ),
            )
        ],
        expand=True,
    )
