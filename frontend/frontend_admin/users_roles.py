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
                            "Create accounts, set roles, and remove users from the system.",
                            ft.icons.PEOPLE,
                            ft.colors.INDIGO_700,
                        ),
                        ft.Divider(height=1),
                        ft.Row([user_username_input, user_password_input, user_role_input], spacing=12, wrap=True),
                        ft.Row([ft.ElevatedButton("Create User", icon=ft.icons.PERSON_ADD, on_click=create_user_record)], spacing=12),
                        users_notice,
                        ft.Container(
                            content=users_table,
                            bgcolor=ft.colors.BLUE_GREY_50,
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
