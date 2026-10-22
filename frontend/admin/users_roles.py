import flet as ft

from frontend.admin.tracking_ui import local_time


EMPLOYEE_PERMISSION_GROUPS = {
    "Dashboard": [
        "View Dashboard",
    ],
    "Documents": [
        "Register Documents",
        "Edit Documents",
        "Delete Documents",
        "Archive Documents",
        "Restore Documents",
        "View Documents",
        "Search Documents",
        "Filter Documents",
        "View Document Details",
        "Import Documents",
        "Export Documents",
        "Download Documents",
        "Print Documents",
        "Update Document Status",
    ],
    "QR Code": [
        "Generate QR Codes",
        "Print QR Codes",
        "View QR Tracking",
    ],
    "Today's Documents": [
        "Set Documents For SB Members",
    ],
    "Users & Roles": [
        "Create Users",
        "Edit Users",
        "Reset Passwords",
        "Activate Users",
        "Deactivate Users",
        "Delete Users",
        "Assign Roles",
        "Manage Permissions",
    ],
    "Members & Committees": [
        "Manage Members And Committees",
    ],
    "Audit Logs": [
        "View Audit Logs",
        "Export Audit Logs",
    ],
    "Analytics": [
        "View Analytics",
        "Export Analytics",
    ],
}

OFFICE_EMPLOYEE_PERMISSION_GROUP = {
    "Office Workflow": [
        "View Office Documents",
        "Search Office Documents",
        "View Office Document Details",
        "Scan QR",
        "Confirm Document Receipt",
        "View Office History",
    ],
}

SB_MEMBER_PERMISSIONS = [
    "View Documents",
    "Search Documents",
    "Filter Documents",
    "View Document Details",
    "Download Documents",
    "Print Documents",
]


def _status_badge(status):
    text = (status or "Active").strip()
    active = text.lower() == "active"
    return ft.Container(
        content=ft.Text(text, size=11, weight=ft.FontWeight.W_600),
        padding=ft.Padding(left=10, top=5, right=10, bottom=5),
        bgcolor=ft.Colors.GREEN_50 if active else ft.Colors.RED_50,
        border_radius=12,
        border=ft.border.all(1, ft.Colors.GREEN_100 if active else ft.Colors.RED_100),
    )


def _role_badge(role):
    role_text = role or "Employee"
    color = ft.Colors.BLUE_50
    border = ft.Colors.BLUE_100
    text_color = ft.Colors.BLUE_800
    if role_text == "Super Administrator":
        color = ft.Colors.AMBER_50
        border = ft.Colors.AMBER_200
        text_color = ft.Colors.AMBER_900
    elif role_text == "SB Member":
        color = ft.Colors.PURPLE_50
        border = ft.Colors.PURPLE_100
        text_color = ft.Colors.PURPLE_800
    return ft.Container(
        content=ft.Text(role_text, size=11, weight=ft.FontWeight.W_600, color=text_color),
        padding=ft.Padding(left=10, top=5, right=10, bottom=5),
        bgcolor=color,
        border_radius=12,
        border=ft.border.all(1, border),
    )


def _permission_summary(user):
    role = user.get("role", "Employee")
    if role == "Super Administrator":
        return "Full Access"
    if role == "SB Member":
        return "Read Only"
    perms = user.get("permissions") or []
    return f"{len(perms)} permissions" if perms else "No permissions"


def _format_timestamp(value):
    if not value:
        return "—"
    local = local_time(value)
    return local.strftime("%Y-%m-%d %H:%M:%S") if local else str(value)


def _build_permission_checkboxes(selected_permissions=None):
    checked = set(selected_permissions or [])
    items = []
    for section_name, perms in EMPLOYEE_PERMISSION_GROUPS.items():
        group = []
        for perm in perms:
            checkbox = ft.Checkbox(label=perm, value=(perm in checked), scale=0.9)
            group.append(checkbox)
        items.append(
            ft.Column(
                [
                    ft.Text(section_name, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700),
                    ft.Wrap(group, spacing=8, run_spacing=6),
                ],
                spacing=6,
            )
        )
    return items


def _locked_badge():
    return ft.Container(
        content=ft.Row(
            [ft.Icon(ft.Icons.LOCK, size=12, color=ft.Colors.RED_800), ft.Text("Locked", size=11, weight=ft.FontWeight.W_600, color=ft.Colors.RED_800)],
            spacing=4,
            tight=True,
        ),
        padding=ft.Padding(left=10, top=5, right=10, bottom=5),
        bgcolor=ft.Colors.RED_50,
        border_radius=12,
        border=ft.border.all(1, ft.Colors.RED_200),
        tooltip="Too many failed logins. Unlocks automatically, or a Super Administrator can unlock it now.",
    )


def _account_status_cell(user, status):
    if not user.get("locked"):
        return _status_badge(status)
    return ft.Row([_status_badge(status), _locked_badge()], spacing=6, tight=True)


