import flet as ft


def build_users_roles_view(
    user_username_input,
    user_password_input,
    user_role_input,
    users_notice,
    users_table,
    create_user_record,
    surface_card,
    section_header,
):
    return ft.Column(
        [
            surface_card(
                ft.Column(
                    [
                        section_header(
                            "Users & Roles",
                            "Manage admin users, roles, and account access for the system.",
                            ft.icons.PEOPLE,
                            ft.colors.BLUE_700,
                        ),
                        ft.Divider(height=1),
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        user_username_input,
                                        user_password_input,
                                        user_role_input,
                                        ft.ElevatedButton(
                                            "Create User",
                                            on_click=create_user_record,
                                            bgcolor=ft.colors.BLUE_800,
                                            color=ft.colors.WHITE,
                                        ),
                                        users_notice,
                                    ],
                                    spacing=12,
                                    width=360,
                                ),
                                ft.Container(
                                    content=users_table,
                                    expand=True,
                                    bgcolor=ft.colors.BLUE_GREY_50,
                                    border_radius=18,
                                    padding=12,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            spacing=20,
                        ),
                    ],
                    spacing=16,
                ),
            )
        ],
        expand=True,
    )
