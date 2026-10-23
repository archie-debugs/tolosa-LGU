import flet as ft
import threading
import time
import traceback

from frontend.admin.tracking_ui import format_time

# Nav items in this section are pinned to the bottom of the sidebar.
FOOTER_SECTION = "Account"
# Nav items in this section are opened from the profile menu instead of the sidebar.
MENU_SECTION = "Menu"
# Below this width the profile button shows only the initials.
COMPACT_WIDTH = 600
SIDEBAR_WIDTH = 250
# The most characters of a nav label that fit beside its icon.
NAV_LABEL_FITS = 20
# Served from the shared assets folder; the sidebar shows plain colour when it is missing.
SIDEBAR_IMAGE = "sb_tolosa_homepage.jpg"
# The Sangguniang Bayan seal; an icon stands in when it is missing.
SEAL_IMAGE = "sb_tolosa_seal.png"
# How often the bell checks for new notifications while a screen stays open.
NOTIFICATION_POLL_SECONDS = 30

# One background poll per browser page: {id(page): the latest shell's check}.
_notification_polls = {}


def _poll_notifications(page, check):
    """Run `check` every NOTIFICATION_POLL_SECONDS until the page disconnects.

    Every shell drawn on the page replaces the check, so a page never runs more than one poll."""
    key = id(page)
    started = key in _notification_polls
    _notification_polls[key] = check
    if started:
        return

    def stop(_=None):
        _notification_polls.pop(key, None)

    if hasattr(page, "on_disconnect"):
        page.on_disconnect = stop

    def loop():
        while True:
            time.sleep(NOTIFICATION_POLL_SECONDS)
            current = _notification_polls.get(key)
            if current is None:
                return
            try:
                current()
            except Exception:
                traceback.print_exc()

    threading.Thread(target=loop, daemon=True).start()


