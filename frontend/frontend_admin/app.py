import flet as ft
if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors
if not hasattr(ft, "Icons") and hasattr(ft, "icons"):
    ft.Icons = ft.icons

# Compatibility shim: provide a `ft.Button(...)` factory that maps to the
# installed Flet button classes and supports legacy kwargs like `bgcolor`
# and `color` by wrapping the real button in a Container when needed.
if not hasattr(ft, "Button"):
    BaseButton = getattr(ft, "FilledButton", None) or getattr(ft, "ElevatedButton", None)

    def _compat_button(*args, **kwargs):
        bgcolor = kwargs.pop("bgcolor", None)
        color = kwargs.pop("color", None)
        # Keep icon and on_click etc. in kwargs for the underlying button
        icon = kwargs.get("icon", None)

        if BaseButton is None:
            raise RuntimeError("No suitable Button implementation found in flet package")

        # Construct underlying button with remaining kwargs
        try:
            btn = BaseButton(*args, **kwargs)
        except TypeError:
            # Some older/newer variants may not accept certain kwargs; try passing only common ones
            common = {}
            if len(args) > 0:
                common['label'] = args[0]
            if icon is not None:
                common['icon'] = icon
            if 'on_click' in kwargs:
                common['on_click'] = kwargs['on_click']
            btn = BaseButton(**common)

        # Apply foreground color if the control supports it
        try:
            if color is not None and hasattr(btn, 'color'):
                btn.color = color
        except Exception:
            pass

        # If a background color was requested, wrap the button in a Container
        if bgcolor is not None:
            return ft.Container(content=btn, bgcolor=bgcolor, padding=0)

        return btn

    ft.Button = _compat_button

# Alignment compatibility: map uppercase `ft.Alignment.CENTER` etc to
# `ft.alignment.center` where the installed Flet exposes lowercase names.
if hasattr(ft, 'Alignment') and hasattr(ft, 'alignment'):
    aln = ft.alignment
    mapping = {
        'CENTER': getattr(aln, 'center', None),
        'CENTER_LEFT': getattr(aln, 'center_left', None),
        'CENTER_RIGHT': getattr(aln, 'center_right', None),
        'TOP_CENTER': getattr(aln, 'top_center', None),
        'TOP_LEFT': getattr(aln, 'top_left', None),
        'TOP_RIGHT': getattr(aln, 'top_right', None),
        'BOTTOM_CENTER': getattr(aln, 'bottom_center', None),
        'BOTTOM_LEFT': getattr(aln, 'bottom_left', None),
        'BOTTOM_RIGHT': getattr(aln, 'bottom_right', None),
    }
    for k, v in mapping.items():
        if v is not None and not hasattr(ft.Alignment, k):
            setattr(ft.Alignment, k, v)
    
    # Padding compatibility shim: some flet versions require positional args
    # for Padding(left, top, right, bottom). Provide a callable/class that
    # accepts keyword arguments (`left=`, `top=`, `right=`, `bottom=`) and
    # preserves `symmetric`/`only` if available.
    if hasattr(ft, 'Padding'):
        import inspect

        OriginalPadding = ft.Padding
        try:
            sig = inspect.signature(OriginalPadding)
            # If signature doesn't contain 'left' parameter, wrap it
            if 'left' not in sig.parameters:
                def _padding(left=0, top=0, right=0, bottom=0):
                    return OriginalPadding(left, top, right, bottom)

                # attach symmetric/only if present on original
                if hasattr(OriginalPadding, 'symmetric'):
                    _padding.symmetric = staticmethod(lambda vertical=0, horizontal=0: OriginalPadding(horizontal, vertical, horizontal, vertical))
                if hasattr(OriginalPadding, 'only'):
                    _padding.only = staticmethod(lambda **kwargs: OriginalPadding(kwargs.get('left', 0), kwargs.get('top', 0), kwargs.get('right', 0), kwargs.get('bottom', 0)))

                ft.Padding = _padding
        except Exception:
            pass
import requests
import io
import base64
import qrcode
import mimetypes
import os
import sys
import json
import re
import secrets
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from dotenv import load_dotenv

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")
AUTH_TOKEN = os.getenv("BACKEND_AUTH_TOKEN")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from frontend.frontend_admin.committees import build_committees_view
from frontend.frontend_admin.documents import build_documents_view
from frontend.frontend_admin.users_roles import build_users_roles_view
from frontend.frontend_admin.audit_logs import build_audit_logs_view
from frontend.frontend_admin.admin_shell import render_shell

