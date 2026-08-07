import flet as ft
import traceback


def render_shell(page, current_user, logout_user, nav_items, content_view):
    selected_index = 0
    nav_container = ft.Column(spacing=12)

    def switch_view(index: int):
        nonlocal selected_index
        selected_index = index
        build_nav()
        try:
            next_view = nav_items[index][2]()
        except Exception as exc:
            tb = traceback.format_exc()
            print("Error building view:\n", tb)
            # Show a helpful error box in the UI so it's clear what failed
            next_view = ft.Container(
                content=ft.Column([
                    ft.Text("Error loading view", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700),
                    ft.Text(str(exc), size=12, color=ft.Colors.RED_700),
                    ft.Container(height=8),
                    ft.Text("Traceback:", size=12, weight=ft.FontWeight.BOLD),
                    ft.Text(tb, size=10),
                ], spacing=8),
                padding=16,
                bgcolor=ft.Colors.WHITE,
                border=ft.Border.all(1, ft.Colors.RED_100),
                border_radius=8,
            )
        try:
            content_holder.content = next_view
            page.update()
        except Exception as exc2:
            tb2 = traceback.format_exc()
            print("Error assigning/updating view:\n", tb2)
            fallback = ft.Container(
                content=ft.Column([
                    ft.Text("Error rendering view", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700),
                    ft.Text(str(exc2), size=12, color=ft.Colors.RED_700),
                    ft.Container(height=8),
                    ft.Text("Traceback:", size=12, weight=ft.FontWeight.BOLD),
                    ft.Text(tb2, size=10),
                ], spacing=8),
                padding=16,
                bgcolor=ft.Colors.WHITE,
                border=ft.Border.all(1, ft.Colors.RED_100),
                border_radius=8,
            )
            content_holder.content = fallback
            try:
                page.update()
            except Exception:
                pass

    def build_nav():
        nav_container.controls.clear()
        nav_container.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=ft.Colors.WHITE),
                            padding=10,
                            bgcolor=ft.Colors.BLUE_800,
                            border_radius=12,
                        ),
                        ft.Text("SB Tolosa", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                        ft.Text("Admin Dashboard", size=12, color=ft.Colors.BLUE_GREY_600),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                ),
                padding=ft.Padding.only(top=6, bottom=8),
                alignment=ft.Alignment.TOP_CENTER,
            )
        )
        for idx, (icon, label, _) in enumerate(nav_items):
            is_selected = idx == selected_index
            nav_container.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(icon, color=ft.Colors.BLUE_800 if is_selected else ft.Colors.BLUE_GREY_700),
                            ft.Container(width=8),
                            ft.Text(label, size=12, color=ft.Colors.BLUE_800 if is_selected else ft.Colors.BLUE_GREY_700),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                    width=200,
                    bgcolor=ft.Colors.BLUE_50 if is_selected else None,
                    border_radius=10,
                    on_click=lambda e, i=idx: switch_view(i),
                )
            )
        nav_container.controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.LOGOUT, color=ft.Colors.RED_700),
                        ft.Container(width=8),
                        ft.Text("Log out", size=12, color=ft.Colors.RED_700),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                width=200,
                border_radius=10,
                on_click=lambda e: logout_user(),
            )
        )

    content_holder = ft.Container(
        expand=True,
        content=content_view if content_view is not None else ft.Container(content=ft.Text("Documents view unavailable")),
        padding=0,
    )

    build_nav()
    page.clean()
    page.horizontal_alignment = ft.CrossAxisAlignment.START
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.add(
        ft.Row(
            [
                ft.Container(
                    width=220,
                    padding=ft.Padding.only(top=8, right=6),
                    content=nav_container,
                    bgcolor=None,
                    border_radius=12,
                    alignment=ft.Alignment.TOP_CENTER,
                ),
                ft.Container(
                    expand=True,
                    padding=ft.Padding.only(top=8),
                    content=ft.Container(
                        expand=True,
                        padding=20,
                        bgcolor=ft.Colors.WHITE,
                        border_radius=12,
                        border=ft.Border.all(1, ft.Colors.BLUE_GREY_50),
                        content=content_holder,
                    ),
                ),
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )
    page.update()
    switch_view(0)
    return page
