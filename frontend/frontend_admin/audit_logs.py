import flet as ft


def build_audit_logs_view(
    audit_logs_table,
    load_audit_logs_view,
    surface_card,
    section_header,
):
    load_audit_logs_view()
    return ft.Column(
        [
            surface_card(
                ft.Column(
                    [
                        section_header(
                            "Audit Logs",
                            "System Activity & History Logs",
                            ft.icons.HISTORY,
                            ft.colors.ORANGE_700,
                        ),
                        ft.Divider(height=1),
                        ft.Container(
                            content=audit_logs_table,
                            bgcolor=ft.colors.BLUE_GREY_50,
                            border_radius=18,
                            padding=12,
                        ),
                    ],
                    spacing=16,
                ),
            )
        ],
        expand=True,
    )