def main(page: ft.Page):
    page.title = "LGU Tolosa - Sangguniang Bayan Admin System"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.WHITE
    page.scroll = ft.ScrollMode.AUTO
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.padding = 8

    current_user = None
    current_user_role = None
    runtime_token = None

    def get_admin_headers():
        hdrs = {}
        if current_user:
            hdrs["X-Admin-Username"] = current_user
        if current_user_role:
            hdrs["X-Admin-Role"] = current_user_role
        # prefer runtime token if present, else env token
        token_to_use = runtime_token or AUTH_TOKEN
        if token_to_use:
            hdrs["Authorization"] = f"Bearer {token_to_use}"
        return hdrs

    # --- Login dialog and flow ---
    login_username = ft.TextField(label="Username", width=280)
    login_password = ft.TextField(label="Password", width=280, password=True, can_reveal_password=True)

    login_dialog = ft.AlertDialog(
        title=ft.Text("Admin Login"),
        content=ft.Column([login_username, login_password], spacing=8),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_login_dialog()),
            ft.Button("Login", on_click=lambda _: do_login()),
        ],
    )
    page.overlay.append(login_dialog)

    def close_login_dialog():
        login_dialog.open = False
        page.update()

    def do_login():
        nonlocal current_user, current_user_role, runtime_token
        try:
            resp = requests.post(
                f"{BACKEND_URL}/auth/login",
                data={"username": login_username.value or "", "password": login_password.value or ""},
                timeout=10,
                verify=False,
            )
            if resp.status_code == 200:
                body = resp.json()
                runtime_token = body.get("access_token")
                current_user = body.get("username") or current_user
                current_user_role = body.get("role") or current_user_role
                page.snack_bar = ft.SnackBar(ft.Text("Login successful"), open=True)
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"Login failed: {resp.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Login error: {exc}"), open=True)
        finally:
            close_login_dialog()
            page.update()

    def format_created_date(value):
        if not value:
            return "—"
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%m/%d/%Y")
        except Exception:
            return value

    users_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Username", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Full Name", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Role", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Created Date", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
        expand=True,
        column_spacing=12,
        horizontal_margin=0,
        data_row_min_height=44,
        data_text_style=ft.TextStyle(size=13),
        heading_text_style=ft.TextStyle(size=12, weight=ft.FontWeight.BOLD),
    )

    user_username_input = ft.TextField(label="Username", width=280)
    user_password_input = ft.TextField(label="Password", width=280, password=True, can_reveal_password=True)
    user_role_input = ft.Dropdown(
        label="Role",
        width=220,
        options=[
            ft.dropdown.Option("Admin"),
            ft.dropdown.Option("Secretary / Vice Mayor"),
            ft.dropdown.Option("Staff"),
        ],
        value="Admin",
    )

    users_notice = ft.Text("", size=12, color=ft.Colors.BLUE_GREY_600)
    pending_delete_user = None

    committee_editor_column = ft.Column(spacing=10)
    committee_notice = ft.Text("", size=12, color=ft.Colors.BLUE_GREY_600)
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
            ft.Button("Save", on_click=lambda _: on_committee_save()),
        ],
    )
    delete_committee_dialog = ft.AlertDialog(
        title=ft.Text("Confirm Action"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_delete_committee_dialog()),
            ft.Button("Delete", on_click=lambda _: delete_committee_action(), bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE),
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

    user_details_dialog = ft.AlertDialog(
        title=ft.Text("User Details"),
        content=ft.Container(content=ft.Text(""), padding=8),
        actions=[ft.TextButton("Close", on_click=lambda _: close_user_details_dialog())],
    )
    page.overlay.append(user_details_dialog)

    def refresh_user_display_ids(users):
        for idx, user in enumerate(users, start=1):
            user["display_id"] = idx

    def surface_card(content, width=None, padding=24, expand=False):
        return ft.Container(
            content=content,
            width=width,
            expand=expand,
            padding=padding,
            bgcolor=ft.Colors.WHITE,
            border_radius=24,
        )

    def section_header(title, subtitle, icon, accent_color):
        return ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, color=accent_color, size=24),
                    padding=10,
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    border_radius=14,
                ),
                ft.Column(
                    [
                        ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
                        ft.Text(subtitle, size=13, color=ft.Colors.BLUE_GREY_600),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def close_user_details_dialog():
        user_details_dialog.open = False
        page.update()

    def show_user_details(user):
        user_details_dialog.title = ft.Text("User Details")
        user_details_dialog.content = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Username", size=12, color=ft.Colors.BLUE_GREY_600),
                    ft.Text(user.get("username", "-"), size=14, weight=ft.FontWeight.BOLD),
                    ft.Text("Role", size=12, color=ft.Colors.BLUE_GREY_600),
                    ft.Text(user.get("role", "Admin"), size=14),
                    ft.Text("Status", size=12, color=ft.Colors.BLUE_GREY_600),
                    ft.Text(user.get("status", "Active"), size=14),
                ],
                spacing=8,
            ),
            padding=8,
        )
        user_details_dialog.open = True
        page.update()

    def show_registration_details(reg):
        user_details_dialog.title = ft.Text("Registration Details")
        user_details_dialog.content = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Username", size=12, color=ft.Colors.BLUE_GREY_600),
                    ft.Text(reg.get("username", "-"), size=14, weight=ft.FontWeight.BOLD),
                    ft.Text("Full Name", size=12, color=ft.Colors.BLUE_GREY_600),
                    ft.Text(reg.get("full_name") or reg.get("applicant_name", "-"), size=14),
                    ft.Text("Requested Role", size=12, color=ft.Colors.BLUE_GREY_600),
                    ft.Text(reg.get("requested_access") or reg.get("role", "-"), size=14),
                    ft.Text("Status", size=12, color=ft.Colors.BLUE_GREY_600),
                    ft.Text(reg.get("status", "Pending"), size=14),
                    ft.Text("Created Date", size=12, color=ft.Colors.BLUE_GREY_600),
                    ft.Text(reg.get("created_at") or "—", size=14),
                ],
                spacing=8,
            ),
            padding=8,
        )
        user_details_dialog.open = True
        page.update()

    def approve_registration(reg):
        try:
            response = requests.put(
                f"{BACKEND_URL}/registration/requests/{reg.get('id')}/approve",
                headers=get_admin_headers(),
                json={"final_role": reg.get("requested_access") or "Staff"},
                verify=False,
                timeout=10,
            )
            if response.status_code == 200:
                page.snack_bar = ft.SnackBar(ft.Text("Registration approved."), open=True)
                load_users_table()
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"Approve failed: {response.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Approve error: {exc}"), open=True)
        page.update()

    def reject_registration(reg):
        try:
            response = requests.put(
                f"{BACKEND_URL}/registration/requests/{reg.get('id')}/reject",
                headers=get_admin_headers(),
                json={"reason": "Rejected by admin"},
                verify=False,
                timeout=10,
            )
            if response.status_code == 200:
                page.snack_bar = ft.SnackBar(ft.Text("Registration rejected."), open=True)
                load_users_table()
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"Reject failed: {response.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Reject error: {exc}"), open=True)
        page.update()

    def show_not_implemented_action(action_name):
        users_notice.value = f"{action_name} is not yet implemented in the backend."
        page.update()

    def load_users_table():
        try:
            users_response = requests.get(
                f"{BACKEND_URL}/auth/users",
                headers=get_admin_headers(),
                verify=False,
                timeout=10,
            )
            users = users_response.json().get("items", []) if users_response.status_code == 200 else []

            regs_response = requests.get(
                f"{BACKEND_URL}/registration/requests",
                headers=get_admin_headers(),
                params={"status": "Pending"},
                verify=False,
                timeout=10,
            )
            regs = regs_response.json().get("items", []) if regs_response.status_code == 200 else []

            usernames = {u.get("username") for u in users if u.get("username")}
            accounts = []

            for user in users:
                accounts.append(
                    {
                        "source": "user",
                        "id": user.get("id"),
                        "username": user.get("username"),
                        "full_name": user.get("full_name") or user.get("username"),
                        "role": user.get("role", "Admin"),
                        "status": user.get("status", "Active"),
                        "created_at": user.get("created_at") or "—",
                        "raw": user,
                    }
                )

            for reg in regs:
                status = (reg.get("status") or "Pending").strip()
                if status != "Pending":
                    continue
                if reg.get("username") in usernames:
                    continue
                accounts.append(
                    {
                        "source": "registration",
                        "id": reg.get("id"),
                        "username": reg.get("username") or reg.get("email") or "-",
                        "full_name": reg.get("full_name") or reg.get("applicant_name") or f"{(reg.get('first_name') or '').strip()} {(reg.get('last_name') or '').strip()}".strip(),
                        "role": reg.get("requested_access") or "-",
                        "status": status,
                        "created_at": reg.get("created_at") or "—",
                        "raw": reg,
                    }
                )

            refresh_user_display_ids(accounts)
            rows = []
            for acct in accounts:
                display_id = acct.get("display_id") or acct.get("id") or "-"
                if acct["source"] == "registration":
                    actions = [
                        ft.PopupMenuItem(content=ft.Text("View Details"), on_click=lambda _, a=acct: show_registration_details(a)),
                        ft.PopupMenuItem(content=ft.Text("Approve Registration"), on_click=lambda _, a=acct: approve_registration(a)),
                        ft.PopupMenuItem(content=ft.Text("Reject Registration"), on_click=lambda _, a=acct: reject_registration(a)),
                    ]
                else:
                    actions = [
                        ft.PopupMenuItem(content=ft.Text("View User"), on_click=lambda _, a=acct: show_user_details(a.get("raw", {}))),
                        ft.PopupMenuItem(content=ft.Text("Set Admin"), on_click=lambda _, a=acct: update_user_role(a.get("raw", {}), "Admin")),
                        ft.PopupMenuItem(content=ft.Text("Set Secretary / Vice Mayor"), on_click=lambda _, a=acct: update_user_role(a.get("raw", {}), "Secretary / Vice Mayor")),
                        ft.PopupMenuItem(content=ft.Text("Set Staff"), on_click=lambda _, a=acct: update_user_role(a.get("raw", {}), "Staff")),
                        ft.PopupMenuItem(content=ft.Text("Activate Account"), on_click=lambda _, a=acct: show_not_implemented_action("Activate Account")),
                        ft.PopupMenuItem(content=ft.Text("Deactivate Account"), on_click=lambda _, a=acct: show_not_implemented_action("Deactivate Account")),
                        ft.PopupMenuItem(content=ft.Text("Reset Password"), on_click=lambda _, a=acct: show_not_implemented_action("Reset Password")),
                        ft.PopupMenuItem(content=ft.Text("Delete User"), on_click=lambda _, a=acct: confirm_delete_user(a.get("raw", {}))),
                    ]

                rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text(str(display_id), size=13),
                                    width=60,
                                    alignment=ft.Alignment.CENTER,
                                )
                            ),
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text(
                                        acct.get("username", "-"),
                                        size=13,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        no_wrap=True,
                                    ),
                                )
                            ),
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text(
                                        acct.get("full_name") or acct.get("username", "-"),
                                        size=13,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        no_wrap=True,
                                    ),
                                )
                            ),
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text(
                                        acct.get("role", "-"),
                                        size=13,
                                    ),
                                    width=120,
                                    alignment=ft.Alignment.CENTER,
                                )
                            ),
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text(
                                        acct.get("status", "Pending"),
                                        size=13,
                                    ),
                                    width=110,
                                    alignment=ft.Alignment.CENTER,
                                )
                            ),
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text(format_created_date(acct.get("created_at")), size=13),
                                    width=100,
                                    alignment=ft.Alignment.CENTER,
                                )
                            ),
                            ft.DataCell(
                                ft.Container(
                                    content=ft.PopupMenuButton(
                                        icon=ft.Icons.MORE_VERT,
                                        tooltip="User actions",
                                        items=actions,
                                    ),
                                    width=140,
                                    alignment=ft.Alignment.CENTER,
                                )
                            ),
                        ],
                    )
                )
            users_table.rows = rows
            users_notice.value = "" if rows else "No users found in the current database."
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
                timeout=10,
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
                headers=get_admin_headers(),
                params={"role": role},
                verify=False,
                timeout=10,
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
                headers=get_admin_headers(),
                verify=False,
                timeout=10,
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
            ft.Button(
                "Delete",
                icon=ft.Icons.DELETE_OUTLINE,
                bgcolor=ft.Colors.RED_700,
                color=ft.Colors.WHITE,
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

    def load_audit_logs_view():
        try:
            response = requests.get(f"{BACKEND_URL}/audit/logs", headers=get_admin_headers(), verify=False)
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
        try:
            return build_audit_logs_view(audit_logs_table, load_audit_logs_view, surface_card, section_header)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print("audit_logs_view error:\n", tb)
            return ft.Column([ft.Text("Error building Audit Logs view"), ft.Text(str(e)), ft.Text(tb)])

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
                                    ft.IconButton(ft.Icons.EDIT, tooltip="Edit", on_click=lambda _, idx=index: open_committee_dialog(idx)),
                                    ft.IconButton(ft.Icons.DELETE, tooltip="Delete", on_click=lambda _, idx=index: confirm_delete_committee(idx)),
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
        try:
            return build_committees_view(committee_table, open_committee_dialog, surface_card, section_header)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print("committees_view error:\n", tb)
            return ft.Column([ft.Text("Error building Committees view"), ft.Text(str(e)), ft.Text(tb)])

    def users_roles_view():
        try:
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
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print("users_roles_view error:\n", tb)
            return ft.Column([ft.Text("Error building Users & Roles view"), ft.Text(str(e)), ft.Text(tb)])

    documents_data = []
    archived_documents_data = []

    def get_document_status_style(status):
        normalized = (status or "").strip().lower()
        if normalized in {"pending", "under review"}:
            return ft.Colors.ORANGE_700, ft.Colors.ORANGE_50
        if normalized in {"in routing", "routed"}:
            return ft.Colors.BLUE_700, ft.Colors.BLUE_50
        if normalized in {"received"}:
            return ft.Colors.CYAN_700, ft.Colors.CYAN_50
        if normalized in {"approved", "completed"}:
            return ft.Colors.GREEN_700, ft.Colors.GREEN_50
        if normalized in {"returned"}:
            return ft.Colors.RED_700, ft.Colors.RED_50
        if normalized in {"archived"}:
            return ft.Colors.BLUE_GREY_700, ft.Colors.BLUE_GREY_50
        return ft.Colors.BLUE_GREY_700, ft.Colors.BLUE_GREY_50

    documents_search_field = ft.TextField(
        label="Search documents",
        hint_text="Search by Tracking ID, title, type, status, or location...",
        prefix_icon=ft.Icon(ft.Icons.SEARCH, size=18, color=ft.Colors.BLUE_GREY_600),
        expand=True,
        on_change=lambda _: load_documents_table(),
    )
    documents_filter_status = ft.Dropdown(
        label="Status",
        width=140,
        options=[ft.dropdown.Option("All"), ft.dropdown.Option("Pending"), ft.dropdown.Option("In Routing"), ft.dropdown.Option("Received"), ft.dropdown.Option("Approved"), ft.dropdown.Option("Returned"), ft.dropdown.Option("Archived")],
        value="All",
    )
    documents_filter_type = ft.Dropdown(
        label="Document Type",
        width=160,
        options=[ft.dropdown.Option("All"), ft.dropdown.Option("Ordinance"), ft.dropdown.Option("Resolution"), ft.dropdown.Option("Committee Report")],
        value="All",
    )
    documents_filter_category = ft.Dropdown(
        label="Category",
        width=140,
        options=[ft.dropdown.Option("All"), ft.dropdown.Option("Legislation"), ft.dropdown.Option("Policy"), ft.dropdown.Option("Report")],
        value="All",
    )
    documents_filter_office = ft.Dropdown(
        label="Current Office",
        width=180,
        options=[ft.dropdown.Option("All"), ft.dropdown.Option("SB Secretariat"), ft.dropdown.Option("Office of the Mayor"), ft.dropdown.Option("Committee on Health")],
        value="All",
    )
    documents_sort_filter = ft.Dropdown(
        label="Sort",
        width=140,
        options=[ft.dropdown.Option("Newest"), ft.dropdown.Option("Oldest"), ft.dropdown.Option("Title")],
        value="Newest",
    )
    documents_filter_start_date = ft.TextField(label="Start Date", hint_text="YYYY-MM-DD", width=140)
    documents_filter_end_date = ft.TextField(label="End Date", hint_text="YYYY-MM-DD", width=140)
    documents_year_filter = ft.TextField(label="Year", hint_text="YYYY", width=100)
    documents_status_filter = documents_filter_status
    documents_category_filter = documents_filter_category
    documents_type_filter = documents_filter_type
    documents_assigned_filter = documents_filter_office

    documents_form_tracking = ft.TextField(label="Tracking Number", expand=True)
    documents_form_tracking.disabled = True
    documents_form_title = ft.TextField(label="Title", expand=True)
    def on_title_change(e):
        nonlocal documents_form_title_auto_generated
        documents_form_title_auto_generated = False
    documents_form_title.on_change = on_title_change
    documents_form_description = ft.TextField(label="Description", multiline=True, min_lines=3, max_lines=6, expand=True)
    documents_form_document_type = ft.TextField(label="Document Type", expand=True)
    documents_form_category = ft.TextField(label="Category", expand=True)
    documents_form_originating_office = ft.TextField(label="Originating Office", expand=True)
    documents_form_current_office = ft.TextField(label="Current Office", expand=True)
    documents_form_assigned_to = ft.TextField(label="Assigned To", expand=True)
    documents_form_status = ft.Dropdown(
        label="Status",
        width=180,
        options=[
            ft.dropdown.Option("Pending"),
            ft.dropdown.Option("In Routing"),
            ft.dropdown.Option("Received"),
            ft.dropdown.Option("Approved"),
            ft.dropdown.Option("Returned"),
            ft.dropdown.Option("Archived"),
        ],
        value="Pending",
    )
    documents_form_priority = ft.Dropdown(
        label="Priority",
        width=180,
        options=[ft.dropdown.Option("Low"), ft.dropdown.Option("Medium"), ft.dropdown.Option("High")],
        value="Medium",
    )
    documents_form_remarks = ft.TextField(label="Remarks", multiline=True, min_lines=2, max_lines=4, expand=True)
    documents_form_created_by = ft.TextField(label="Created By", expand=True)
    documents_form_author = ft.TextField(label="Author", expand=True)
    documents_form_session = ft.TextField(label="Session", expand=True)
    documents_form_date_registered = ft.TextField(label="Date Registered", expand=True, hint_text="YYYY-MM-DD")
    documents_form_attachment_file = None
    documents_form_attachment_file_name = ""
    documents_form_attachment_name = ft.TextField(value="", visible=False)
    documents_form_attachment_display = ft.Text("No file selected", size=13, color=ft.Colors.BLUE_GREY_700)
    documents_form_title_auto_generated = False

    documents_form_mode = "create"
    documents_form_target_id = None

    # Choose file coroutine using the FilePicker service (Flet 0.86.5)
    async def choose_attachment_file():
        nonlocal documents_form_attachment_file, documents_form_attachment_file_name, documents_form_title_auto_generated
        try:
            file_picker = ft.FilePicker()
            files = await file_picker.pick_files(
                dialog_title="Choose attachment",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf", "doc", "docx"],
                allow_multiple=False,
                with_data=True,
            )
            if not files:
                # user cancelled
                return
            selected = files[0]
            # Verify bytes available
            if not selected.bytes:
                show_document_notice("Unable to read the selected file. Please try again.")
                return
            documents_form_attachment_file = selected.bytes
            documents_form_attachment_file_name = selected.name
            documents_form_attachment_display.value = selected.name
            # Auto-populate title if user hasn't typed one (or previous title was auto-generated)
            if (not documents_form_title.value or documents_form_title.value.strip() == "") or documents_form_title_auto_generated:
                base = os.path.splitext(selected.name)[0]
                title = base.replace("_", " ")
                title = " ".join(title.split())
                documents_form_title.value = title
                documents_form_title_auto_generated = True
            page.update()
        except Exception as exc:
            show_document_notice(f"File selection failed: {exc}")

    documents_form_dialog = ft.AlertDialog(
        title=ft.Text("Register Document"),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("Capture a new document record for routing and tracking.", size=13, color=ft.Colors.BLUE_GREY_600),
                    ft.Row([documents_form_tracking, documents_form_status], spacing=12),
                    documents_form_title,
                    documents_form_description,
                    ft.Row([documents_form_document_type, documents_form_category], spacing=12),
                    ft.Row([documents_form_originating_office, documents_form_current_office], spacing=12),
                    ft.Row([documents_form_author, documents_form_session], spacing=12),
                    documents_form_date_registered,
                    ft.Divider(height=1),
                    ft.Text("Attachment", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Selected File:", size=12, color=ft.Colors.BLUE_GREY_600),
                                    documents_form_attachment_display,
                                    ft.Text(
                                        "Accepted formats: PDF (.pdf), Microsoft Word (.doc), Microsoft Word (.docx)",
                                        size=12,
                                        color=ft.Colors.BLUE_GREY_600,
                                    ),
                                ],
                                expand=True,
                                spacing=6,
                            ),
                            ft.Container(
                                content=ft.Button("Choose File", icon=ft.Icons.ATTACH_FILE, on_click=lambda e: page.run_task(choose_attachment_file)),
                                alignment=ft.Alignment.CENTER,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row([documents_form_assigned_to, documents_form_priority], spacing=12),
                    documents_form_remarks,
                    documents_form_created_by,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=620,
            padding=8,
        ),
        actions=[ft.TextButton("Cancel", on_click=lambda _: close_documents_form_dialog()), ft.Button("Save", on_click=lambda _: submit_document_form())],
    )
    page.overlay.append(documents_form_dialog)

    documents_details_dialog = ft.AlertDialog(
        title=ft.Text("Document Details"),
        content=ft.Container(content=ft.Text(""), padding=8),
        actions=[ft.TextButton("Close", on_click=lambda _: close_documents_details_dialog())],
    )
    page.overlay.append(documents_details_dialog)

    pending_delete_document = None
    documents_delete_dialog = ft.AlertDialog(
        title=ft.Text("Archive Document"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_documents_delete_dialog()),
            ft.Button("Okay", bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda _: run_delete_document_action()),
        ],
    )
    page.overlay.append(documents_delete_dialog)

    scan_input_field = ft.TextField(label="Scan QR / Tracking", width=280, hint_text="Scan code or enter tracking number")
    scan_destination_field = ft.TextField(label="Destination Office", width=280)
    scan_location_field = ft.TextField(label="Current Location", width=280)
    scan_remarks_field = ft.TextField(label="Remarks", width=280, multiline=True, min_lines=2, max_lines=4)
    scan_action_dropdown = ft.Dropdown(
        label="Action",
        width=200,
        options=[
            ft.dropdown.Option("Scan"),
            ft.dropdown.Option("Forward"),
            ft.dropdown.Option("Review"),
            ft.dropdown.Option("Return"),
        ],
        value="Scan",
    )
    scan_status_dropdown = ft.Dropdown(
        label="Status",
        width=200,
        options=[
            ft.dropdown.Option("In Routing"),
            ft.dropdown.Option("Pending"),
            ft.dropdown.Option("Approved"),
            ft.dropdown.Option("Returned"),
        ],
        value="In Routing",
    )
    scan_submit_button = ft.Button("Submit Scan", icon=ft.Icons.QR_CODE_2, on_click=lambda _: submit_qr_scan())

    qr_scan_dialog = ft.AlertDialog(
        title=ft.Text("QR Scan"),
        content=ft.Column(
            [
                scan_input_field,
                ft.Row([scan_location_field, scan_destination_field], spacing=12),
                ft.Row([scan_action_dropdown, scan_status_dropdown], spacing=12),
                scan_remarks_field,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_qr_scan_dialog()),
            scan_submit_button,
        ],
    )
    page.overlay.append(qr_scan_dialog)

    qr_monitor_content = ft.Column(spacing=8)
    qr_monitor_dialog = ft.AlertDialog(
        title=ft.Text("QR Monitor"),
        content=ft.Container(content=qr_monitor_content, padding=16, width=520),
        actions=[
            ft.TextButton("Close", on_click=lambda _: close_qr_monitor_dialog()),
        ],
    )
    page.overlay.append(qr_monitor_dialog)

    def close_qr_scan_dialog():
        qr_scan_dialog.open = False
        page.update()

    def close_qr_monitor_dialog():
        qr_monitor_dialog.open = False
        page.update()

    def format_qr_monitor_details(payload):
        summary = []
        summary.append(ft.Text(f"Total documents: {payload.get('total_documents', 0)}", size=13, weight=ft.FontWeight.BOLD))
        summary.append(ft.Text(f"Successful scans: {payload.get('successful_scans', 0)}", size=13))
        summary.append(ft.Text(f"Unrecognized scans: {payload.get('unrecognized_scans', 0)}", size=13))
        latest_scan = payload.get('latest_scan')
        if latest_scan:
            summary.append(ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100))
            summary.append(ft.Text("Latest scan", size=13, weight=ft.FontWeight.BOLD))
            summary.append(ft.Text(f"Actor: {latest_scan.get('actor', 'N/A')}", size=12))
            summary.append(ft.Text(f"Action: {latest_scan.get('action', 'N/A')}", size=12))
            summary.append(ft.Text(f"Target: {latest_scan.get('target_id', 'N/A')}", size=12))
            summary.append(ft.Text(f"Time: {latest_scan.get('created_at', 'N/A')}", size=12))
            details = latest_scan.get('details')
            if details:
                summary.append(ft.Text(f"Details: {details}", size=12, color=ft.Colors.BLUE_GREY_700))
        documents = payload.get('documents') or []
        if documents:
            summary.append(ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100))
            summary.append(ft.Text("Recent documents", size=13, weight=ft.FontWeight.BOLD))
            for doc in documents[:8]:
                summary.append(ft.Text(f"{doc.get('tracking_number', 'N/A')} — {doc.get('status', 'N/A')} — {doc.get('current_office', 'N/A')}", size=12))
        return summary

    def load_qr_monitor_data():
        try:
            response = requests.get(f"{BACKEND_URL}/documents/qr/monitor", verify=False, timeout=10)
            if response.status_code != 200:
                raise Exception(response.text)
            payload = response.json() if response.content else {}
            qr_monitor_content.controls = format_qr_monitor_details(payload)
        except Exception as exc:
            qr_monitor_content.controls = [ft.Text(f"Unable to load QR monitor data: {exc}", size=12, color=ft.Colors.RED_700)]
        page.update()

    def open_qr_monitor(_=None):
        qr_monitor_dialog.open = True
        qr_monitor_content.controls = [ft.Text("Loading QR monitor data...", size=13, color=ft.Colors.BLUE_GREY_700)]
        page.update()
        load_qr_monitor_data()

    def open_qr_scan_dialog(_=None):
        qr_scan_dialog.open = True
        scan_input_field.value = scan_input_field.value or ""
        scan_location_field.value = scan_location_field.value or ""
        scan_destination_field.value = scan_destination_field.value or ""
        scan_remarks_field.value = scan_remarks_field.value or ""
        scan_action_dropdown.value = "Scan"
        scan_status_dropdown.value = "In Routing"
        page.update()

    def submit_qr_scan():
        qr_value = (scan_input_field.value or "").strip()
        if not qr_value:
            show_document_notice("QR/tracking value is required.")
            return
        payload = {
            "qr_value": qr_value,
            "scanner": current_user or "Unknown",
            "current_location": (scan_location_field.value or "").strip() or "",
            "destination": (scan_destination_field.value or "").strip() or "",
            "remarks": (scan_remarks_field.value or "").strip() or scan_action_dropdown.value or "Scan",
            "action": scan_action_dropdown.value or "Scan",
            "status": scan_status_dropdown.value or "In Routing",
        }
        try:
            response = requests.post(f"{BACKEND_URL}/documents/scan", json=payload, verify=False, timeout=10)
            if response.status_code != 200:
                raise Exception(response.text)
            load_documents_table()
            hide_page = current_user
            show_document_notice("QR scan submitted successfully.")
            close_qr_scan_dialog()
        except Exception as exc:
            show_document_notice(f"QR scan failed: {exc}")

    def make_document_header(label, width):
        return ft.Container(
            content=ft.Text(label, weight=ft.FontWeight.BOLD, size=12),
            width=width,
            alignment=ft.Alignment.CENTER_LEFT,
            padding=ft.Padding(0, 0, 0, 0),
        )

    documents_table = ft.DataTable(
        columns=[
            ft.DataColumn(label=make_document_header("Actions", 90)),
            ft.DataColumn(label=make_document_header("Tracking No.", 120)),
            ft.DataColumn(label=make_document_header("Title", 280)),
            ft.DataColumn(label=make_document_header("Document Type", 120)),
            ft.DataColumn(label=make_document_header("Category", 100)),
            ft.DataColumn(label=make_document_header("Originating Office", 150)),
            ft.DataColumn(label=make_document_header("Current Office", 140)),
            ft.DataColumn(label=make_document_header("Assigned To", 110)),
            ft.DataColumn(label=make_document_header("Status", 120)),
            ft.DataColumn(label=make_document_header("Priority", 80)),
            ft.DataColumn(label=make_document_header("Date Received", 100)),
            ft.DataColumn(label=make_document_header("Last Updated", 100)),
        ],
        rows=[],
        width=1600,
        column_spacing=10,
        horizontal_margin=0,
        data_row_min_height=52,
        data_text_style=ft.TextStyle(size=13),
        heading_text_style=ft.TextStyle(
            size=12,
            weight=ft.FontWeight.BOLD,
        ),
        horizontal_lines=ft.BorderSide(width=1, color=ft.Colors.BLUE_GREY_100),
        border_radius=10,
    )

    documents_notice = ft.Text("", size=12, color=ft.Colors.BLUE_GREY_600)

    documents_empty_state = ft.Container(
        content=ft.Text(
            "No documents match your search.",
            size=13,
            color=ft.Colors.BLUE_GREY_600,
            text_align=ft.TextAlign.CENTER,
        ),
        width=1600,
        height=40,
        alignment=ft.Alignment.CENTER,
        visible=False,
        padding=ft.Padding(left=0, top=8, right=0, bottom=8),
    )

    archived_documents_table = ft.DataTable(
        columns=[
            ft.DataColumn(label=make_document_header("Actions", 90)),
            ft.DataColumn(label=make_document_header("Tracking No.", 120)),
            ft.DataColumn(label=make_document_header("Title", 280)),
            ft.DataColumn(label=make_document_header("Document Type", 120)),
            ft.DataColumn(label=make_document_header("Category", 100)),
            ft.DataColumn(label=make_document_header("Originating Office", 150)),
            ft.DataColumn(label=make_document_header("Current Office", 140)),
            ft.DataColumn(label=make_document_header("Assigned To", 110)),
            ft.DataColumn(label=make_document_header("Status", 120)),
            ft.DataColumn(label=make_document_header("Priority", 80)),
            ft.DataColumn(label=make_document_header("Date Received", 100)),
            ft.DataColumn(label=make_document_header("Last Updated", 100)),
        ],
        rows=[],
        width=1600,
        column_spacing=10,
        horizontal_margin=0,
        data_row_min_height=52,
        data_text_style=ft.TextStyle(size=13),
        heading_text_style=ft.TextStyle(
            size=12,
            weight=ft.FontWeight.BOLD,
        ),
        horizontal_lines=ft.BorderSide(width=1, color=ft.Colors.BLUE_GREY_100),
        border_radius=10,
    )

    archived_documents_notice = ft.Text("", size=12, color=ft.Colors.BLUE_GREY_600)

    archived_documents_empty_state = ft.Container(
        content=ft.Text(
            "No archived documents available.",
            size=13,
            color=ft.Colors.BLUE_GREY_600,
            text_align=ft.TextAlign.CENTER,
        ),
        width=1600,
        height=40,
        alignment=ft.Alignment.CENTER,
        visible=False,
        padding=ft.Padding(left=0, top=8, right=0, bottom=8),
    )

    archived_documents_search_field = ft.TextField(
        label="Search archived documents",
        hint_text="Search by Tracking ID, title, type, status, or location...",
        prefix_icon=ft.Icon(ft.Icons.SEARCH, size=18, color=ft.Colors.BLUE_GREY_600),
        width=320,
        on_change=lambda _: load_archived_documents_table(),
        on_submit=lambda _: load_archived_documents_table(),
    )

    archived_documents_filter_status = ft.Dropdown(
        label="Status",
        width=140,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("Pending"),
            ft.dropdown.Option("In Routing"),
            ft.dropdown.Option("Received"),
            ft.dropdown.Option("Approved"),
            ft.dropdown.Option("Returned"),
            ft.dropdown.Option("Archived"),
        ],
        value="All",
    )
    archived_documents_filter_type = ft.Dropdown(
        label="Document Type",
        width=160,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("Ordinance"),
            ft.dropdown.Option("Resolution"),
            ft.dropdown.Option("Committee Report"),
        ],
        value="All",
    )
    archived_documents_filter_category = ft.Dropdown(
        label="Category",
        width=140,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("Legislation"),
            ft.dropdown.Option("Policy"),
            ft.dropdown.Option("Report"),
        ],
        value="All",
    )
    archived_documents_filter_office = ft.Dropdown(
        label="Current Office",
        width=180,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("SB Secretariat"),
            ft.dropdown.Option("Office of the Mayor"),
            ft.dropdown.Option("Committee on Health"),
        ],
        value="All",
    )
    archived_documents_sort_filter = ft.Dropdown(
        label="Sort",
        width=140,
        options=[
            ft.dropdown.Option("Newest"),
            ft.dropdown.Option("Oldest"),
            ft.dropdown.Option("Title"),
        ],
        value="Newest",
    )
    archived_documents_filter_start_date = ft.TextField(label="Start Date", hint_text="YYYY-MM-DD", width=140)
    archived_documents_filter_end_date = ft.TextField(label="End Date", hint_text="YYYY-MM-DD", width=140)
    archived_documents_year_filter = ft.TextField(label="Year", hint_text="YYYY", width=100)

    archived_documents_apply_button = ft.OutlinedButton("Apply", icon=ft.Icons.FILTER_LIST, on_click=lambda _: load_archived_documents_table())
    archived_documents_refresh_button = ft.Button(
        "Refresh",
        icon=ft.Icons.REFRESH,
        on_click=lambda _: reset_archived_document_filters(),
    )

    def normalize_search_text(value):
        if value is None:
            return ""
        return " ".join(str(value).strip().split()).lower()

    def normalize_tracking_identifier(value):
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None

        if text.isdigit():
            return int(text.lstrip("0") or "0")

        digits = []
        for chunk in re.findall(r"\d+", text):
            digits.append(chunk)

        if not digits:
            return None

        last_digits = digits[-1]
        return int(last_digits.lstrip("0") or "0")

    def looks_like_tracking_search(value):
        text = normalize_search_text(value)
        return bool(text) and any(ch.isdigit() for ch in text)

    def get_document_search_mode(search_text):
        text = normalize_search_text(search_text)
        if not text:
            return "Smart search"
        if looks_like_tracking_search(text):
            return "Tracking ID • Exact match"
        return "Smart search"

    def document_matches_search_term(doc, term):
        query = normalize_search_text(term)
        if not query:
            return True

        if looks_like_tracking_search(query):
            doc_tracking = normalize_tracking_identifier(doc.get("tracking_number") or doc.get("id"))
            search_tracking = normalize_tracking_identifier(query)
            if doc_tracking is None or search_tracking is None:
                return False
            return doc_tracking == search_tracking

        fields = [
            doc.get("title"),
            doc.get("document_type"),
            doc.get("status"),
            doc.get("current_office"),
            doc.get("assigned_to"),
            doc.get("originating_office"),
            doc.get("category"),
            doc.get("description"),
            doc.get("remarks"),
            doc.get("author"),
            doc.get("session"),
            doc.get("tracking_number"),
            doc.get("created_by"),
        ]

        for field_value in fields:
            if field_value is None:
                continue
            normalized_field = normalize_search_text(field_value)
            if normalized_field and query in normalized_field:
                return True
        return False

    def apply_document_search(documents, search_text=None):
        if search_text is None:
            search_text = documents_search_field.value
        query = normalize_search_text(search_text)
        if not query:
            return list(documents)

        terms = [token for token in query.split() if token]
        if not terms:
            return list(documents)

        filtered = []
        for doc in documents:
            if all(document_matches_search_term(doc, term) for term in terms):
                filtered.append(doc)
        return filtered

    def update_document_result_indicator(display_documents, visible_count=None):
        search_text = normalize_search_text(documents_search_field.value)
        mode_text = get_document_search_mode(search_text)
        if not display_documents:
            documents_notice.value = f"{mode_text} • No matching documents"
            return
        count_label = "document" if len(display_documents) == 1 else "documents"
        if visible_count is not None and visible_count < len(display_documents):
            documents_notice.value = f"{mode_text} • Showing {visible_count} of {len(display_documents)} matching {count_label}"
            return
        documents_notice.value = f"{mode_text} • Showing {len(display_documents)} {count_label}"

    def show_document_notice(message):
        page.snack_bar = ft.SnackBar(ft.Text(message), open=True)
        page.update()

    # File selection for attachment inside Register Document form
    # Uses inline FilePicker coroutine (no overlay append, no separate page)

    def close_documents_form_dialog():
        documents_form_dialog.open = False
        page.update()

    def close_documents_details_dialog():
        documents_details_dialog.open = False
        page.update()

    def close_documents_delete_dialog():
        nonlocal pending_delete_document
        pending_delete_document = None
        documents_delete_dialog.open = False
        page.update()

    def confirm_delete_document(doc):
        nonlocal pending_delete_document
        pending_delete_document = doc
        documents_delete_dialog.title = ft.Text("Archive Document")
        documents_delete_dialog.content = ft.Text(f"Archive document \"{doc.get('title', 'this document')}\"? This action moves the record to Archived Documents.")
        documents_delete_dialog.open = True
        page.update()

    def run_delete_document_action():
        nonlocal pending_delete_document
        document = pending_delete_document
        close_documents_delete_dialog()
        if document:
            delete_document_record(document.get("id"))
            render_shell(page, current_user, logout_user, nav_items, archived_documents_view(), initial_selected_index=1)

    def generate_tracking_number():
        try:
            response = requests.get(f"{BACKEND_URL}/documents", verify=False, timeout=10)
            if response.status_code == 200:
                payload = response.json() if response.content else []
                documents = payload if isinstance(payload, list) else payload.get("items", [])
                used_numbers = set()
                for doc in documents:
                    tracking = str(doc.get("tracking_number", "") or "").strip()
                    if tracking.startswith("DOC-"):
                        suffix = tracking.replace("DOC-", "", 1)
                        if suffix.isdigit():
                            used_numbers.add(int(suffix))
                candidate = 1
                while candidate in used_numbers:
                    candidate += 1
                return f"DOC-{candidate}"
        except Exception:
            pass
        return "DOC-1"

    def reset_document_form():
        nonlocal documents_form_attachment_file, documents_form_attachment_file_name, documents_form_title_auto_generated
        documents_form_tracking.value = ""
        documents_form_title.value = ""
        documents_form_description.value = ""
        documents_form_document_type.value = ""
        documents_form_category.value = ""
        documents_form_originating_office.value = ""
        documents_form_current_office.value = ""
        documents_form_assigned_to.value = ""
        documents_form_status.value = "Pending"
        documents_form_priority.value = "Medium"
        documents_form_remarks.value = ""
        documents_form_created_by.value = ""
        documents_form_author.value = ""
        documents_form_session.value = ""
        documents_form_date_registered.value = datetime.now().strftime("%Y-%m-%d")
        documents_form_attachment_name.value = ""
        documents_form_attachment_file = None
        documents_form_attachment_file_name = ""
        documents_form_attachment_display.value = "No file selected"
        documents_form_title_auto_generated = False

    def populate_document_form(doc):
        documents_form_tracking.value = doc.get("tracking_number", "") or ""
        documents_form_title.value = doc.get("title", "") or ""
        documents_form_description.value = doc.get("description", "") or ""
        documents_form_document_type.value = doc.get("document_type", "") or ""
        documents_form_category.value = doc.get("category", "") or ""
        documents_form_originating_office.value = doc.get("originating_office", "") or ""
        documents_form_current_office.value = doc.get("current_office", "") or ""
        documents_form_assigned_to.value = doc.get("assigned_to", "") or ""
        documents_form_status.value = doc.get("status") or "Pending"
        documents_form_priority.value = doc.get("priority") or "Medium"
        documents_form_remarks.value = doc.get("remarks", "") or ""
        documents_form_created_by.value = doc.get("created_by", "") or ""
        documents_form_author.value = doc.get("author", "") or ""
        documents_form_session.value = doc.get("session", "") or ""
        documents_form_date_registered.value = doc.get("date_registered", "") or ""
        documents_form_attachment_name.value = doc.get("attachment_name", "") or ""
        # when editing an existing record we don't have file bytes in frontend
        nonlocal documents_form_attachment_file, documents_form_attachment_file_name, documents_form_title_auto_generated
        documents_form_attachment_file = None
        documents_form_attachment_file_name = ""
        documents_form_attachment_display.value = doc.get("attachment_name", "") or "No file selected"
        documents_form_title_auto_generated = False

    def open_document_form(doc=None):
        nonlocal documents_form_mode, documents_form_target_id
        documents_form_mode = "edit" if doc and doc.get("id") else "create"
        documents_form_target_id = doc.get("id") if doc and doc.get("id") else None
        documents_form_dialog.title = ft.Text("Edit Document" if documents_form_mode == "edit" else "Register Document")
        if doc:
            populate_document_form(doc)
        else:
            reset_document_form()
            documents_form_tracking.value = generate_tracking_number()
        documents_form_dialog.open = True
        page.update()

    def submit_document_form():
        payload = {
            "tracking_number": (documents_form_tracking.value or "").strip(),
            "title": (documents_form_title.value or "").strip(),
            "description": (documents_form_description.value or "").strip() or None,
            "document_type": (documents_form_document_type.value or "").strip() or None,
            "category": (documents_form_category.value or "").strip() or None,
            "originating_office": (documents_form_originating_office.value or "").strip() or None,
            "current_office": (documents_form_current_office.value or "").strip() or None,
            "assigned_to": (documents_form_assigned_to.value or "").strip() or None,
            "status": (documents_form_status.value or "Pending").strip() or "Pending",
            "priority": (documents_form_priority.value or "Medium").strip() or "Medium",
            "remarks": (documents_form_remarks.value or "").strip() or None,
            "created_by": (documents_form_created_by.value or "").strip() or None,
            "author": (documents_form_author.value or "").strip() or None,
            "session": (documents_form_session.value or "").strip() or None,
            "date_registered": (documents_form_date_registered.value or "").strip() or None,
            "attachment_name": (documents_form_attachment_name.value or "").strip() or None,
        }
        if not payload["title"]:
            show_document_notice("Title is required.")
            return
        if not payload["tracking_number"]:
            payload["tracking_number"] = generate_tracking_number()
        if documents_form_mode == "edit" and documents_form_target_id is not None:
            update_document_record(documents_form_target_id, payload)
        else:
            create_document_record(payload)
        close_documents_form_dialog()

    def open_route_dialog(doc):
        route_destination = ft.TextField(label="Destination Office", width=300)
        route_user = ft.TextField(label="Assigned User", width=300)
        route_remarks = ft.TextField(label="Remarks", multiline=True, min_lines=3, max_lines=5, width=300)
        route_value = ft.Dropdown(label="Route", width=200, options=[ft.dropdown.Option("Routing"), ft.dropdown.Option("Forward"), ft.dropdown.Option("Review")], value="Routing")
        route_dialog = ft.AlertDialog(
            title=ft.Text("Route Document"),
            content=ft.Column([route_destination, route_user, route_remarks, route_value], spacing=10),
            actions=[ft.TextButton("Cancel", on_click=lambda _: close_route_dialog()), ft.Button("Route", on_click=lambda _: submit_route(doc, route_destination, route_user, route_remarks, route_value))],
        )
        def close_route_dialog():
            route_dialog.open = False
            page.update()
        def submit_route(document, destination_field, user_field, remarks_field, route_field):
            payload = {
                "destination_office": (destination_field.value or "").strip(),
                "assigned_user": (user_field.value or "").strip(),
                "remarks": (remarks_field.value or "").strip(),
                "route": (route_field.value or "Routing").strip(),
                "status": "In Routing",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M"),
            }
            try:
                response = requests.post(f"{BACKEND_URL}/documents/{document.get('id')}/route", json=payload, verify=False, timeout=10)
                if response.status_code != 200:
                    raise Exception(response.text)
                load_documents_table()
                close_route_dialog()
                show_document_notice("Document routed successfully.")
            except Exception as exc:
                show_document_notice(f"Routing failed: {exc}")
        page.overlay.append(route_dialog)
        route_dialog.open = True
        page.update()

    def show_document_details(doc):
        try:
            response = requests.get(f"{BACKEND_URL}/documents/{doc.get('id')}", verify=False, timeout=10)
            if response.status_code == 200:
                doc = normalize_document(response.json())
            else:
                raise Exception(response.text)
        except Exception as exc:
            show_document_notice(f"Unable to load document details: {exc}")
            return

        qr_image = ft.Image(width=220, height=220, fit=ft.ImageFit.CONTAIN)
        qr_generation_notice = ft.Text("", size=12, color=ft.Colors.GREEN_700)

        def update_qr_image(value):
            if not value:
                qr_image.src_base64 = ""
                return
            qr_img = qrcode.make(str(value))
            qr_buffer = io.BytesIO()
            qr_img.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)
            qr_image.src_base64 = base64.b64encode(qr_buffer.read()).decode("ascii")

        def generate_document_qr(document):
            try:
                response = requests.post(f"{BACKEND_URL}/documents/{document.get('id')}/qr", verify=False, timeout=10)
                if response.status_code != 200:
                    raise Exception(response.text)
                updated = normalize_document(response.json())
                document.update(updated)
                qr_value = document.get("qr_code_value") or document.get("tracking_number") or f"DOC-{document.get('id')}"
                update_qr_image(qr_value)
                qr_generation_notice.value = "QR generated successfully."
                page.update()
            except Exception as exc:
                qr_generation_notice.value = f"QR generation failed: {exc}"
                page.update()

        update_qr_image(doc.get("qr_code_value") or doc.get("tracking_number") or f"DOC-{doc.get('id')}")
        status_color, status_bg = get_document_status_style(doc.get("status", "Pending"))
        details_content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color=ft.Colors.BLUE_700, size=26),
                        ft.Column(
                            [
                                ft.Text(doc.get("tracking_number", doc.get("id", "-")), size=13, weight=ft.FontWeight.BOLD),
                                ft.Text(doc.get("title", "-"), size=16, weight=ft.FontWeight.BOLD),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Container(
                            content=ft.Text(doc.get("status", "Pending"), size=12, weight=ft.FontWeight.BOLD, color=status_color),
                            bgcolor=status_bg,
                            padding=8,
                            border_radius=14,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(height=1),
                ft.Text(doc.get("description", "No description provided."), size=13, color=ft.Colors.BLUE_GREY_700),
                ft.Row(
                    [
                        ft.Column([ft.Text("Document Type", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("document_type", "-"), size=13)], spacing=2, expand=True),
                        ft.Column([ft.Text("Category", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("category", "-"), size=13)], spacing=2, expand=True),
                    ],
                    spacing=16,
                ),
                ft.Row(
                    [
                        ft.Column([ft.Text("Originating Office", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("originating_office", "-"), size=13)], spacing=2, expand=True),
                        ft.Column([ft.Text("Current Office", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("current_office", "-"), size=13)], spacing=2, expand=True),
                    ],
                    spacing=16,
                ),
                ft.Row(
                    [
                        ft.Column([ft.Text("Assigned User", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("assigned_to", "-"), size=13)], spacing=2, expand=True),
                        ft.Column([ft.Text("Priority", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("priority", "-"), size=13)], spacing=2, expand=True),
                    ],
                    spacing=16,
                ),
                ft.Row(
                    [
                        ft.Column([ft.Text("QR Code", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("qr_code_value", "-"), size=13)], spacing=2, expand=True),
                    ],
                    spacing=16,
                ),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Generate QR", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.ElevatedButton(
                                    "Generate QR",
                                    icon=ft.Icons.QR_CODE_2,
                                    on_click=lambda _: generate_document_qr(doc),
                                ),
                                qr_generation_notice,
                            ],
                            spacing=6,
                            width=220,
                        ),
                        ft.Column(
                            [
                                ft.Text("Generated QR", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Container(
                                    content=qr_image,
                                    width=220,
                                    height=220,
                                    alignment=ft.alignment.center,
                                    bgcolor=ft.Colors.WHITE,
                                    border_radius=14,
                                    padding=8,
                                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                                ),
                            ],
                            spacing=6,
                            expand=True,
                        ),
                    ],
                    spacing=16,
                ),
                ft.Row(
                    [
                        ft.Column([ft.Text("Author", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("author", "-"), size=13)], spacing=2, expand=True),
                        ft.Column([ft.Text("Session", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("session", "-"), size=13)], spacing=2, expand=True),
                    ],
                    spacing=16,
                ),
                ft.Row(
                    [
                        ft.Column([ft.Text("Date Registered", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("date_registered", doc.get("date_received", "-")), size=13)], spacing=2, expand=True),
                        ft.Column([ft.Text("Created By", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("created_by", "-"), size=13)], spacing=2, expand=True),
                    ],
                    spacing=16,
                ),
                ft.Row(
                    [
                        ft.Column([ft.Text("Attachment", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("attachment_name", "-"), size=13)], spacing=2, expand=True),
                        ft.Column([ft.Text("Updated Date", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(doc.get("last_updated", "-"), size=13)], spacing=2, expand=True),
                    ],
                    spacing=16,
                ),
                # QR preview removed for routing-history-only view
                ft.Text("Routing History", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_800),
                ft.Column(
                    [
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(item.get("route", item.get("action", "Action")), size=12, weight=ft.FontWeight.BOLD),
                                    ft.Text(f"{item.get('date', '-')} {item.get('time', '-')}", size=12, color=ft.Colors.BLUE_GREY_600),
                                    ft.Text(f"From: {item.get('from', '-')}", size=12, color=ft.Colors.BLUE_GREY_600),
                                    ft.Text(f"To: {item.get('to', '-')}", size=12, color=ft.Colors.BLUE_GREY_600),
                                    ft.Text(f"User: {item.get('user', '-')}", size=12, color=ft.Colors.BLUE_GREY_600),
                                    ft.Text(f"Remarks: {item.get('remarks', '-')}", size=12, color=ft.Colors.BLUE_GREY_600),
                                    ft.Text(f"Status: {item.get('status', '-')}", size=12, color=ft.Colors.BLUE_GREY_600),
                                ],
                                spacing=3,
                            ),
                            padding=10,
                            bgcolor=ft.Colors.BLUE_GREY_50,
                            border_radius=14,
                        )
                        for item in sorted(doc.get("routing_history", []), key=lambda item: item.get("date", "") + item.get("time", ""), reverse=True)
                    ],
                    spacing=8,
                ),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )
        documents_details_dialog.content = ft.Container(content=details_content, padding=8, width=540)
        documents_details_dialog.open = True
        page.update()

    # QR generation/print functionality removed from frontend.

    def build_document_summary_cards():
        total_documents = len(documents_data)
        pending_count = sum(1 for doc in documents_data if (doc.get("status") or "").lower() == "pending")
        routing_count = sum(1 for doc in documents_data if (doc.get("status") or "").lower() in {"in routing", "routed"})
        completed_count = sum(1 for doc in documents_data if (doc.get("status") or "").lower() in {"approved", "completed"})
        archived_count = sum(1 for doc in documents_data if (doc.get("status") or "").lower() == "archived")
        summary_items = [
            {"title": "Total Documents", "value": str(total_documents), "detail": "Tracked records", "icon": ft.Icons.DESCRIPTION_OUTLINED, "accent": ft.Colors.BLUE_700},
            {"title": "Pending", "value": str(pending_count), "detail": "Awaiting attention", "icon": ft.Icons.HOURGLASS_EMPTY_OUTLINED, "accent": ft.Colors.ORANGE_700},
            {"title": "In Routing", "value": str(routing_count), "detail": "Currently moving", "icon": ft.Icons.SYNC_ALT_OUTLINED, "accent": ft.Colors.BLUE_700},
            {"title": "Completed", "value": str(completed_count), "detail": "Finalized items", "icon": ft.Icons.CHECK_CIRCLE_OUTLINED, "accent": ft.Colors.GREEN_700},
            {"title": "Archived", "value": str(archived_count), "detail": "Stored for reference", "icon": ft.Icons.ARCHIVE_OUTLINED, "accent": ft.Colors.BLUE_GREY_700},
        ]
        cards = []
        for item in summary_items:
            cards.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row([ft.Icon(item["icon"], color=item["accent"], size=22), ft.Text(item["title"], size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700)], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.Text(item["value"], size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                            ft.Text(item["detail"], size=12, color=ft.Colors.BLUE_GREY_600),
                        ],
                        spacing=6,
                    ),
                    padding=16,
                    bgcolor=ft.Colors.WHITE,
                    border_radius=18,
                    width=190,
                )
            )
        return cards

    def get_visible_documents():
        return documents_data

    def get_visible_archived_documents():
        return archived_documents_data

    def format_frontend_date(value):
        if not value:
            return "-"
        if isinstance(value, datetime):
            dt = value
        else:
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return str(value)
        return dt.strftime("%m/%d/%y")

    def normalize_document(doc):
        return {
            "id": doc.get("id"),
            "tracking_number": doc.get("tracking_number") or doc.get("tracking_no") or "-",
            "title": doc.get("title") or "-",
            "description": doc.get("description") or "",
            "document_type": doc.get("document_type") or doc.get("type") or "-",
            "category": doc.get("category") or "-",
            "originating_office": doc.get("originating_office") or "-",
            "current_office": doc.get("current_office") or "-",
            "assigned_to": doc.get("assigned_to") or "-",
            "status": doc.get("status") or "Pending",
            "priority": doc.get("priority") or "Medium",
            "date_received": doc.get("created_at") or doc.get("date_received") or "-",
            "last_updated": doc.get("updated_at") or doc.get("last_updated") or doc.get("created_at") or "-",
            "created_by": doc.get("created_by") or "-",
            "author": doc.get("author") or "-",
            "session": doc.get("session") or "-",
            "date_registered": doc.get("date_registered") or doc.get("created_at") or "-",
            "attachment_name": doc.get("attachment_name") or "-",
            "remarks": doc.get("remarks") or "",
            "attachments": doc.get("attachments") or [],
            "routing_history": doc.get("routing_history") or [],
            "archived": bool(doc.get("archived", False)),
        }

    def create_document_record(payload):
        nonlocal documents_form_attachment_file, documents_form_attachment_file_name, documents_form_title_auto_generated
        try:
            # If a file has been selected in the form, send multipart/form-data
            if documents_form_attachment_file is not None:
                files = {
                    "file": (
                        documents_form_attachment_file_name,
                        io.BytesIO(documents_form_attachment_file),
                        mimetypes.guess_type(documents_form_attachment_file_name)[0] or "application/octet-stream",
                    )
                }
                # include form fields as data
                data = {k: (v if v is not None else "") for k, v in payload.items()}
                response = requests.post(f"{BACKEND_URL}/documents", data=data, files=files, headers=get_admin_headers(), verify=False, timeout=30)
            else:
                # No file: send JSON metadata-only create
                response = requests.post(f"{BACKEND_URL}/documents", json=payload, headers=get_admin_headers(), verify=False, timeout=10)
            if response.status_code not in {200, 201}:
                raise Exception(response.text)
            # reset attachment state
            documents_form_attachment_display.value = "No file selected"
            # clear in-memory file
            documents_form_attachment_file = None
            documents_form_attachment_file_name = ""
            documents_form_title_auto_generated = False
            load_documents_table()
            show_document_notice("Document created successfully.")
        except Exception as exc:
            show_document_notice(f"Create failed: {exc}")

    def update_document_record(document_id, payload):
        try:
            response = requests.put(f"{BACKEND_URL}/documents/{document_id}", json=payload, verify=False, timeout=10)
            if response.status_code != 200:
                raise Exception(response.text)
            load_documents_table()
            show_document_notice("Document updated successfully.")
        except Exception as exc:
            show_document_notice(f"Update failed: {exc}")

    def delete_document_record(document_id):
        try:
            response = requests.delete(f"{BACKEND_URL}/documents/{document_id}", verify=False, timeout=10)
            if response.status_code != 200:
                raise Exception(response.text)
            load_documents_table()
            show_document_notice("Document archived successfully.")
        except Exception as exc:
            show_document_notice(f"Delete failed: {exc}")

    def apply_document_search_to_current_view():
        visible_documents = get_visible_documents()
        if documents_sort_filter.value == "Oldest":
            visible_documents = sorted(visible_documents, key=lambda doc: str(doc.get("date_received", "")), reverse=False)
        elif documents_sort_filter.value == "Title":
            visible_documents = sorted(visible_documents, key=lambda doc: str(doc.get("title", "")).lower(), reverse=False)
        else:
            visible_documents = sorted(visible_documents, key=lambda doc: str(doc.get("date_received", "")), reverse=True)

        # Backend already filters and searches the documents dataset.
        rendered_documents = visible_documents[:10]
        rows = []
        for doc in rendered_documents:
            status = doc.get("status", "Pending")
            status_color, status_bg = get_document_status_style(status)
            document_title = str(doc.get("title", "-") or "-")
            title_cell = ft.DataCell(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                document_title,
                                size=13,
                                no_wrap=True,
                                overflow=ft.TextOverflow.CLIP,
                            )
                        ],
                        spacing=0,
                        scroll=ft.ScrollMode.AUTO,
                        width=280,
                    ),
                    width=280,
                    height=40,
                    padding=ft.Padding(left=4, top=0, right=4, bottom=0),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    alignment=ft.Alignment.CENTER_LEFT,
                )
            )
            actions = [
                ft.PopupMenuItem(content=ft.Text("View Details"), on_click=lambda _, d=doc: show_document_details(d)),
                ft.PopupMenuItem(content=ft.Text("Edit"), on_click=lambda _, d=doc: open_document_form(d)),
                ft.PopupMenuItem(content=ft.Text("Route Document"), on_click=lambda _, d=doc: open_route_dialog(d)),
                ft.PopupMenuItem(content=ft.Text("View Routing History"), on_click=lambda _, d=doc: show_document_details(d)),
                # QR actions removed from row popup to streamline routing-history view
                ft.PopupMenuItem(content=ft.Text("Download"), on_click=lambda _: show_document_notice("Download action preview enabled.")),
                ft.PopupMenuItem(content=ft.Text("Archive Document"), on_click=lambda _, d=doc: confirm_delete_document(d)),
            ]
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(
                            ft.Container(
                                content=ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, tooltip="Document actions", items=actions),
                                width=90,
                                alignment=ft.Alignment.CENTER,
                            )
                        ),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("tracking_number", doc.get("id", "-")), size=13), width=120, alignment=ft.Alignment.CENTER_LEFT)),
                        title_cell,
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("document_type", "-"), size=13), width=120, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("category", "-"), size=13), width=100, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("originating_office", "-"), size=13, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True), width=150, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("current_office", "-"), size=13, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True), width=140, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("assigned_to", "-"), size=13, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True), width=110, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(status, size=12, color=status_color),
                                bgcolor=status_bg,
                                padding=6,
                                border_radius=12,
                                alignment=ft.Alignment.CENTER,
                                width=120,
                            )
                        ),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("priority", "-"), size=13), width=80, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(format_frontend_date(doc.get("date_received", "-")), size=13), width=100, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(format_frontend_date(doc.get("last_updated", "-")), size=13), width=100, alignment=ft.Alignment.CENTER_LEFT)),
                    ],
                )
            )

        documents_table.rows = rows
        documents_empty_state.visible = len(rows) == 0
        update_document_result_indicator(visible_documents, visible_count=len(rows))
        page.update()

    def build_document_rows(documents, include_archive_action=True):
        rows = []
        for doc in documents:
            status = doc.get("status", "Pending")
            status_color, status_bg = get_document_status_style(status)
            document_title = str(doc.get("title", "-") or "-")
            title_cell = ft.DataCell(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                document_title,
                                size=13,
                                no_wrap=True,
                                overflow=ft.TextOverflow.CLIP,
                            )
                        ],
                        spacing=0,
                        scroll=ft.ScrollMode.AUTO,
                        width=280,
                    ),
                    width=280,
                    height=40,
                    padding=ft.Padding(left=4, top=0, right=4, bottom=0),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    alignment=ft.Alignment.CENTER_LEFT,
                )
            )
            if include_archive_action:
                actions = [
                    ft.PopupMenuItem(content=ft.Text("View Details"), on_click=lambda _, d=doc: show_document_details(d)),
                    ft.PopupMenuItem(content=ft.Text("Edit"), on_click=lambda _, d=doc: open_document_form(d)),
                    ft.PopupMenuItem(content=ft.Text("Route Document"), on_click=lambda _, d=doc: open_route_dialog(d)),
                    ft.PopupMenuItem(content=ft.Text("View Routing History"), on_click=lambda _, d=doc: show_document_details(d)),
                    ft.PopupMenuItem(content=ft.Text("Archive Document"), on_click=lambda _, d=doc: confirm_delete_document(d)),
                ]
            else:
                actions = [
                    ft.PopupMenuItem(content=ft.Text("View Details"), on_click=lambda _, d=doc: show_document_details(d)),
                    ft.PopupMenuItem(content=ft.Text("Restore Document"), on_click=lambda _, d=doc: show_document_notice("Restore not implemented.")),
                    ft.PopupMenuItem(content=ft.Text("Delete Document"), on_click=lambda _, d=doc: show_document_notice("Permanent delete not implemented.")),
                ]
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(
                            ft.Container(
                                content=ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, tooltip="Document actions", items=actions),
                                width=90,
                                alignment=ft.Alignment.CENTER,
                            )
                        ),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("tracking_number", doc.get("id", "-")), size=13), width=120, alignment=ft.Alignment.CENTER_LEFT)),
                        title_cell,
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("document_type", "-"), size=13), width=120, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("category", "-"), size=13), width=100, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("originating_office", "-"), size=13, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True), width=150, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("current_office", "-"), size=13, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True), width=140, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("assigned_to", "-"), size=13, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True), width=110, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(status, size=12, color=status_color),
                                bgcolor=status_bg,
                                padding=6,
                                border_radius=12,
                                alignment=ft.Alignment.CENTER,
                                width=120,
                            )
                        ),
                        ft.DataCell(ft.Container(content=ft.Text(doc.get("priority", "-"), size=13), width=80, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(format_frontend_date(doc.get("date_received", "-")), size=13), width=100, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(format_frontend_date(doc.get("last_updated", "-")), size=13), width=100, alignment=ft.Alignment.CENTER_LEFT)),
                    ],
                )
            )
        return rows

    def apply_archived_document_search_to_current_view():
        visible_documents = get_visible_archived_documents()
        visible_documents = apply_document_search(visible_documents, archived_documents_search_field.value)

        if documents_sort_filter.value == "Oldest":
            visible_documents = sorted(visible_documents, key=lambda doc: str(doc.get("date_received", "")), reverse=False)
        elif documents_sort_filter.value == "Title":
            visible_documents = sorted(visible_documents, key=lambda doc: str(doc.get("title", "")).lower(), reverse=False)
        else:
            visible_documents = sorted(visible_documents, key=lambda doc: str(doc.get("date_received", "")), reverse=True)

        rows = build_document_rows(visible_documents, include_archive_action=False)
        archived_documents_table.rows = rows
        archived_documents_empty_state.visible = len(rows) == 0
        update_document_result_indicator(visible_documents, visible_count=len(rows))
        page.update()

    def load_archived_documents_table():
        try:
            params = {"archived": "true"}
            if archived_documents_search_field.value:
                params["search"] = archived_documents_search_field.value
            if archived_documents_filter_status.value and archived_documents_filter_status.value != "All":
                params["status"] = archived_documents_filter_status.value
            if archived_documents_filter_type.value and archived_documents_filter_type.value != "All":
                params["document_type"] = archived_documents_filter_type.value
            if archived_documents_filter_category.value and archived_documents_filter_category.value != "All":
                params["category"] = archived_documents_filter_category.value
            if archived_documents_filter_office.value and archived_documents_filter_office.value != "All":
                params["current_office"] = archived_documents_filter_office.value
            if archived_documents_year_filter.value:
                params["year"] = archived_documents_year_filter.value
            if archived_documents_filter_start_date.value:
                params["start_date"] = archived_documents_filter_start_date.value
            if archived_documents_filter_end_date.value:
                params["end_date"] = archived_documents_filter_end_date.value
            response = requests.get(f"{BACKEND_URL}/documents", params=params, verify=False, timeout=10)
            if response.status_code != 200:
                raise Exception(response.text)
            payload = response.json() if response.content else []
            archived_documents_data[:] = [normalize_document(doc) for doc in payload]
        except Exception as exc:
            archived_documents_data[:] = []
            archived_documents_table.rows = []
            archived_documents_empty_state.visible = True
            archived_documents_notice.value = f"Unable to load archived documents: {exc}"
            page.update()
            return

        apply_archived_document_search_to_current_view()

    def reset_archived_document_filters():
        archived_documents_search_field.value = ""
        archived_documents_filter_status.value = "All"
        archived_documents_filter_type.value = "All"
        archived_documents_filter_category.value = "All"
        archived_documents_filter_office.value = "All"
        archived_documents_sort_filter.value = "Newest"
        archived_documents_year_filter.value = ""
        archived_documents_filter_start_date.value = ""
        archived_documents_filter_end_date.value = ""
        load_archived_documents_table()
        page.update()

    def build_archived_documents_view():
        load_archived_documents_table()

        header_card = surface_card(
            ft.Column(
                [
                    section_header(
                        "Archived Documents",
                        "View records that have been archived and stored for reference.",
                        ft.Icons.ARCHIVE_OUTLINED,
                        ft.Colors.BLUE_GREY_700,
                    ),
                    ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                    ft.Row(
                        [
                            archived_documents_search_field,
                            archived_documents_refresh_button,
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            archived_documents_filter_status,
                            archived_documents_filter_category,
                            archived_documents_filter_type,
                            archived_documents_year_filter,
                            archived_documents_filter_office,
                            archived_documents_sort_filter,
                            archived_documents_filter_start_date,
                            archived_documents_filter_end_date,
                            archived_documents_apply_button,
                        ],
                        spacing=12,
                        run_spacing=12,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=14,
            ),
            padding=18,
            expand=False,
        )

        table_card = surface_card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.ARCHIVE_OUTLINED, size=20, color=ft.Colors.BLUE_GREY_700),
                                    ft.Text("Archived Document Records", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(f"{len(archived_documents_data)} archived documents", size=12, color=ft.Colors.BLUE_GREY_600),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                    archived_documents_table,
                    archived_documents_empty_state,
                ],
                spacing=10,
                width=1600,
                horizontal_alignment=ft.CrossAxisAlignment.START,
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=14,
            expand=False,
        )

        return ft.Column(
            controls=[
                header_card,
                ft.Container(content=archived_documents_notice, padding=ft.Padding(left=4, right=4, top=4, bottom=0)),
                table_card,
            ],
            spacing=10,
            expand=False,
            tight=True,
        )

    def reset_document_filters():
        try:
            params = {}
            if documents_search_field.value:
                params["search"] = documents_search_field.value
            if documents_status_filter.value and documents_status_filter.value != "All":
                params["status"] = documents_status_filter.value
            if documents_type_filter.value and documents_type_filter.value != "All":
                params["document_type"] = documents_type_filter.value
            if documents_category_filter.value and documents_category_filter.value != "All":
                params["category"] = documents_category_filter.value
            if documents_assigned_filter.value and documents_assigned_filter.value != "All":
                params["current_office"] = documents_assigned_filter.value
            if documents_year_filter.value:
                params["year"] = documents_year_filter.value
            if documents_filter_start_date.value:
                params["start_date"] = documents_filter_start_date.value
            if documents_filter_end_date.value:
                params["end_date"] = documents_filter_end_date.value
            response = requests.get(f"{BACKEND_URL}/documents", params=params, verify=False, timeout=10)
            if response.status_code != 200:
                raise Exception(response.text)
            payload = response.json() if response.content else []
            documents_data[:] = [normalize_document(doc) for doc in payload]
        except Exception as exc:
            documents_data[:] = []
            documents_table.rows = []
            documents_empty_state.visible = True
            documents_notice.value = f"Unable to load documents: {exc}"
            page.update()
            return

        apply_document_search_to_current_view()

    def load_documents_table():
        try:
            params = {}
            if documents_search_field.value:
                params["search"] = documents_search_field.value
            if documents_status_filter.value and documents_status_filter.value != "All":
                params["status"] = documents_status_filter.value
            if documents_type_filter.value and documents_type_filter.value != "All":
                params["document_type"] = documents_type_filter.value
            if documents_category_filter.value and documents_category_filter.value != "All":
                params["category"] = documents_category_filter.value
            if documents_assigned_filter.value and documents_assigned_filter.value != "All":
                params["current_office"] = documents_assigned_filter.value
            if documents_year_filter.value:
                params["year"] = documents_year_filter.value
            if documents_filter_start_date.value:
                params["start_date"] = documents_filter_start_date.value
            if documents_filter_end_date.value:
                params["end_date"] = documents_filter_end_date.value
            response = requests.get(f"{BACKEND_URL}/documents", params=params, verify=False, timeout=10)
            if response.status_code != 200:
                raise Exception(response.text)
            payload = response.json() if response.content else []
            documents_data[:] = [normalize_document(doc) for doc in payload]
        except Exception as exc:
            documents_data[:] = []
            documents_table.rows = []
            documents_empty_state.visible = True
            documents_notice.value = f"Unable to load documents: {exc}"
            page.update()
            return

        apply_document_search_to_current_view()

    def reset_document_filters():
        documents_search_field.value = ""
        documents_status_filter.value = "All"
        documents_type_filter.value = "All"
        documents_category_filter.value = "All"
        documents_assigned_filter.value = "All"
        documents_sort_filter.value = "Newest"
        documents_year_filter.value = ""
        documents_filter_start_date.value = ""
        documents_filter_end_date.value = ""
        load_documents_table()
        page.update()

    def open_documents_view(_=None):
        load_documents_table()
        page.update()

    def documents_view():
        try:
            load_documents_table()
            print("documents_view: building document controls")
            documents_controls = {
                "summary_cards": build_document_summary_cards(),
                "search_field": documents_search_field,
                "status_filter": documents_status_filter,
                "category_filter": documents_category_filter,
                "type_filter": documents_type_filter,
                "year_filter": documents_year_filter,
                "assigned_filter": documents_assigned_filter,
                "register_button": ft.Button("Register Document", icon=ft.Icons.ADD, on_click=lambda _: open_document_form()),
                "refresh_button": ft.Button("Refresh", icon=ft.Icons.REFRESH, on_click=lambda _: reset_document_filters()),
                "qr_monitor_button": ft.OutlinedButton("QR Monitor", icon=ft.Icons.QR_CODE_2, on_click=lambda _: open_qr_monitor()),
                "qr_labels_button": None,
                "export_button": None,
                "print_button": None,
                # Import Documents removed; attachment is part of Register Document workflow
                "import_button": None,
                "filter_button": ft.OutlinedButton("Apply", icon=ft.Icons.FILTER_LIST, on_click=lambda _: load_documents_table()),
                "reset_filter_button": None,
                "sort_filter": documents_sort_filter,
                "start_date_filter": documents_filter_start_date,
                "end_date_filter": documents_filter_end_date,
                "empty_state_button": ft.Button("Register Document", icon=ft.Icons.ADD, on_click=lambda _: open_document_form()),
                "empty_state": documents_empty_state,
            }
            return build_documents_view(
                documents_table,
                documents_notice,
                open_documents_view,
                surface_card,
                section_header,
                documents_controls,
            )
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print("documents_view error:\n", tb)
            return ft.Column([ft.Text("Error building Documents view"), ft.Text(str(e)), ft.Text(tb)])

    def settings_view():
        return ft.Column(
            [
                surface_card(
                    ft.Column(
                        [
                            section_header(
                                "Settings",
                                "System configuration and operational preferences.",
                                ft.Icons.SETTINGS,
                                ft.Colors.BLUE_GREY_700,
                            ),
                            ft.Divider(height=1),
                            ft.Text(
                                "This admin system provides operational monitoring, user management, and audit log visibility.",
                                size=13,
                                color=ft.Colors.BLUE_GREY_600,
                            ),
                            ft.Text(
                                "Update backend deployment or environment settings to adjust service behavior.",
                                size=13,
                                color=ft.Colors.BLUE_GREY_600,
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

    def archived_documents_view():
        return build_archived_documents_view()

    def show_login():
        page.clean()
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER

        username_field = ft.TextField(label="Username", width=300, icon=ft.Icons.PERSON)
        password_field = ft.TextField(label="Password", width=300, password=True, can_reveal_password=True, icon=ft.Icons.LOCK)
        login_error = ft.Text("", size=12, color=ft.Colors.RED_700)

        def attempt_login(_):
            nonlocal current_user, current_user_role
            username = (username_field.value or "").strip()
            password = password_field.value or ""
            login_error.value = ""

            if not username or not password:
                login_error.value = "Please fill out both fields."
                page.update()
                return

            try:
                res = requests.post(f"{BACKEND_URL}/auth/login", params={"username": username, "password": password}, verify=False, timeout=10)
                if res.status_code == 200:
                    payload = res.json()
                    role = (payload.get("role") or "Admin").strip()
                    current_user = payload.get("username")
                    current_user_role = role
                    if role == "Admin":
                        render_shell(page, current_user, logout_user, nav_items, content_view=None)
                    elif role in {"Secretary / Vice Mayor", "Secretary"}:
                        render_shell(page, current_user, logout_user, nav_items, documents_view())
                    else:
                        page.snack_bar = ft.SnackBar(ft.Text("Your account is not approved for access yet."), open=True)
                        page.update()
                else:
                    detail = res.json().get("detail", "Invalid credentials.") if res.headers.get("content-type", "").startswith("application/json") else "Invalid credentials."
                    login_error.value = detail
                    page.update()
            except Exception as ex:
                login_error.value = f"Connection failed: {ex}"
                page.update()

        login_btn = ft.Button("Log In", width=300, on_click=attempt_login, bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE)
        signup_link = ft.TextButton("Don't have an account? Sign Up", on_click=lambda _: show_signup())

        page.add(
            surface_card(
                ft.Column([
                    ft.Container(
                        content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=52, color=ft.Colors.BLUE_800),
                        padding=14,
                        bgcolor=ft.Colors.BLUE_GREY_50,
                        border_radius=20,
                    ),
                    ft.Text("LGU Tolosa - Sangguniang Bayan", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                    ft.Text("Administration System Login", size=14, color=ft.Colors.BLUE_GREY_600),
                    ft.Container(height=4),
                    username_field,
                    password_field,
                    login_error,
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

        reg_first_name = ft.TextField(label="First Name", width=300, icon=ft.Icons.PERSON)
        reg_last_name = ft.TextField(label="Last Name", width=300, icon=ft.Icons.PERSON)
        reg_email = ft.TextField(label="Email", width=300, icon=ft.Icons.EMAIL)
        reg_username = ft.TextField(label="Desired Username", width=300, icon=ft.Icons.PERSON_ADD)
        reg_password = ft.TextField(label="Password", width=300, password=True, can_reveal_password=True, icon=ft.Icons.LOCK_OUTLINE)
        reg_confirm_password = ft.TextField(label="Confirm Password", width=300, password=True, can_reveal_password=True, icon=ft.Icons.LOCK)
        reg_office = ft.TextField(label="Office", width=300, icon=ft.Icons.BUSINESS)
        reg_position = ft.TextField(label="Position", width=300, icon=ft.Icons.WORK)
        reg_notes = ft.TextField(label="Notes", width=300, multiline=True, min_lines=2, max_lines=4, icon=ft.Icons.NOTES)
        signup_error = ft.Text("", size=12, color=ft.Colors.RED_700)

        def attempt_signup(_):
            first_name = (reg_first_name.value or "").strip()
            last_name = (reg_last_name.value or "").strip()
            email = (reg_email.value or "").strip()
            username = (reg_username.value or "").strip()
            password = reg_password.value or ""
            confirm_password = reg_confirm_password.value or ""
            signup_error.value = ""

            if not first_name or not last_name or not email or not username or not password or not confirm_password:
                signup_error.value = "Please fill out all required fields."
                page.update()
                return

            if password != confirm_password:
                signup_error.value = "Passwords do not match."
                page.update()
                return

            if len(password) < 8:
                signup_error.value = "Password must be at least 8 characters."
                page.update()
                return

            if "@" not in email or "." not in email:
                signup_error.value = "Please enter a valid email address."
                page.update()
                return

            payload = {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "username": username,
                "password": password,
                "office": (reg_office.value or "").strip() or None,
                "position": (reg_position.value or "").strip() or None,
                "notes": (reg_notes.value or "").strip() or None,
            }

            try:
                res = requests.post(f"{BACKEND_URL}/registration/requests", json=payload, verify=False, timeout=10)
                if res.status_code == 201:
                    page.clean()
                    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
                    page.vertical_alignment = ft.MainAxisAlignment.CENTER
                    ref = res.json().get("registration_reference", "N/A")
                    page.add(
                        surface_card(
                            ft.Column([
                                ft.Container(
                                    content=ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=52, color=ft.Colors.GREEN_700),
                                    padding=14,
                                    bgcolor=ft.Colors.GREEN_50,
                                    border_radius=20,
                                ),
                                ft.Text("Registration Submitted Successfully", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_800),
                                ft.Text("Reference Number:", size=13, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(f"({ref})", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                                ft.Text("Status:", size=13, color=ft.Colors.BLUE_GREY_600),
                                ft.Text("Pending Administrator Approval", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                                ft.Text("Your registration request has been submitted successfully. Your account cannot log in until it has been reviewed and approved by the System Administrator.", size=13, color=ft.Colors.BLUE_GREY_600, text_align=ft.TextAlign.CENTER),
                                ft.Row([
                                    ft.Button("Return to Login", on_click=lambda _: show_login(), bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE),
                                    ft.OutlinedButton("Register Another Account", on_click=lambda _: show_signup()),
                                ], spacing=12),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                            width=520,
                            padding=36,
                        )
                    )
                    page.update()
                else:
                    detail = res.json().get("detail", "Registration failed.") if res.headers.get("content-type", "").startswith("application/json") else "Registration failed."
                    signup_error.value = detail
                    page.update()
            except Exception as ex:
                signup_error.value = f"Connection failed: {ex}"
                page.update()

        register_btn = ft.Button("Register Account", width=300, on_click=attempt_signup, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)
        back_to_login = ft.TextButton("Already have an account? Log In", on_click=lambda e: show_login())

        page.add(
            surface_card(
                ft.Column([
                    ft.Container(
                        content=ft.Icon(ft.Icons.PERSON_ADD, size=52, color=ft.Colors.GREEN_700),
                        padding=14,
                        bgcolor=ft.Colors.GREEN_50,
                        border_radius=20,
                    ),
                    ft.Text("Create Administrator Account", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_800),
                    ft.Text("Sangguniang Bayan Registry", size=14, color=ft.Colors.BLUE_GREY_600),
                    ft.Container(height=4),
                    reg_first_name,
                    reg_last_name,
                    reg_email,
                    reg_username,
                    reg_password,
                    reg_confirm_password,
                    reg_office,
                    reg_position,
                    reg_notes,
                    signup_error,
                    ft.Container(height=6),
                    register_btn,
                    back_to_login,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                width=520,
                padding=36,
            )
        )
        page.update()

    nav_items = [
        (ft.Icons.DESCRIPTION_OUTLINED, "Documents", lambda: documents_view()),
        (ft.Icons.ARCHIVE_OUTLINED, "Archived Documents", lambda: archived_documents_view()),
        (ft.Icons.GROUP_OUTLINED, "Committees", lambda: committees_view()),
        (ft.Icons.PEOPLE_OUTLINED, "Users & Roles", lambda: users_roles_view()),
        (ft.Icons.HISTORY_OUTLINED, "Audit Logs", lambda: audit_logs_view()),
        (ft.Icons.SETTINGS_OUTLINED, "Settings", lambda: settings_view()),
    ]

    show_login()


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