def _user_actions_menu(user, open_view_user_dialog, open_edit_user_dialog, open_reset_password_dialog, delete_user, unlock_user=None):
    items = [
        ft.PopupMenuItem(content=ft.Text("View"), on_click=lambda _, item=user: open_view_user_dialog(item)),
        ft.PopupMenuItem(content=ft.Text("Edit"), on_click=lambda _, item=user: open_edit_user_dialog(item)),
        ft.PopupMenuItem(content=ft.Text("Reset Password"), on_click=lambda _, item=user: open_reset_password_dialog(item)),
    ]
    # Unlocking is a Super Administrator action, so callers pass unlock_user only for them.
    if unlock_user is not None and user.get("locked"):
        items.append(ft.PopupMenuItem(content=ft.Text("Unlock Login"), on_click=lambda _, item=user: unlock_user(item)))
    items.append(ft.PopupMenuItem(content=ft.Text("Delete"), on_click=lambda _, item=user: delete_user(item)))
    return ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, tooltip="User actions", items=items)


def build_users_roles_table(
    users_data,
    open_view_user_dialog,
    open_edit_user_dialog,
    open_reset_password_dialog,
    delete_user,
    unlock_user=None,
):
    user_rows = []
    for user in users_data:
        full_name = user.get("full_name", "Unknown User")
        username = user.get("username", "unknown")
        role = user.get("role", "Employee")
        status = user.get("status", "Active")
        permissions = user.get("permissions") or []
        last_login = _format_timestamp(user.get("last_login"))
        created = _format_timestamp(user.get("created"))
        action_buttons = _user_actions_menu(
            user, open_view_user_dialog, open_edit_user_dialog, open_reset_password_dialog, delete_user, unlock_user
        )

        user_rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(action_buttons),
                    ft.DataCell(
                        ft.Column(
                            [
                                ft.Text(full_name, size=13, weight=ft.FontWeight.W_600),
                                ft.Text(username, size=11, color=ft.Colors.BLUE_GREY_600),
                            ],
                            spacing=2,
                            tight=True,
                        )
                    ),
                    ft.DataCell(ft.Text(username, size=12)),
                    ft.DataCell(_role_badge(role)),
                    ft.DataCell(ft.Text(user.get("department") or "-", size=12)),
                    ft.DataCell(_account_status_cell(user, status)),
                    ft.DataCell(ft.Text(_permission_summary(user), size=12, color=ft.Colors.BLUE_GREY_700)),
                    ft.DataCell(ft.Text(last_login, size=12)),
                    ft.DataCell(ft.Text(created, size=12)),
                ]
            )
        )

    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("User", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Username", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Role", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Office", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Account Status", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Permissions", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Last Login", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Created", weight=ft.FontWeight.BOLD, size=12)),
        ],
        rows=user_rows,
        width=1600,
        expand=False,
        column_spacing=16,
        heading_row_color=ft.Colors.BLUE_GREY_50,
    )

    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=table,
                    width=1600,
                    padding=ft.Padding(left=6, top=8, right=6, bottom=8),
                    bgcolor=ft.Colors.WHITE,
                    border_radius=12,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                )
            ],
            width="100%",
            scroll=ft.ScrollMode.AUTO,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        width="100%",
        bgcolor=ft.Colors.WHITE,
        border_radius=12,
        border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
    )


def build_offices_table(offices_data, open_edit_office_dialog, view_office_users):
    rows = []
    for office in offices_data:
        actions = ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT,
            tooltip="Office actions",
            items=[
                ft.PopupMenuItem(content=ft.Text("Edit"), on_click=lambda _, item=office: open_edit_office_dialog(item)),
                ft.PopupMenuItem(content=ft.Text("View Users"), on_click=lambda _, item=office: view_office_users(item)),
            ],
        )
        rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(office.get("name") or "-", size=13)),
                    ft.DataCell(ft.Text(office.get("office_code") or "-", size=13)),
                    ft.DataCell(_status_badge("Active" if office.get("is_active") else "Inactive")),
                    ft.DataCell(ft.Text(str(office.get("user_count", 0)), size=13)),
                    ft.DataCell(actions),
                ]
            )
        )
    return ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Office Name", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Office Code", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Users", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD, size=12)),
        ],
        rows=rows,
        column_spacing=20,
        heading_row_color=ft.Colors.BLUE_GREY_50,
    )


