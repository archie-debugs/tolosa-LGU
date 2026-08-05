import flet as ft


def render_shell(page, current_user, logout_user, nav_items, content_view):
    header = ft.Container(
        padding=ft.padding.symmetric(vertical=16, horizontal=16),
        bgcolor=ft.colors.WHITE,
        border_radius=16,
        border=ft.border.all(1, ft.colors.BLUE_GREY_50),
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.icons.ACCOUNT_BALANCE, size=22, color=ft.colors.WHITE),
                            padding=10,
                            bgcolor=ft.colors.BLUE_800,
                            border_radius=12,
                        ),
                        ft.Column(
                            [
                                ft.Text("SB Tolosa — Administration Dashboard", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_900),
                                ft.Text("System Administration and Document Management Overview", size=12, color=ft.colors.BLUE_GREY_600),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                    expand=True,
                ),
                ft.Row(
                    [
                        ft.IconButton(icon=ft.icons.NOTIFICATIONS_OUTLINED, tooltip="Notifications"),
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Icon(ft.icons.ACCOUNT_CIRCLE_OUTLINED, size=24, color=ft.colors.BLUE_700),
                                        padding=4,
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text(current_user or "Administrator", size=13, weight=ft.FontWeight.W_600),
                                            ft.Text("Administrator", size=12, color=ft.colors.BLUE_GREY_600),
                                        ],
                                        spacing=1,
                                        horizontal_alignment=ft.CrossAxisAlignment.START,
                                    ),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=8,
                            ),
                            padding=ft.padding.symmetric(horizontal=8, vertical=6),
                            bgcolor=ft.colors.BLUE_GREY_50,
                            border_radius=10,
                        ),
                        ft.IconButton(icon=ft.icons.LOGOUT, tooltip="Log out", on_click=lambda _: logout_user()),
                    ],
                    spacing=8,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
    )

    selected_index = 0
    nav_container = ft.Column(spacing=12)

    def switch_view(index: int):
        nonlocal selected_index
        selected_index = index
        build_nav()
        try:
            next_view = nav_items[index][2]()
        except Exception:
            next_view = ft.Text("Error loading view")
        content_holder.content = next_view
        page.update()

    def build_nav():
        nav_container.controls.clear()
        nav_container.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Container(
                            content=ft.Icon(ft.icons.DASHBOARD, color=ft.colors.BLUE_800),
                            padding=8,
                            bgcolor=ft.colors.BLUE_50,
                            border_radius=12,
                        ),
                        ft.Text("Admin", size=12, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_900),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                ),
                padding=ft.padding.only(top=6, bottom=8),
                alignment=ft.alignment.top_center,
            )
        )
        for idx, (icon, label, _) in enumerate(nav_items):
            is_selected = idx == selected_index
            nav_container.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(icon, color=ft.colors.BLUE_800 if is_selected else ft.colors.BLUE_GREY_700),
                            ft.Container(width=8),
                            ft.Text(label, size=12, color=ft.colors.BLUE_800 if is_selected else ft.colors.BLUE_GREY_700),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(vertical=10, horizontal=12),
                    width=200,
                    bgcolor=ft.colors.BLUE_50 if is_selected else None,
                    border_radius=10,
                    on_click=lambda e, i=idx: switch_view(i),
                )
            )

    content_holder = ft.Container(
        expand=True,
        content=content_view if content_view is not None else ft.Text("Documents view unavailable"),
        padding=0,
    )

    build_nav()
    page.clean()
    page.horizontal_alignment = ft.CrossAxisAlignment.START
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.add(
        ft.Column(
            [
                header,
                ft.Row(
                    [
                        ft.Container(
                            width=200,
                            padding=ft.padding.only(top=8, right=6),
                            content=nav_container,
                            bgcolor=None,
                            border_radius=12,
                            alignment=ft.alignment.top_center,
                        ),
                        ft.Container(
                            expand=True,
                            padding=ft.padding.only(top=8),
                            content=ft.Container(
                                expand=True,
                                padding=20,
                                bgcolor=ft.colors.WHITE,
                                border_radius=12,
                                border=ft.border.all(1, ft.colors.BLUE_GREY_50),
                                content=content_holder,
                            ),
                        ),
                    ],
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=16,
            expand=True,
        )
    )
    page.update()
    switch_view(0)
    return page
