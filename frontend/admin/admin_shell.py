import flet as ft
import traceback

# Nav items in this section are pinned to the bottom of the sidebar.
FOOTER_SECTION = "Account"
# Nav items in this section are opened from the profile menu instead of the sidebar.
MENU_SECTION = "Menu"
# Below this width the profile button shows only the initials.
COMPACT_WIDTH = 600


def initials(name):
    words = (name or "").split()
    if len(words) >= 2:
        return (words[0][0] + words[-1][0]).upper()
    return (words[0][:2] if words else "?").upper()


def render_shell(
    page,
    current_user,
    logout_user,
    nav_items,
    content_view,
    initial_selected_index: int = 0,
    account=None,
):
    """Draw the sidebar, the profile bar and `content_view`.

    `account` describes the signed-in user for the profile menu:
    {"name", "role", "office", "on_change_password"}; missing keys fall back to `current_user`.
    """
    account = account or {}
    selected_index = initial_selected_index
    shell_nav_items = list(nav_items)
    # Below COMPACT_WIDTH the sidebar becomes a drawer opened from the profile bar.
    compact = (getattr(page, "width", None) or 1200) < COMPACT_WIDTH
    drawer_open = False
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

    def apply_view_theme(control):
        if control is None:
            return
        if is_dark:
            if isinstance(control, ft.Text):
                if control.color in {
                    ft.Colors.BLUE_GREY_900,
                    ft.Colors.BLUE_GREY_800,
                    ft.Colors.BLUE_GREY_700,
                    ft.Colors.BLUE_GREY_600,
                    ft.Colors.BLUE_GREY_500,
                    ft.Colors.BLUE_900,
                }:
                    control.color = ft.Colors.BLUE_GREY_100
            elif isinstance(control, (ft.TextField, ft.Dropdown)):
                control.bgcolor = "#14212B"
                control.focused_bgcolor = "#1b2d3a"
                if isinstance(control, ft.Dropdown):
                    control.filled = True
                control.color = ft.Colors.BLUE_GREY_100
                control.text_style = ft.TextStyle(color=ft.Colors.BLUE_GREY_100)
                control.label_style = ft.TextStyle(color=ft.Colors.BLUE_GREY_300)
                control.hint_style = ft.TextStyle(color="#64748b")
                control.border_color = ft.Colors.WHITE
                control.focused_border_color = ft.Colors.WHITE
                if isinstance(control, ft.TextField):
                    control.cursor_color = "#3B82F6"
                    if isinstance(control.prefix_icon, ft.Icon):
                        control.prefix_icon.color = "#334653"
            elif hasattr(control, "bgcolor") and control.bgcolor in {
                ft.Colors.WHITE,
                ft.Colors.BLUE_GREY_50,
            }:
                control.bgcolor = ft.Colors.GREY_900 if control.bgcolor == ft.Colors.WHITE else "#26343a"
        for child in getattr(control, "controls", []) or []:
            apply_view_theme(child)
        content = getattr(control, "content", None)
        if content is not None:
            apply_view_theme(content)

    # Nav items are (icon, label, view) or (icon, label, view, section).
    shell_nav_items = [item if len(item) == 4 else (*item, None) for item in shell_nav_items]

    # =========================================================
    # SIDEBAR
    # =========================================================

    nav_container = ft.Column(
        spacing=2,
        expand=False,
    )
    footer_container = ft.Column(
        spacing=2,
        expand=False,
    )

    def natural_height_view(view):
        if hasattr(view, "expand"):
            view.expand = False
        return view

    content_scroll = ft.Column(
        controls=[natural_height_view(content_view)] if content_view is not None else [],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
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
        content=content_scroll,
    )

    # =========================================================
    # SWITCH VIEW
    # =========================================================

    def switch_view(index: int):
        nonlocal selected_index

        selected_index = index
        build_nav()
        build_profile_bar()
        set_drawer(False)

        try:
            next_view = shell_nav_items[index][2]()
            next_view = natural_height_view(next_view)
            apply_view_theme(next_view)

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

        content_scroll.controls = [next_view]

        try:
            page.update()

        except Exception as exc2:
            tb2 = traceback.format_exc()

            print("Error assigning/updating view:")
            print(tb2)

            side2 = ft.BorderSide(1, ft.Colors.RED_100)

            content_scroll.controls = [ft.Container(
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
            )]

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
        main_panel.bgcolor = surface_color
        style_sidebar()
        switch_view(selected_index)

    # =========================================================
    # BUILD NAVIGATION
    # =========================================================

    def nav_tile(icon, label, color, on_click, bgcolor=None):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, color=color, size=20),
                    ft.Container(width=8),
                    ft.Text(label, size=12, color=color),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(left=12, top=8, right=12, bottom=8),
            width=200,
            bgcolor=bgcolor,
            border_radius=10,
            on_click=on_click,
        )

    def section_header(title):
        return ft.Container(
            content=ft.Text(
                title.upper(),
                size=10,
                weight=ft.FontWeight.BOLD,
                color=(ft.Colors.BLUE_GREY_300 if is_dark else ft.Colors.BLUE_GREY_400),
            ),
            padding=ft.Padding(left=12, top=14, right=12, bottom=4),
            width=200,
        )

    def build_nav():
        nav_container.controls.clear()
        footer_container.controls.clear()

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

        # A header is drawn whenever the section changes, so empty sections
        # never show one. Footer-section items go to the pinned footer.

        current_section = None

        for idx, (icon, label, _, section) in enumerate(shell_nav_items):

            is_selected = idx == selected_index
            tile = nav_tile(
                icon,
                label,
                ft.Colors.BLUE_800 if is_selected else text_color,
                lambda e, i=idx: switch_view(i),
                bgcolor=(selected_color if is_selected else None),
            )

            if section == MENU_SECTION:
                continue

            if section == FOOTER_SECTION:
                footer_container.controls.append(tile)
                continue

            if section and section != current_section:
                nav_container.controls.append(section_header(section))
            current_section = section
            nav_container.controls.append(tile)

    # =========================================================
    # PROFILE BAR
    # =========================================================

    profile_bar = ft.Container(padding=ft.Padding(left=8, top=4, right=8, bottom=4))

    def open_menu_view(label):
        index = next((i for i, item in enumerate(shell_nav_items) if item[1] == label), None)
        if index is not None:
            switch_view(index)

    def menu_entry(icon, label, on_click, color=None, trailing=None):
        color = color or text_color
        row = [ft.Icon(icon, size=18, color=color), ft.Text(label, size=13, color=color)]
        if trailing is not None:
            row += [ft.Container(width=12), trailing]
        return ft.PopupMenuItem(
            content=ft.Row(row, spacing=10, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            on_click=on_click,
        )

    def build_profile_bar():
        name = account.get("name") or current_user or "Signed in"
        muted = ft.Colors.BLUE_GREY_300 if is_dark else ft.Colors.BLUE_GREY_500

        avatar = ft.CircleAvatar(
            content=ft.Text(initials(name), size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.BLUE_700,
            radius=16,
        )
        button = [avatar]
        if not compact:
            button += [
                ft.Text(name, size=13, weight=ft.FontWeight.W_600, color=heading_color, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=20, color=muted),
            ]

        who = [ft.Text(name, size=14, weight=ft.FontWeight.BOLD, color=heading_color)]
        details = " · ".join(part for part in (account.get("role"), account.get("office")) if part)
        if details:
            who.append(ft.Text(details, size=12, color=muted))

        items = [
            ft.PopupMenuItem(content=ft.Column(who, spacing=2, tight=True)),
            ft.PopupMenuItem(),
        ]
        if any(item[1] == "My Account" for item in shell_nav_items):
            items.append(menu_entry(ft.Icons.PERSON_OUTLINE, "My account", lambda e: open_menu_view("My Account")))
        if account.get("on_change_password"):
            items.append(menu_entry(ft.Icons.LOCK_RESET, "Change password", lambda e: account["on_change_password"]()))
        items += [
            menu_entry(
                ft.Icons.DARK_MODE_OUTLINED,
                "Night mode",
                toggle_night_mode,
                trailing=ft.Icon(ft.Icons.TOGGLE_ON if is_dark else ft.Icons.TOGGLE_OFF, size=26, color=(ft.Colors.BLUE_300 if is_dark else muted)),
            ),
            ft.PopupMenuItem(),
            menu_entry(ft.Icons.LOGOUT, "Log out", lambda e: logout_user(), color=(ft.Colors.RED_300 if is_dark else ft.Colors.RED_700)),
        ]

        leading = []
        if compact:
            leading = [ft.IconButton(ft.Icons.MENU, icon_color=heading_color, tooltip="Menu", on_click=lambda e: set_drawer(not drawer_open))]
        profile_bar.content = ft.Row(
            leading + [
                ft.PopupMenuButton(
                    content=ft.Container(
                        content=ft.Row(button, spacing=8, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.Padding(left=4, top=4, right=8, bottom=4),
                        border_radius=20,
                    ),
                    items=items,
                    menu_position=ft.PopupMenuPosition.UNDER,
                    tooltip="Account",
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN if compact else ft.MainAxisAlignment.END,
        )
        profile_bar.bgcolor = surface_color
        profile_bar.border = ft.Border(bottom=ft.BorderSide(1, ft.Colors.BLUE_GREY_800 if is_dark else ft.Colors.BLUE_GREY_100))

    # =========================================================
    # LAYOUT: sidebar beside the screen, or a drawer over it
    # =========================================================

    sidebar_panel = ft.Container(
        width=220,
        padding=ft.Padding(left=0, top=8, right=6, bottom=0),
        content=ft.Column(
            controls=[
                ft.Column(controls=[nav_container], expand=True, scroll=ft.ScrollMode.AUTO),
                ft.Divider(height=1, color=(ft.Colors.BLUE_GREY_800 if is_dark else ft.Colors.BLUE_GREY_100)),
                ft.Container(content=footer_container, padding=ft.Padding(left=0, top=4, right=0, bottom=8)),
            ],
            expand=True,
            spacing=0,
        ),
        border=None,
        border_radius=0,
        alignment=ft.Alignment.TOP_CENTER,
    )
    main_panel = ft.Container(
        expand=True,
        padding=ft.Padding(top=8, left=8, right=8, bottom=8),
        bgcolor=surface_color,
        border=None,
        border_radius=0,
        content=ft.Column([profile_bar, content_holder], expand=True, spacing=4),
    )
    scrim = ft.Container(
        left=0, top=0, right=0, bottom=0,
        bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
        visible=False,
        on_click=lambda e: set_drawer(False),
    )

    def style_sidebar():
        # The drawer floats over the screen, so it needs a solid background.
        sidebar_panel.bgcolor = sidebar_color or (surface_color if compact else None)
        sidebar_panel.shadow = ft.BoxShadow(blur_radius=16, color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK)) if compact else None

    def set_drawer(opened):
        nonlocal drawer_open
        drawer_open = bool(opened) and compact
        scrim.visible = drawer_open
        if compact:
            sidebar_panel.visible = drawer_open
        try:
            page.update()
        except Exception:
            pass

    def layout():
        style_sidebar()
        if compact:
            sidebar_panel.height = None
            sidebar_panel.left, sidebar_panel.top, sidebar_panel.bottom = 0, 0, 0
            sidebar_panel.visible = drawer_open
            scrim.visible = drawer_open
            main_panel.left, main_panel.top, main_panel.right, main_panel.bottom = 0, 0, 0, 0
            return ft.Stack([main_panel, scrim, sidebar_panel], expand=True)
        sidebar_panel.height = float("inf")
        sidebar_panel.left = sidebar_panel.top = sidebar_panel.bottom = None
        sidebar_panel.visible = True
        main_panel.left = main_panel.top = main_panel.right = main_panel.bottom = None
        return ft.Row([sidebar_panel, main_panel], expand=True, spacing=0, vertical_alignment=ft.CrossAxisAlignment.START)

    def show_layout():
        page.clean()
        page.add(layout())

    def page_resized(_=None):
        nonlocal compact, drawer_open
        now_compact = (getattr(page, "width", None) or 1200) < COMPACT_WIDTH
        if now_compact == compact:
            return
        compact = now_compact
        drawer_open = False
        build_profile_bar()
        show_layout()
        page.update()

    # Flet 0.28 names the resize event on_resized; other releases use on_resize.
    if hasattr(type(page), "on_resized"):
        page.on_resized = page_resized
    else:
        page.on_resize = page_resized

    # =========================================================
    # INITIAL NAVIGATION
    # =========================================================

    build_nav()
    build_profile_bar()

    page.horizontal_alignment = ft.CrossAxisAlignment.START
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.bgcolor = surface_color
    show_layout()

    # =========================================================
    # UPDATE PAGE
    # =========================================================

    page.update()

    # =========================================================
    # LOAD FIRST VIEW
    # =========================================================

    switch_view(initial_selected_index)

    return page