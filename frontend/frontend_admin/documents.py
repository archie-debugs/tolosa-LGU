import flet as ft


def build_documents_view(
    documents_table,
    documents_notice,
    open_document_dialog,
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
                            "View and manage legislative documents and tracking status.",
                            ft.icons.DESCRIPTION_OUTLINED,
                            ft.colors.BLUE_700,
                        ),
                        ft.Divider(height=1),
                        ft.Row(
                            [
                                ft.Text(
                                    "This UI is a frontend-only preview. Document data is static for now.",
                                    size=13,
                                    color=ft.colors.BLUE_GREY_600,
                                    expand=True,
                                ),
                                ft.ElevatedButton(
                                    "Refresh Preview",
                                    icon=ft.icons.REFRESH,
                                    on_click=lambda _: open_document_dialog(None),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Container(
                            content=documents_table,
                            bgcolor=ft.colors.BLUE_GREY_50,
                            border_radius=18,
                            padding=12,
                        ),
                        ft.Text(documents_notice.value, size=12, color=ft.colors.BLUE_GREY_600),
                    ],
                    spacing=16,
                ),
            )
        ],
        expand=True,
    )