def build_users_roles_view(
    users_data,
    search_field,
    role_filter,
    status_filter,
    office_filter,
    permission_filter,
    create_button,
    refresh_button,
    open_create_user_dialog,
    open_view_user_dialog,
    open_edit_user_dialog,
    open_reset_password_dialog,
    delete_user,
    page,
    surface_card,
    section_header,
    user_table_holder=None,
    no_users_notice=None,
    offices_data=None,
    create_office=None,
    edit_office=None,
    view_office_users=None,
    office_table_holder=None,
    create_employee=None,
    unlock_user=None,
):
    user_rows = []
    for user in users_data:
        full_name = user.get("full_name", "Unknown User")
        username = user.get("username", "unknown")
        role = user.get("role", "Employee")
        status = user.get("status", "Active")
        permissions = user.get("permissions") or []
        last_login = _format_timestamp(user.get("last_login"))
        created = _format_timestamp(user.get("created"))
        action_buttons = _user_actions_menu(
            user, open_view_user_dialog, open_edit_user_dialog, open_reset_password_dialog, delete_user, unlock_user
        )

        user_rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(action_buttons),
                    ft.DataCell(
                        ft.Column(
                            [
                                ft.Text(full_name, size=13, weight=ft.FontWeight.W_600),
                                ft.Text(username, size=11, color=ft.Colors.BLUE_GREY_600),
                            ],
                            spacing=2,
                            tight=True,
                        )
                    ),
                    ft.DataCell(ft.Text(username, size=12)),
                    ft.DataCell(_role_badge(role)),
                    ft.DataCell(ft.Text(user.get("department") or "-", size=12)),
                    ft.DataCell(_account_status_cell(user, status)),
                    ft.DataCell(ft.Text(_permission_summary(user), size=12, color=ft.Colors.BLUE_GREY_700)),
                    ft.DataCell(ft.Text(last_login, size=12)),
                    ft.DataCell(ft.Text(created, size=12)),
                ]
            )
        )

    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("User", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Username", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Role", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Office", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Account Status", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Permissions", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Last Login", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Created", weight=ft.FontWeight.BOLD, size=12)),
        ],
        rows=user_rows,
        width=1600,
        expand=False,
        column_spacing=16,
        heading_row_color=ft.Colors.BLUE_GREY_50,
    )

    if user_table_holder is None:
        table_container = ft.Container(
            content=ft.Container(
                content=table,
                width=1600,
                padding=ft.Padding(left=6, top=8, right=6, bottom=8),
                bgcolor=ft.Colors.WHITE,
            ),
            width="100%",
            bgcolor=ft.Colors.WHITE,
            border_radius=12,
            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
        )
    else:
        table_container = user_table_holder

    if no_users_notice is None:
        no_users = ft.Container(
            content=ft.Column(
                [
                    ft.Text("No users found.", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700),
                    ft.Text("Try another search or change the filters.", size=12, color=ft.Colors.BLUE_GREY_500),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=24,
            visible=len(user_rows) == 0,
            alignment=ft.Alignment.CENTER,
            width="100%",
            height=120,
            bgcolor=ft.Colors.BLUE_GREY_50,
            border_radius=12,
        )
    else:
        no_users = no_users_notice

    toolbar = ft.Column(
        [
            ft.Row(
                [
                    search_field,
                    create_button,
                ],
                spacing=20,
                wrap=True,
                run_spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                [
                    role_filter,
                    status_filter,
                    office_filter,
                    permission_filter,
                ],
                spacing=20,
                wrap=True,
                run_spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=10,
    )

    header = surface_card(
        ft.Column(
            [
                section_header(
                    "Users & Roles",
                    "Manage system accounts, roles, permissions, and account status.",
                    ft.Icons.PEOPLE_ALT_OUTLINED,
                    ft.Colors.BLUE_700,
                ),
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                toolbar,
            ],
            spacing=16,
        ),
        padding=18,
        expand=False,
    )

    table_section = ft.Column(
        [
            ft.Row(
                [
                    ft.Text("User Accounts", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                    ft.Container(
                        content=ft.Text(f"{len(user_rows)} users", size=12, color=ft.Colors.BLUE_GREY_600),
                        alignment=ft.Alignment.CENTER_RIGHT,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                width="100%",
            ),
            table_container,
            no_users,
        ],
        spacing=10,
    )

    sections = [
        header,
        surface_card(table_section, padding=18, expand=False),
    ]
    if offices_data is not None:
        office_table = office_table_holder or build_offices_table(
            offices_data,
            edit_office or (lambda _office: None),
            view_office_users or (lambda _office: None),
        )
        sections.append(
            surface_card(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("Office Management", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                                ft.Row(
                                    [
                                        *([ft.Button(
                                            "+ Create Employee Account",
                                            on_click=create_employee,
                                            bgcolor=ft.Colors.BLUE_800,
                                            color=ft.Colors.WHITE,
                                        )] if create_employee else []),
                                        ft.Button(
                                            "+ Add Office",
                                            on_click=create_office,
                                            bgcolor=ft.Colors.BLUE_800,
                                            color=ft.Colors.WHITE,
                                        ),
                                    ],
                                    spacing=8,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row([office_table], scroll=ft.ScrollMode.AUTO),
                    ],
                    spacing=10,
                ),
                padding=18,
                expand=False,
            )
        )
    return ft.Column(
        sections,
        spacing=12,
    )
