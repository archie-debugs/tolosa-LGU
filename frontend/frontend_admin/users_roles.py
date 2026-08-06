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
    registration_requests_content=None,
):
    content = [
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
                                content=ft.Column([
                                    users_table,
                                ]),
                                expand=True,
                                bgcolor=ft.colors.BLUE_GREY_50,
                                border_radius=18,
                                padding=12,
                                height=240,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        spacing=20,
                    ),
                ],
                spacing=16,
            ),
        )
    ]

    if registration_requests_content is not None:
        content.append(ft.Container(height=24))
        content.append(registration_requests_content)

    # If the users table is empty, show a clear placeholder inside the users area
    try:
        rows = getattr(users_table, "rows", None) or []
        if len(rows) == 0:
            placeholder = ft.Container(
                content=ft.Column([
                    ft.Text("No users loaded", size=14, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_GREY_700),
                    ft.Text("The user list is empty — backend may be offline or no users exist.", size=12, color=ft.colors.BLUE_GREY_400),
                ], spacing=6),
                padding=18,
                bgcolor=ft.colors.TRANSPARENT,
            )
            # insert placeholder into the users table container (Row is at index 2 of the Column)
            # find the main Row and append placeholder below the table container (its right-side child is controls[1])
            content[0].content.controls[2].controls[1].content.controls.append(placeholder)
    except Exception:
        pass

    return ft.Column(content, spacing=16, expand=True)