def shell_colors(is_dark):
    """The sidebar and page colours for light or night mode."""
    if is_dark:
        return {
            "canvas": "#0f171d",
            "sidebar": ["#13263d", "#0b1622"],
            "selected": "#1f4b7d",
            "section": "#7fa6d6",
        }
    return {
        "canvas": "#F2F6FC",
        "sidebar": ["#1A56B5", "#0E3A86"],
        "selected": "#2F7BE6",
        "section": "#A9CBFF",
    }


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
    notifications=None,
    panel_title="Admin Panel",
):
    """Draw the sidebar, the profile bar and `content_view`.

    `panel_title` is the line under "SB Tolosa" in the sidebar header.

    `account` describes the signed-in user for the profile menu:
    {"name", "role", "office", "on_change_password"}; missing keys fall back to `current_user`.
    `notifications` adds a bell: {"load": () -> {"unread", "items"}, "seen": () -> None, "open": item -> None}.
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
    text_color = ft.Colors.WHITE if is_dark else ft.Colors.BLUE_GREY_700
    heading_color = ft.Colors.WHITE if is_dark else ft.Colors.BLUE_900
    colors = shell_colors(is_dark)
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
        padding=ft.Padding(left=16, top=4, right=16, bottom=16),
        bgcolor=colors["canvas"],
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
        refresh_notifications()
        build_profile_bar()
        set_drawer(False)
        notifications_panel.visible = False

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
        nonlocal is_dark, surface_color, text_color, heading_color, colors

        is_dark = not is_dark
        colors = shell_colors(is_dark)
        page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        surface_color = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        text_color = ft.Colors.WHITE if is_dark else ft.Colors.BLUE_GREY_700
        heading_color = ft.Colors.WHITE if is_dark else ft.Colors.BLUE_900
        try:
            page.client_storage.set("sb_night_mode", is_dark)
        except Exception:
            pass
        page.bgcolor = colors["canvas"]
        content_holder.bgcolor = colors["canvas"]
        main_panel.bgcolor = colors["canvas"]
        style_sidebar()
        switch_view(selected_index)

    # =========================================================
    # BUILD NAVIGATION
    # =========================================================

    def nav_tile(icon, label, on_click, selected=False):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, color=ft.Colors.WHITE, size=21),
                    ft.Container(width=10),
                    ft.Text(
                        label,
                        size=13,
                        color=ft.Colors.WHITE,
                        weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_400,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(left=14, top=10, right=12, bottom=10),
            width=SIDEBAR_WIDTH - 24,
            bgcolor=colors["selected"] if selected else None,
            border_radius=12,
            # Long names are cut short, so hovering shows the whole name.
            tooltip=label if len(label) > NAV_LABEL_FITS else None,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK), offset=ft.Offset(0, 2)) if selected else None,
            on_click=on_click,
            ink=not selected,
        )

    def section_header(title):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(title.upper(), size=11, weight=ft.FontWeight.BOLD, color=colors["section"]),
                    ft.Container(height=1, expand=True, bgcolor=ft.Colors.with_opacity(0.35, colors["section"])),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(left=14, top=16, right=12, bottom=6),
            width=SIDEBAR_WIDTH - 24,
        )

    def build_nav():
        nav_container.controls.clear()
        footer_container.controls.clear()

        # -----------------------------------------------------
        # SIDEBAR HEADER
        # -----------------------------------------------------

        nav_container.controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Image(
                                src=SEAL_IMAGE,
                                fit=ft.ImageFit.CONTAIN,
                                error_content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=ft.Colors.WHITE, size=30),
                            ),
                            width=58,
                            height=58,
                            alignment=ft.Alignment(0, 0),
                        ),
                        ft.Column(
                            [
                                ft.Text("SB Tolosa", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                ft.Text(panel_title, size=13, color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE)),
                            ],
                            spacing=0,
                            tight=True,
                        ),
                    ],
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(left=14, top=12, right=0, bottom=18),
            )
        )

        # -----------------------------------------------------
        # NAVIGATION ITEMS

        # A header is drawn whenever the section changes, so empty sections
        # never show one. Footer-section items go to the pinned footer.

        current_section = None

        for idx, (icon, label, _, section) in enumerate(shell_nav_items):

            is_selected = idx == selected_index
            tile = nav_tile(icon, label, lambda e, i=idx: switch_view(i), selected=is_selected)

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

    # =========================================================
    # NOTIFICATIONS
    # =========================================================

    notification_state = {"unread": 0, "items": [], "error": None}
    notifications_panel = ft.Container(data="notifications-panel", visible=False, padding=ft.Padding(left=12, top=8, right=12, bottom=8), border_radius=10)
    NOTIFICATION_STYLES = {
        "incoming": (ft.Icons.MOVE_TO_INBOX_OUTLINED, ft.Colors.BLUE_700),
        "incoming_overdue": (ft.Icons.WARNING_AMBER_ROUNDED, ft.Colors.RED_700),
        "received": (ft.Icons.TASK_ALT, ft.Colors.GREEN_700),
        "outgoing_overdue": (ft.Icons.WARNING_AMBER_ROUNDED, ft.Colors.RED_700),
        "handoff_overdue": (ft.Icons.WARNING_AMBER_ROUNDED, ft.Colors.RED_700),
        "returned": (ft.Icons.UNDO, ft.Colors.DEEP_ORANGE_700),
        "cancelled": (ft.Icons.CANCEL_OUTLINED, ft.Colors.BLUE_GREY_600),
        "registered": (ft.Icons.NOTE_ADD_OUTLINED, ft.Colors.BLUE_GREY_600),
        "due": (ft.Icons.EVENT_OUTLINED, ft.Colors.AMBER_800),
        "overdue": (ft.Icons.EVENT_BUSY_OUTLINED, ft.Colors.RED_700),
    }

    def refresh_notifications():
        if not notifications:
            return
        try:
            body = notifications["load"]() or {}
            notification_state.update(unread=int(body.get("unread") or 0), items=list(body.get("items") or []), error=None)
        except Exception as exc:
            notification_state.update(unread=0, error=str(exc) or "Something went wrong.")

    def hide_notifications():
        notifications_panel.visible = False
        page.update()

    def open_notification(item):
        hide_notifications()
        notifications["open"](item)

    def notification_row(item):
        muted = ft.Colors.BLUE_GREY_300 if is_dark else ft.Colors.BLUE_GREY_500
        icon, color = NOTIFICATION_STYLES.get(item.get("kind"), (ft.Icons.NOTIFICATIONS_OUTLINED, ft.Colors.BLUE_GREY_600))
        heading = [
            ft.Text(item.get("tracking_number") or "-", size=12, weight=ft.FontWeight.BOLD, color=(ft.Colors.BLUE_200 if is_dark else ft.Colors.BLUE_900)),
            ft.Text(item.get("title") or "", size=12, color=heading_color, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
        ]
        if item.get("unread"):
            heading.append(ft.Container(width=8, height=8, border_radius=4, bgcolor=ft.Colors.BLUE_600))
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(ft.Icon(icon, size=18, color=color), padding=6, border_radius=8, bgcolor=ft.Colors.with_opacity(0.12, color)),
                    ft.Column(
                        [
                            ft.Row(heading, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.Text(item.get("message") or "", size=12, color=text_color),
                            ft.Text(format_time(item.get("at")), size=11, color=muted),
                        ],
                        spacing=1,
                        tight=True,
                        expand=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding(left=6, top=6, right=6, bottom=6),
            border_radius=8,
            ink=True,
            on_click=lambda e, chosen=item: open_notification(chosen),
        )

    def show_notifications():
        refresh_notifications()
        muted = ft.Colors.BLUE_GREY_300 if is_dark else ft.Colors.BLUE_GREY_500
        items = notification_state["items"]
        if notification_state["error"]:
            rows = [ft.Text(f"Notifications could not be loaded: {notification_state['error']}", size=12, color=ft.Colors.RED_400 if is_dark else ft.Colors.RED_700)]
        elif not items:
            rows = [ft.Text("Nothing needs your attention right now.", size=12, color=muted)]
        else:
            rows = [notification_row(item) for item in items]
        notifications_panel.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Notifications", size=12, weight=ft.FontWeight.W_600, color=muted, expand=True),
                        ft.IconButton(ft.Icons.CLOSE, icon_size=18, tooltip="Close", on_click=lambda e: hide_notifications()),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                *rows,
            ],
            spacing=2,
            tight=True,
        )
        notifications_panel.bgcolor = ft.Colors.BLUE_GREY_900 if is_dark else ft.Colors.BLUE_GREY_50
        notifications_panel.visible = True
        if notification_state["unread"] and not notification_state["error"]:
            try:
                notifications["seen"]()
                notification_state["unread"] = 0
            except Exception:
                pass
        build_profile_bar()
        page.update()

    def bell_button():
        unread = notification_state["unread"]
        button = ft.IconButton(
            ft.Icons.NOTIFICATIONS_ACTIVE if unread else ft.Icons.NOTIFICATIONS_OUTLINED,
            icon_color=heading_color,
            tooltip="Notifications",
            on_click=lambda e: show_notifications(),
        )
        if not unread:
            return button
        return ft.Stack(
            [
                button,
                ft.Container(
                    data="notification-badge",
                    content=ft.Text("9+" if unread > 9 else str(unread), size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.RED_600,
                    border_radius=9,
                    padding=ft.Padding(5, 1, 5, 1),
                    right=2,
                    top=2,
                ),
            ],
            width=44,
            height=40,
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
        profile_menu = ft.PopupMenuButton(
            content=ft.Container(
                content=ft.Row(button, spacing=8, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(left=4, top=4, right=8, bottom=4),
                border_radius=20,
            ),
            items=items,
            menu_position=ft.PopupMenuPosition.UNDER,
            tooltip="Account",
        )
        # The bell stays beside the profile button, at the right end of the bar.
        right = ft.Row([bell_button(), profile_menu], spacing=4, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER) if notifications else profile_menu
        profile_bar.content = ft.Row(
            leading + [right],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN if compact else ft.MainAxisAlignment.END,
            spacing=8,
        )
        profile_bar.bgcolor = colors["canvas"]

    # =========================================================
    # LAYOUT: sidebar beside the screen, or a drawer over it
    # =========================================================

    sidebar_divider = ft.Container(height=1, bgcolor=ft.Colors.with_opacity(0.2, ft.Colors.WHITE), margin=ft.Padding(left=12, top=0, right=12, bottom=0))
    sidebar_panel = ft.Container(
        width=SIDEBAR_WIDTH,
        content=ft.Stack(
            [
                # The town hall, faded into the bottom of the sidebar.
                ft.Container(
                    content=ft.Image(src=SIDEBAR_IMAGE, fit=ft.ImageFit.COVER, opacity=0.12, error_content=ft.Container()),
                    left=0, right=0, bottom=0, height=260,
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Column(controls=[nav_container], expand=True, scroll=ft.ScrollMode.AUTO),
                            sidebar_divider,
                            ft.Container(content=footer_container, padding=ft.Padding(left=0, top=8, right=0, bottom=12)),
                        ],
                        expand=True,
                        spacing=0,
                    ),
                    padding=ft.Padding(left=12, top=8, right=12, bottom=0),
                    left=0, right=0, top=0, bottom=0,
                ),
            ],
            expand=True,
        ),
        border=None,
        border_radius=0,
        alignment=ft.Alignment.TOP_CENTER,
    )
    main_panel = ft.Container(
        expand=True,
        padding=ft.Padding(top=12, left=16, right=16, bottom=0),
        bgcolor=colors["canvas"],
        border=None,
        border_radius=0,
        content=ft.Column([profile_bar, notifications_panel, content_holder], expand=True, spacing=4),
    )
    scrim = ft.Container(
        left=0, top=0, right=0, bottom=0,
        bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
        visible=False,
        on_click=lambda e: set_drawer(False),
    )

    def style_sidebar():
        sidebar_panel.gradient = ft.LinearGradient(begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1), colors=colors["sidebar"])
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
    page.bgcolor = colors["canvas"]
    show_layout()

    # =========================================================
    # UPDATE PAGE
    # =========================================================

    page.update()

    # =========================================================
    # LOAD FIRST VIEW
    # =========================================================

    switch_view(initial_selected_index)

    # New handoffs and receipts reach the bell without the user changing screens.
    def check_notifications():
        before = (notification_state["unread"], notification_state["error"])
        refresh_notifications()
        if (notification_state["unread"], notification_state["error"]) != before:
            build_profile_bar()
            page.update()

    if notifications:
        _poll_notifications(page, check_notifications)

    return page