import flet as ft


def build_documents_view(
    title_input,
    type_dropdown,
    committee_input,
    search_field,
    type_filter,
    status_filter,
    data_table,
    import_button,
    submit_button,
    surface_card,
    section_header,
):
    return ft.Column(
        [
            surface_card(
                ft.Column(
                    [
                        section_header(
                            "Documents",
                            "Active Legislative Tracker & Document Registration",
                            ft.icons.LIST_ALT,
                            ft.colors.BLUE_800,
                        ),
                        ft.Divider(height=1),
                        ft.Row([title_input, import_button], spacing=16),
                        ft.Row([type_dropdown, committee_input, submit_button], spacing=16),
                        ft.Container(height=6),
                        ft.Row([search_field, type_filter, status_filter], spacing=15),
                        ft.Container(height=4),
                        ft.Container(
                            content=data_table,
                            bgcolor=ft.colors.BLUE_GREY_50,
                            border_radius=18,
                            padding=12,
                        ),
                    ],
                    spacing=16,
                    expand=True,
                ),
                expand=True,
            )
        ],
        expand=True,
    )
