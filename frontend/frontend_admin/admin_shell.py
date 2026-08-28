import flet as ft
import traceback


def render_shell(
    page,
    current_user,
    logout_user,
    nav_items,
    content_view,
    initial_selected_index: int = 0,
):
    selected_index = initial_selected_index
    shell_nav_items = list(nav_items)
    is_dark = page.theme_mode == ft.ThemeMode.DARK
    try:
        stored_night_mode = page.client_storage.get("sb_night_mode")
        if stored_night_mode is not None:
            is_dark = bool(stored_night_mode)
    except Exception:
        pass

    surface_color = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
    sidebar_color = "#111c22" if is_dark else None
    text_color = ft.Colors.WHITE if is_dark else ft.Colors.BLUE_GREY_700
    heading_color = ft.Colors.WHITE if is_dark else ft.Colors.BLUE_900
    selected_color = ft.Colors.BLUE_GREY_800 if is_dark else ft.Colors.BLUE_50
    page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT

    def night_mode_setting():
        return ft.Switch(
            label="Night mode",
            value=is_dark,
            on_change=toggle_night_mode,
        )

    def shared_settings_view():
        return ft.Container(
            padding=20,
            bgcolor=surface_color,
            content=ft.Column(
                [
                    ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD, color=heading_color),
                    ft.Text("Personalize your workspace appearance.", color=text_color),
                    night_mode_setting(),
                ],
                spacing=16,
            ),
        )

    if not any(label == "Settings" for _, label, _ in shell_nav_items):
        shell_nav_items.append((ft.Icons.SETTINGS_OUTLINED, "Settings", shared_settings_view))

    # =========================================================
    # SIDEBAR
    # =========================================================

    nav_container = ft.Column(
        spacing=12,
        expand=False,
    )

    # =========================================================
    # CONTENT HOLDER
    # =========================================================

    content_holder = ft.Container(
        padding=0,
        bgcolor=surface_color,
        border=None,
        border_radius=0,
        expand=True,
        content=(
            content_view
            if content_view is not None
            else ft.Container(
                content=ft.Text(
                    "Documents view unavailable",
                    color=ft.Colors.BLUE_GREY_700,
                ),
                bgcolor=surface_color,
            )
        ),
    )

    # =========================================================
    # SWITCH VIEW
    # =========================================================

    def switch_view(index: int):
        nonlocal selected_index

        selected_index = index
        build_nav()

        try:
            next_view = shell_nav_items[index][2]()
            if shell_nav_items[index][1] == "Settings" and shell_nav_items[index][2] is not shared_settings_view:
                next_view = ft.Column([next_view, night_mode_setting()], spacing=16)

        except Exception as exc:
            tb = traceback.format_exc()

            print("Error building view:")
            print(tb)

            side = ft.BorderSide(1, ft.Colors.RED_100)

            next_view = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Error loading view",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.RED_700,
                        ),
                        ft.Text(
                            str(exc),
                            size=12,
                            color=ft.Colors.RED_700,
                        ),
                        ft.Text(
                            "Traceback:",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            tb,
                            size=10,
                        ),
                    ],
                    spacing=8,
                ),
                padding=16,
                bgcolor=surface_color,
                border=ft.Border(top=side, right=side, bottom=side, left=side),
                border_radius=8,
            )

        content_holder.content = next_view

        try:
            page.update()

        except Exception as exc2:
            tb2 = traceback.format_exc()

            print("Error assigning/updating view:")
            print(tb2)

            side2 = ft.BorderSide(1, ft.Colors.RED_100)

            content_holder.content = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Error rendering view",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.RED_700,
                        ),
                        ft.Text(
                            str(exc2),
                            size=12,
                            color=ft.Colors.RED_700,
                        ),
                        ft.Text(
                            "Traceback:",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            tb2,
                            size=10,
                        ),
                    ],
                    spacing=8,
                ),
                padding=16,
                bgcolor=surface_color,
                border=ft.Border(top=side2, right=side2, bottom=side2, left=side2),
                border_radius=8,
            )

            try:
                page.update()
            except Exception:
                pass

    def toggle_night_mode(_):
        nonlocal is_dark, surface_color, sidebar_color, text_color, heading_color, selected_color

        is_dark = not is_dark
        page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        surface_color = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        sidebar_color = "#111c22" if is_dark else None
        text_color = ft.Colors.WHITE if is_dark else ft.Colors.BLUE_GREY_700
        heading_color = ft.Colors.WHITE if is_dark else ft.Colors.BLUE_900
        selected_color = ft.Colors.BLUE_GREY_800 if is_dark else ft.Colors.BLUE_50
        try:
            page.client_storage.set("sb_night_mode", is_dark)
        except Exception:
            pass
        page.bgcolor = surface_color
        content_holder.bgcolor = surface_color
        build_nav()
        page.update()

    # =========================================================
    # BUILD NAVIGATION
    # =========================================================

    def build_nav():
        nav_container.controls.clear()

        # -----------------------------------------------------
        # SIDEBAR HEADER
        # -----------------------------------------------------

        nav_container.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.ACCOUNT_BALANCE,
                                color=ft.Colors.WHITE,
                            ),
                            padding=10,
                            bgcolor=ft.Colors.BLUE_800,
                            border_radius=12,
                        ),
                        ft.Text(
                            "SB Tolosa",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=heading_color,
                        ),
                        ft.Text(
                            "Admin Panel",
                            size=12,
                            color=(ft.Colors.BLUE_GREY_300 if is_dark else ft.Colors.BLUE_GREY_600),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                ),
                padding=ft.Padding(
                    left=0,
                    top=6,
                    right=0,
                    bottom=8,
                ),
                alignment=ft.Alignment.TOP_CENTER,
            )
        )

        # -----------------------------------------------------
        # NAVIGATION ITEMS

        for idx, (icon, label, _) in enumerate(shell_nav_items):

            is_selected = idx == selected_index

            nav_container.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                icon,
                                color=(
                                    ft.Colors.BLUE_800
                                    if is_selected
                                    else text_color
                                ),
                            ),
                            ft.Container(width=8),
                            ft.Text(
                                label,
                                size=12,
                                color=(
                                    ft.Colors.BLUE_800
                                    if is_selected
                                    else text_color
                                ),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(left=12, top=10, right=12, bottom=10),
                    width=200,
                    bgcolor=(selected_color if is_selected else None),
                    border_radius=10,
                    on_click=lambda e, i=idx: switch_view(i),
                )
            )

        # -----------------------------------------------------
        # LOGOUT
        # -----------------------------------------------------

        nav_container.controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.LOGOUT,
                            color=ft.Colors.RED_700,
                        ),
                        ft.Container(width=8),
                        ft.Text(
                            "Log out",
                            size=12,
                            color=ft.Colors.RED_700,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(left=12, top=10, right=12, bottom=10),
                width=200,
                border_radius=10,
                on_click=lambda e: logout_user(),
            )
        )

    # =========================================================
    # INITIAL NAVIGATION
    # =========================================================

    build_nav()

    # =========================================================
    # RESET PAGE
    # =========================================================

    page.clean()

    page.horizontal_alignment = ft.CrossAxisAlignment.START
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.bgcolor = surface_color

    # =========================================================
    # MAIN LAYOUT
    # =========================================================

    page.add(
        ft.Row(
            [
                # =================================================
                # SIDEBAR
                # =================================================

                ft.Container(
                    width=220,
                    padding=ft.Padding(
                        left=0,
                        top=8,
                        right=6,
                        bottom=0,
                    ),
                    content=nav_container,
                    bgcolor=sidebar_color,
                    border=None,
                    border_radius=0,
                    alignment=ft.Alignment.TOP_CENTER,
                ),

                # =================================================
                # MAIN CONTENT
                # =================================================

                ft.Container(
                    expand=True,
                    padding=ft.Padding(
                        top=8,
                        left=8,
                        right=8,
                        bottom=8,
                    ),
                    bgcolor=surface_color,
                    border=None,
                    border_radius=0,
                    content=content_holder,
                ),
            ],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )

    # =========================================================
    # UPDATE PAGE
    # =========================================================

    page.update()

    # =========================================================
    # LOAD FIRST VIEW
    # =========================================================

    switch_view(initial_selected_index)

    return page