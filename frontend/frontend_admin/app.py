import flet as ft
import requests
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from frontend.frontend_admin.committees import build_committees_view
from frontend.frontend_admin.documents import build_documents_view
from frontend.frontend_admin.users_roles import build_users_roles_view
from frontend.frontend_admin.audit_logs import build_audit_logs_view
from frontend.frontend_admin.admin_shell import render_shell
from frontend.frontend_admin.admindashboard import build_admin_dashboard_view

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")


def main(page: ft.Page):
    page.title = "LGU Tolosa - Sangguniang Bayan Admin System"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.colors.BLUE_GREY_100
    page.scroll = ft.ScrollMode.AUTO
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.padding = 8

    current_user = None
    current_user_role = None

    users_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Username", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Role", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )

    user_username_input = ft.TextField(label="Username", width=280)
    user_password_input = ft.TextField(label="Password", width=280, password=True, can_reveal_password=True)
    user_role_input = ft.Dropdown(
        label="Role",
        width=220,
        options=[
            ft.dropdown.Option("Admin"),
            ft.dropdown.Option("SB Member"),
            ft.dropdown.Option("Mayor's Office"),
        ],
        value="Admin",
    )

    users_notice = ft.Text("", size=12, color=ft.colors.BLUE_GREY_600)
    pending_delete_user = None

    committee_editor_column = ft.Column(spacing=10)
    committee_notice = ft.Text("", size=12, color=ft.colors.BLUE_GREY_600)
    pending_delete_committee = None
    committee_edit_index = None
    committee_name_input = ft.TextField(label="Committee Name", width=420)

    COMMITTEES = [
        {"name": "Committee on Finance"},
        {"name": "Committee on Health"},
        {"name": "Committee on Education"},
    ]

    committee_edit_dialog = ft.AlertDialog(
        title=ft.Text("Edit Committee"),
        content=committee_name_input,
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_committee_dialog()),
            ft.ElevatedButton("Save", on_click=lambda _: on_committee_save()),
        ],
    )
    delete_committee_dialog = ft.AlertDialog(
        title=ft.Text("Confirm Action"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_delete_committee_dialog()),
            ft.ElevatedButton("Delete", on_click=lambda _: delete_committee_action(), bgcolor=ft.colors.RED_700, color=ft.colors.WHITE),
        ],
    )
    page.overlay.append(delete_committee_dialog)
    page.overlay.append(committee_edit_dialog)

    audit_logs_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Time", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Actor", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Action", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Target", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Details", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )

    AUDIT_LOGS_SAMPLE = [
        {"created_at": "11:02 AM", "actor": "Admin", "action": "Reviewed document", "target_type": "Document", "details": "DOC-2026-0015 moved to review."},
        {"created_at": "10:45 AM", "actor": "Secretary", "action": "Routed resolution", "target_type": "Document", "details": "DOC-2026-0016 forwarded to committee."},
        {"created_at": "10:20 AM", "actor": "Staff", "action": "Archived document", "target_type": "Document", "details": "DOC-2026-0017 archived."},
    ]

    def save_committees_to_file(committees):
        # UI preview only: no persistent save is required for the current design.
        pass

    delete_dialog = ft.AlertDialog(title=ft.Text("Confirm Action"), content=ft.Text(""), actions=[])
    page.overlay.append(delete_dialog)

    dashboard_action_dialog = ft.AlertDialog(
        title=ft.Text("Frontend preview"),
        content=ft.Text("This action is only a visual preview. No backend or database changes are performed."),
        actions=[ft.TextButton("Close", on_click=lambda _: close_dashboard_action_dialog())],
    )
    page.overlay.append(dashboard_action_dialog)

    def refresh_user_display_ids(users):
        for idx, user in enumerate(users, start=1):
            user["display_id"] = idx

    def surface_card(content, width=None, padding=24, expand=False):
        return ft.Container(
            content=content,
            width=width,
            expand=expand,
            padding=padding,
            bgcolor=ft.colors.WHITE,
            border_radius=24,
        )

    def section_header(title, subtitle, icon, accent_color):
        return ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, color=accent_color, size=24),
                    padding=10,
                    bgcolor=ft.colors.BLUE_GREY_50,
                    border_radius=14,
                ),
                ft.Column(
                    [
                        ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
                        ft.Text(subtitle, size=13, color=ft.colors.BLUE_GREY_600),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def close_dashboard_action_dialog():
        dashboard_action_dialog.open = False
        page.update()

    def open_preview_notice(_=None):
        dashboard_action_dialog.open = True
        page.update()

    def load_users_table():
        try:
            response = requests.get(f"{BACKEND_URL}/auth/users", verify=False)
            if response.status_code == 200:
                users = response.json().get("items", [])
                refresh_user_display_ids(users)
                rows = []
                for user in users:
                    rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(str(user.get("display_id", user.get("id", "-"))))),
                                ft.DataCell(ft.Text(user.get("username", "-"))),
                                ft.DataCell(ft.Text(user.get("role", "Admin"))),
                                ft.DataCell(
                                    ft.PopupMenuButton(
                                        icon=ft.icons.MORE_VERT,
                                        tooltip="User actions",
                                        items=[
                                            ft.PopupMenuItem(text="Set Admin", on_click=lambda _, u=user: update_user_role(u, "Admin")),
                                            ft.PopupMenuItem(text="Set SB Member", on_click=lambda _, u=user: update_user_role(u, "SB Member")),
                                            ft.PopupMenuItem(text="Set Mayor's Office", on_click=lambda _, u=user: update_user_role(u, "Mayor's Office")),
                                            ft.PopupMenuItem(text="Delete User", on_click=lambda _, u=user: confirm_delete_user(u)),
                                        ],
                                    )
                                ),
                            ],
                        )
                    )
                users_table.rows = rows
            else:
                users_table.rows = []
                users_notice.value = f"Load failed: {response.text}"
        except Exception as exc:
            users_table.rows = []
            users_notice.value = f"Load error: {exc}"
        page.update()

    def create_user_record(_=None):
        if not user_username_input.value or not user_password_input.value:
            users_notice.value = "Username and password are required."
            page.update()
            return

        try:
            response = requests.post(
                f"{BACKEND_URL}/auth/register",
                params={
                    "username": user_username_input.value.strip(),
                    "password": user_password_input.value,
                    "role": user_role_input.value or "Admin",
                },
                verify=False,
            )
            if response.status_code == 200:
                user_username_input.value = ""
                user_password_input.value = ""
                users_notice.value = "User created successfully."
                load_users_table()
            else:
                users_notice.value = f"Create failed: {response.text}"
        except Exception as exc:
            users_notice.value = f"Create error: {exc}"
        page.update()

    def update_user_role(user, role):
        try:
            response = requests.put(
                f"{BACKEND_URL}/auth/users/{requests.utils.quote(user['username'])}/role",
                params={"role": role},
                verify=False,
            )
            if response.status_code == 200:
                load_users_table()
                users_notice.value = response.json().get("message", "Role updated.")
            else:
                users_notice.value = f"Role update failed: {response.text}"
        except Exception as exc:
            users_notice.value = f"Role update error: {exc}"
        page.update()

    def delete_user_record(user):
        try:
            response = requests.delete(
                f"{BACKEND_URL}/auth/users/{requests.utils.quote(user['username'])}",
                verify=False,
            )
            if response.status_code == 200:
                users_notice.value = response.json().get("message", "User deleted.")
                load_users_table()
            else:
                users_notice.value = f"Delete failed: {response.text}"
        except Exception as exc:
            users_notice.value = f"Delete error: {exc}"
        page.update()

    def confirm_delete_user(user):
        nonlocal pending_delete_user
        pending_delete_user = user
        delete_dialog.title = ft.Text("Delete User")
        delete_dialog.content = ft.Text(f"Delete user \"{user.get('username', 'this user')}\"? This cannot be undone.")
        delete_dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda _: close_delete_dialog()),
            ft.ElevatedButton(
                "Delete",
                icon=ft.icons.DELETE_OUTLINE,
                bgcolor=ft.colors.RED_700,
                color=ft.colors.WHITE,
                on_click=lambda _: run_delete_user_action(),
            ),
        ]
        delete_dialog.open = True
        page.update()

    def close_delete_dialog():
        nonlocal pending_delete_user
        delete_dialog.open = False
        pending_delete_user = None
        page.update()

    def run_delete_user_action():
        nonlocal pending_delete_user
        user = pending_delete_user
        close_delete_dialog()
        if user:
            delete_user_record(user)

    def open_committee_dialog(index: int | None):
        nonlocal committee_edit_index
        committee_edit_index = index
        if index is None:
            committee_name_input.value = ""
            committee_edit_dialog.title.value = "Add Committee"
        else:
            committee_name_input.value = COMMITTEES[index]["name"]
            committee_edit_dialog.title.value = "Edit Committee"
        committee_edit_dialog.open = True
        page.update()

    def close_committee_dialog():
        committee_edit_dialog.open = False
        page.update()

    def on_committee_save():
        nonlocal committee_edit_index
        name = (committee_name_input.value or "").strip()
        if not name:
            return
        if committee_edit_index is None:
            COMMITTEES.append({"name": name})
        else:
            COMMITTEES[committee_edit_index]["name"] = name
        save_committees_to_file(COMMITTEES)
        committee_edit_dialog.open = False
        page.update()

    def confirm_delete_committee(index: int):
        nonlocal pending_delete_committee
        pending_delete_committee = index
        delete_committee_dialog.open = True
        page.update()

    def delete_committee_action():
        nonlocal pending_delete_committee
        try:
            if pending_delete_committee is not None and 0 <= pending_delete_committee < len(COMMITTEES):
                COMMITTEES.pop(pending_delete_committee)
                save_committees_to_file(COMMITTEES)
        finally:
            pending_delete_committee = None
            delete_committee_dialog.open = False
            page.update()

    def close_delete_committee_dialog():
        nonlocal pending_delete_committee
        pending_delete_committee = None
        delete_committee_dialog.open = False
        page.update()

    def workflow_summary_section():
        return ft.Text("The admin dashboard includes user, committee, and audit tools.", size=13, color=ft.colors.BLUE_GREY_600)

    def load_audit_logs_view():
        try:
            response = requests.get(f"{BACKEND_URL}/audit/logs", verify=False)
            if response.status_code == 200:
                payload = response.json()
                items = payload.get("items", [])
                audit_logs_table.rows = [
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(item.get("created_at", "-"))),
                            ft.DataCell(ft.Text(item.get("actor", "-"))),
                            ft.DataCell(ft.Text(item.get("action", "-"))),
                            ft.DataCell(ft.Text(item.get("target_type", "-"))),
                            ft.DataCell(ft.Text(item.get("details", "-"))),
                        ]
                    )
                    for item in items
                ]
            else:
                raise ValueError("Backend returned non-200 response")
        except Exception:
            audit_logs_table.rows = [
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(item["created_at"])),
                        ft.DataCell(ft.Text(item["actor"])),
                        ft.DataCell(ft.Text(item["action"])),
                        ft.DataCell(ft.Text(item["target_type"])),
                        ft.DataCell(ft.Text(item["details"])),
                    ]
                )
                for item in AUDIT_LOGS_SAMPLE
            ]
        page.update()

    def audit_logs_view():
        return build_audit_logs_view(audit_logs_table, load_audit_logs_view, surface_card, section_header)

    def build_dashboard_view():
        return build_admin_dashboard_view(surface_card, section_header, open_preview_notice)

    def committees_view():
        committee_rows = []
        for index, committee in enumerate(COMMITTEES):
            committee_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(index + 1))),
                        ft.DataCell(ft.Text(committee["name"])),
                        ft.DataCell(
                            ft.Row(
                                [
                                    ft.IconButton(ft.icons.EDIT, tooltip="Edit", on_click=lambda _, idx=index: open_committee_dialog(idx)),
                                    ft.IconButton(ft.icons.DELETE, tooltip="Delete", on_click=lambda _, idx=index: confirm_delete_committee(idx)),
                                ],
                                spacing=4,
                            )
                        ),
                    ]
                )
            )

        committee_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("#", weight=ft.FontWeight.BOLD, size=12)),
                ft.DataColumn(ft.Text("Committee", weight=ft.FontWeight.BOLD, size=12)),
                ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD, size=12)),
            ],
            rows=committee_rows,
            column_spacing=12,
        )
        return build_committees_view(committee_table, open_committee_dialog, surface_card, section_header)

    def users_roles_view():
        load_users_table()
        return build_users_roles_view(
            user_username_input,
            user_password_input,
            user_role_input,
            users_notice,
            users_table,
            create_user_record,
            surface_card,
            section_header,
        )

    DOCUMENTS_SAMPLE = [
        {
            "id": "DOC-2026-0015",
            "title": "Proposed Ordinance on Local Revenue",
            "type": "Ordinance",
            "status": "Under Review",
            "assigned_committee": "Committee on Finance",
        },
        {
            "id": "DOC-2026-0016",
            "title": "Resolution No. 2026-008",
            "type": "Resolution",
            "status": "Routed",
            "assigned_committee": "Committee on Health",
        },
        {
            "id": "DOC-2026-0017",
            "title": "Committee Report No. 04",
            "type": "Committee Report",
            "status": "Completed",
            "assigned_committee": "SB Office",
        },
    ]

    documents_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Title", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Type", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Assigned Committee", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )

    documents_notice = ft.Text("", size=12, color=ft.colors.BLUE_GREY_600)

    def load_documents_table():
        rows = []
        for doc in DOCUMENTS_SAMPLE:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(doc["id"])),
                        ft.DataCell(ft.Text(doc["title"])),
                        ft.DataCell(ft.Text(doc["type"])),
                        ft.DataCell(ft.Text(doc["status"])),
                        ft.DataCell(ft.Text(doc["assigned_committee"])),
                    ],
                )
            )
        documents_table.rows = rows
        documents_notice.value = "Document design preview only. Backend integration is disabled."
        page.update()

    def open_documents_view(_=None):
        load_documents_table()
        page.update()

    def documents_view():
        return build_documents_view(
            documents_table,
            documents_notice,
            open_documents_view,
            surface_card,
            section_header,
        )

    def settings_view():
        return ft.Column(
            [
                surface_card(
                    ft.Column(
                        [
                            section_header(
                                "Settings",
                                "System configuration and operational preferences.",
                                ft.icons.SETTINGS,
                                ft.colors.BLUE_GREY_700,
                            ),
                            ft.Divider(height=1),
                            ft.Text(
                                "This admin system provides dashboard monitoring, user management, and audit log visibility.",
                                size=13,
                                color=ft.colors.BLUE_GREY_600,
                            ),
                            ft.Text(
                                "Update backend deployment or environment settings to adjust service behavior.",
                                size=13,
                                color=ft.colors.BLUE_GREY_600,
                            ),
                        ],
                        spacing=14,
                    ),
                )
            ],
            expand=True,
        )

    def logout_user():
        nonlocal current_user, current_user_role
        current_user = None
        current_user_role = None
        show_login()

    def show_login():
        page.clean()
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER

        username_field = ft.TextField(label="Username", width=300, icon=ft.icons.PERSON)
        password_field = ft.TextField(label="Password", width=300, password=True, can_reveal_password=True, icon=ft.icons.LOCK)

        def attempt_login(_):
            nonlocal current_user, current_user_role
            if not username_field.value or not password_field.value:
                page.snack_bar = ft.SnackBar(ft.Text("Please fill out both fields."), open=True)
                page.update()
                return

            try:
                params = {"username": username_field.value, "password": password_field.value}
                res = requests.post(f"{BACKEND_URL}/auth/login", params=params, verify=False)
                if res.status_code == 200:
                    payload = res.json()
                    role = (payload.get("role") or "Admin").strip()
                    current_user = payload.get("username")
                    current_user_role = role
                    render_shell(page, current_user, logout_user, nav_items, build_dashboard_view())
                else:
                    page.snack_bar = ft.SnackBar(ft.Text("Invalid credentials."), open=True)
                    page.update()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Connection Failed: Ensure Backend is running. {ex}"), open=True)
                page.update()

        login_btn = ft.ElevatedButton("Log In", width=300, on_click=attempt_login, bgcolor=ft.colors.BLUE_800, color=ft.colors.WHITE)
        signup_link = ft.TextButton("Don't have an account? Sign Up", on_click=lambda _: show_signup())

        page.add(
            surface_card(
                ft.Column([
                    ft.Container(
                        content=ft.Icon(ft.icons.ACCOUNT_BALANCE, size=52, color=ft.colors.BLUE_800),
                        padding=14,
                        bgcolor=ft.colors.BLUE_GREY_50,
                        border_radius=20,
                    ),
                    ft.Text("LGU Tolosa - Sangguniang Bayan", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_900),
                    ft.Text("Administration System Login", size=14, color=ft.colors.BLUE_GREY_600),
                    ft.Container(height=4),
                    username_field,
                    password_field,
                    ft.Container(height=6),
                    login_btn,
                    signup_link,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                width=420,
                padding=36,
            )
        )
        page.update()

    def show_signup():
        page.clean()
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER

        reg_username = ft.TextField(label="Desired Username", width=300, icon=ft.icons.PERSON_ADD)
        reg_password = ft.TextField(label="Password", width=300, password=True, can_reveal_password=True, icon=ft.icons.LOCK_OUTLINE)
        reg_confirm_password = ft.TextField(label="Confirm Password", width=300, password=True, can_reveal_password=True, icon=ft.icons.LOCK)

        def attempt_signup(_):
            if not reg_username.value or not reg_password.value or not reg_confirm_password.value:
                page.snack_bar = ft.SnackBar(ft.Text("Please fill out all registration fields."), open=True)
                page.update()
                return

            if reg_password.value != reg_confirm_password.value:
                page.snack_bar = ft.SnackBar(ft.Text("Passwords do not match!"), open=True)
                page.update()
                return

            try:
                params = {"username": reg_username.value.strip(), "password": reg_password.value, "role": "Admin"}
                res = requests.post(f"{BACKEND_URL}/auth/register", params=params, verify=False)
                if res.status_code == 200:
                    page.snack_bar = ft.SnackBar(ft.Text("Account created successfully! You can now log in."), open=True)
                    show_login()
                else:
                    error_msg = res.json().get("detail", "Registration failed.")
                    page.snack_bar = ft.SnackBar(ft.Text(f"Error: {error_msg}"), open=True)
                page.update()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Connection Failed: Ensure Backend is running. {ex}"), open=True)
                page.update()

        register_btn = ft.ElevatedButton("Register Account", width=300, on_click=attempt_signup, bgcolor=ft.colors.GREEN_700, color=ft.colors.WHITE)
        back_to_login = ft.TextButton("Already have an account? Log In", on_click=lambda e: show_login())

        page.add(
            surface_card(
                ft.Column([
                    ft.Container(
                        content=ft.Icon(ft.icons.PERSON_ADD, size=52, color=ft.colors.GREEN_700),
                        padding=14,
                        bgcolor=ft.colors.GREEN_50,
                        border_radius=20,
                    ),
                    ft.Text("Create Administrator Account", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_800),
                    ft.Text("Sangguniang Bayan Registry", size=14, color=ft.colors.BLUE_GREY_600),
                    ft.Container(height=4),
                    reg_username,
                    reg_password,
                    reg_confirm_password,
                    ft.Container(height=6),
                    register_btn,
                    back_to_login,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                width=420,
                padding=36,
            )
        )
        page.update()

    nav_items = [
        (ft.icons.DASHBOARD_OUTLINED, "Dashboard", lambda: build_dashboard_view()),
        (ft.icons.DESCRIPTION_OUTLINED, "Documents", lambda: documents_view()),
        (ft.icons.GROUP_OUTLINED, "Committees", lambda: committees_view()),
        (ft.icons.PEOPLE_OUTLINED, "Users & Roles", lambda: users_roles_view()),
        (ft.icons.HISTORY_OUTLINED, "Audit Logs", lambda: audit_logs_view()),
        (ft.icons.SETTINGS_OUTLINED, "Settings", lambda: settings_view()),
    ]

    show_login()


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
