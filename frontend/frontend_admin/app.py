import flet as ft
from datetime import date, datetime

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
import ast
import re
import secrets
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import time
import secrets
from flet_core.file_picker import FilePickerUploadFile
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(override=True)

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")
AUTH_TOKEN = os.getenv("BACKEND_AUTH_TOKEN")

if os.getenv("DEV_HTTP", "0").lower() in ("1", "true", "yes"):
    if BACKEND_URL.startswith("https://"):
        BACKEND_URL = BACKEND_URL.replace("https://", "http://", 1)

from frontend.frontend_admin.committees import build_committees_view
from frontend.frontend_admin.documents import build_documents_view
from frontend.frontend_admin.audit_logs import build_audit_logs_view
from frontend.frontend_admin.analytics import build_analytics_view
from frontend.frontend_admin.users_roles import build_users_roles_table, build_users_roles_view, EMPLOYEE_PERMISSION_GROUPS
from frontend.frontend_admin.admin_shell import render_shell


def clear_stale_session_state(state):
    reset = dict(state or {})
    reset["current_user"] = None
    reset["current_user_role"] = None
    reset["current_user_permissions"] = []
    reset["runtime_token"] = None
    reset["refresh_token"] = None
    return reset


def main(page: ft.Page):
    page.title = "LGU Tolosa — Legislative Document Tracking Management System"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.WHITE
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.padding = 8

    current_user = None
    current_user_role = None
    current_user_permissions = []
    runtime_token = None
    refresh_token = None

    def has_permission(permission):
        normalized_role = (current_user_role or "").strip().lower()
        if normalized_role == "super administrator":
            return True
        raw_permissions = current_user_permissions or []
        if isinstance(raw_permissions, str):
            try:
                raw_permissions = json.loads(raw_permissions)
            except (TypeError, ValueError):
                try:
                    raw_permissions = ast.literal_eval(raw_permissions)
                except (SyntaxError, ValueError):
                    raw_permissions = [raw_permissions]
        if isinstance(raw_permissions, dict):
            raw_permissions = raw_permissions.keys()
        normalized_permissions = {
            str(item).strip().lower().replace(" ", "_")
            for item in raw_permissions
        }
        return permission.strip().lower().replace(" ", "_") in normalized_permissions or "*" in normalized_permissions

    def is_employee():
        return (current_user_role or "").strip().lower() == "employee"

    def save_session_state():
        try:
            if hasattr(page, "client_storage"):
                page.client_storage.set("sb_access_token", runtime_token or "")
                page.client_storage.set("sb_refresh_token", refresh_token or "")
                page.client_storage.set("sb_current_user", current_user or "")
                page.client_storage.set("sb_current_user_role", current_user_role or "")
                page.client_storage.set("sb_current_user_permissions", json.dumps(current_user_permissions or []))
        except Exception:
            pass

    def clear_session_state():
        try:
            if hasattr(page, "client_storage"):
                page.client_storage.remove("sb_access_token")
                page.client_storage.remove("sb_refresh_token")
                page.client_storage.remove("sb_current_user")
                page.client_storage.remove("sb_current_user_role")
                page.client_storage.remove("sb_current_user_permissions")
        except Exception:
            pass

    def refresh_runtime_token_if_needed(force=False):
        nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
        if force:
            should_refresh = True
        else:
            should_refresh = False
        if not runtime_token or not refresh_token:
            return
        try:
            token_parts = runtime_token.split('.')
            if len(token_parts) == 3:
                payload_part = token_parts[1]
                payload_part += '=' * (-len(payload_part) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_part))
                exp = payload.get('exp')
                if exp is not None and int(exp) - int(time.time()) > 300 and not should_refresh:
                    return
        except Exception:
            pass

        try:
            resp = requests.post(
                f"{BACKEND_URL}/auth/refresh",
                data={"refresh_token": refresh_token},
                verify=False,
                timeout=10,
            )
            if resp.status_code == 200:
                body = resp.json()
                runtime_token = body.get("access_token") or runtime_token
                refresh_token = body.get("refresh_token") or refresh_token
                if body.get("role"):
                    current_user_role = body["role"]
                if body.get("permissions") is not None:
                    current_user_permissions = body["permissions"]
                save_session_state()
                return

            reset = clear_stale_session_state({
                "current_user": current_user,
                "current_user_role": current_user_role,
                "current_user_permissions": current_user_permissions,
                "runtime_token": runtime_token,
                "refresh_token": refresh_token,
            })
            current_user = reset["current_user"]
            current_user_role = reset["current_user_role"]
            current_user_permissions = reset["current_user_permissions"]
            runtime_token = reset["runtime_token"]
            refresh_token = reset["refresh_token"]
            clear_session_state()
            show_login()
            return
        except Exception:
            reset = clear_stale_session_state({
                "current_user": current_user,
                "current_user_role": current_user_role,
                "current_user_permissions": current_user_permissions,
                "runtime_token": runtime_token,
                "refresh_token": refresh_token,
            })
            current_user = reset["current_user"]
            current_user_role = reset["current_user_role"]
            current_user_permissions = reset["current_user_permissions"]
            runtime_token = reset["runtime_token"]
            refresh_token = reset["refresh_token"]
            clear_session_state()
            show_login()
            return

    def get_admin_headers():
        refresh_runtime_token_if_needed()
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
        title=ft.Text("LGU Tolosa Login"),
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
        nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
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
                refresh_token = body.get("refresh_token")
                current_user = body.get("username") or current_user
                current_user_role = body.get("role") or current_user_role
                current_user_permissions = body.get("permissions") or []
                save_session_state()
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
            ft.DataColumn(ft.Text("Date & Time", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("User", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Action", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Module", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Details", weight=ft.FontWeight.BOLD, size=12)),
            ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD, size=12)),
        ],
        rows=[],
        width=1400,
        column_spacing=18,
        heading_row_height=34,
        data_row_min_height=36,
        data_row_max_height=42,
        border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
        border_radius=12,
    )

    AUDIT_LOGS_SAMPLE = [
        {"created_at": "2026-09-02T02:22:00+00:00", "actor": "admin", "action": "USER_LOGIN", "target_type": "Auth", "details": "User logged in successfully.", "status": "Success"},
        {"created_at": "2026-09-02T05:13:58+00:00", "actor": "admin", "action": "DOCUMENT_REJECT", "target_type": "Documents", "details": "Document rejected because required validation fields were missing.", "status": "Failed"},
        {"created_at": "2026-09-01T09:15:00+00:00", "actor": "joel", "action": "DOCUMENT_CREATE", "target_type": "Documents", "details": "Document registered in the system.", "status": "Success"},
        {"created_at": "2026-09-01T11:42:00+00:00", "actor": "beth", "action": "DOCUMENT_UPDATE", "target_type": "Documents", "details": "Document metadata updated.", "status": "Success"},
        {"created_at": "2026-09-01T15:26:00+00:00", "actor": "rhea", "action": "DOCUMENT_APPROVE", "target_type": "Documents", "details": "Document approved by administrative review.", "status": "Success"},
        {"created_at": "2026-08-31T08:10:00+00:00", "actor": "joel", "action": "ROLE_ASSIGN", "target_type": "Users & Roles", "details": "Role assigned to user account.", "status": "Success"},
        {"created_at": "2026-08-31T10:35:00+00:00", "actor": "beth", "action": "REPORT_EXPORT", "target_type": "Analytics", "details": "Analytics report exported successfully.", "status": "Success"},
        {"created_at": "2026-08-30T17:45:00+00:00", "actor": "admin", "action": "USER_LOGIN", "target_type": "Auth", "details": "Logged in successfully after password reset.", "status": "Success"},
        {"created_at": "2026-08-29T09:20:00+00:00", "actor": "marla", "action": "USER_LOGOUT", "target_type": "Auth", "details": "Session closed successfully.", "status": "Success"},
        {"created_at": "2026-08-28T14:11:00+00:00", "actor": "beth", "action": "DOCUMENT_UPDATE", "target_type": "Documents", "details": "Document status changed to returned.", "status": "Success"},
        {"created_at": "2026-08-27T07:34:00+00:00", "actor": "admin", "action": "USER_LOGIN", "target_type": "Auth", "details": "Failed login attempt detected and blocked.", "status": "Failed"},
        {"created_at": "2026-08-26T18:22:00+00:00", "actor": "rhea", "action": "DOCUMENT_REJECT", "target_type": "Documents", "details": "Document rejected due to incomplete attachments.", "status": "Failed"},
        {"created_at": "2026-08-24T12:50:00+00:00", "actor": "joel", "action": "ROLE_ASSIGN", "target_type": "Users & Roles", "details": "Temporary access granted for committee review.", "status": "Success"},
        {"created_at": "2026-08-22T16:12:00+00:00", "actor": "marla", "action": "REPORT_EXPORT", "target_type": "Analytics", "details": "Summary export generated for leadership review.", "status": "Success"},
        {"created_at": "2026-08-20T10:08:00+00:00", "actor": "admin", "action": "DOCUMENT_ARCHIVE", "target_type": "Documents", "details": "Document archived and moved to closed records.", "status": "Success"},
    ]

    def save_committees_to_file(committees):
        # UI preview only: no persistent save is required for the current design.
        pass

    delete_dialog = ft.AlertDialog(title=ft.Text("Confirm Action"), content=ft.Text(""), actions=[])
    page.overlay.append(delete_dialog)

    def surface_card(content, width=None, padding=24, expand=False):
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        card_bg = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        border_color = ft.Colors.BLUE_GREY_700 if is_dark else ft.Colors.BLUE_GREY_100
        return ft.Container(
            content=content,
            width=width,
            expand=expand,
            padding=padding,
            bgcolor=card_bg,
            border_radius=18,
            border=ft.border.all(1, border_color),
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK) if not is_dark else ft.Colors.with_opacity(0.24, ft.Colors.BLACK), offset=ft.Offset(0, 2), spread_radius=0),
        )

    def section_header(title, subtitle, icon, accent_color):
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        text_color = ft.Colors.BLUE_GREY_100 if is_dark else ft.Colors.BLUE_GREY_900
        muted_color = ft.Colors.BLUE_GREY_300 if is_dark else ft.Colors.BLUE_GREY_600
        badge_bg = ft.Colors.with_opacity(0.12, accent_color)
        return ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, color=accent_color, size=24),
                    padding=10,
                    bgcolor=badge_bg,
                    border_radius=14,
                ),
                ft.Column(
                    [
                        ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=text_color),
                        ft.Text(subtitle, size=13, color=muted_color),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

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

    audit_summary_cards = ft.Row([], spacing=12, wrap=True)
    audit_filter_bar = ft.Row([], spacing=10, wrap=True)
    audit_action_bar = ft.Row([], spacing=8, wrap=True)
    audit_pagination_bar = ft.Row([], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    audit_details_dialog = ft.AlertDialog(
        title=ft.Text("Audit Log Details"),
        content=ft.Column([], spacing=8, tight=True),
        actions=[ft.TextButton("Close", on_click=lambda _: close_audit_details())],
    )

    def close_audit_details():
        audit_details_dialog.open = False
        try:
            page.update()
        except Exception:
            pass

    def format_audit_datetime(value):
        if not value:
            return "—"
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(value)

    def get_audit_status_style(status):
        normalized = (status or "Success").strip().lower()
        if normalized == "failed":
            return ft.Colors.RED_700, ft.Colors.RED_50
        return ft.Colors.GREEN_700, ft.Colors.GREEN_50

    def render_status_badge(status):
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        color, background = get_audit_status_style(status)
        text_color = ft.Colors.RED_100 if is_dark and status == "Failed" else ft.Colors.GREEN_100 if is_dark and status != "Failed" else color
        return ft.Container(
            content=ft.Text(str(status or "Success"), size=11, weight=ft.FontWeight.W_500, color=text_color),
            padding=ft.Padding(6, 4, 6, 4),
            bgcolor=ft.Colors.with_opacity(0.12, color) if not is_dark else ft.Colors.with_opacity(0.2, color),
            border_radius=8,
        )

    audit_filter_state = {
        "page": 1,
        "page_count": 1,
        "limit": 10,
        "search": "",
        "date_range": "last_30_days",
        "user": "all",
        "module": "all",
        "action": "all",
        "status": "all",
    }

    def normalize_audit_filter_value(value, default="all"):
        if value is None:
            return default
        text = str(value).strip()
        if not text or text in {"all", "All Users", "All Modules", "All Actions", "All Status"}:
            return default
        return text

    def build_audit_results_label(total_items, current_page, page_size):
        if total_items <= 0:
            return ft.Text("Showing 0–0 of 0 audit logs", size=12, color=ft.Colors.BLUE_GREY_600)
        start = min((current_page - 1) * page_size + 1, total_items)
        end = min(current_page * page_size, total_items)
        return ft.Text(f"Showing {start}–{end} of {total_items} audit logs", size=12, color=ft.Colors.BLUE_GREY_600)

    audit_search_field = ft.TextField(label="Search", hint_text="Search audit logs...", width=220, value="", prefix_icon=ft.Icon(ft.Icons.SEARCH, size=18), dense=True)
    audit_date_filter = ft.Dropdown(
        label="Date Range",
        width=170,
        value="last_30_days",
        options=[
            ft.dropdown.Option("today", "Today"),
            ft.dropdown.Option("yesterday", "Yesterday"),
            ft.dropdown.Option("last_7_days", "This Week"),
            ft.dropdown.Option("this_month", "This Month"),
            ft.dropdown.Option("last_30_days", "Last 30 Days"),
            ft.dropdown.Option("custom_range", "Custom Range"),
        ],
    )
    audit_user_filter = ft.Dropdown(label="User", width=170, value="All Users", options=[ft.dropdown.Option("All Users", "All Users")])
    audit_module_filter = ft.Dropdown(label="Module", width=170, value="All Modules", options=[ft.dropdown.Option("All Modules", "All Modules")])
    audit_action_filter = ft.Dropdown(label="Action", width=170, value="All Actions", options=[ft.dropdown.Option("All Actions", "All Actions")])
    audit_status_filter = ft.Dropdown(
        label="Status",
        width=150,
        value="All Status",
        options=[
            ft.dropdown.Option("All Status", "All Status"),
            ft.dropdown.Option("Success", "Success"),
            ft.dropdown.Option("Failed", "Failed"),
        ],
    )

    def update_audit_filter_options(payload):
        if not payload:
            return
        filters = payload.get("filters") or {}
        users = filters.get("users") or []
        modules = filters.get("modules") or []
        actions = filters.get("actions") or []

        def build_options(values, placeholder):
            result = [ft.dropdown.Option("all", placeholder)]
            for value in values:
                if value is None:
                    continue
                result.append(ft.dropdown.Option(str(value), str(value)))
            return result

        audit_user_filter.options = build_options(users, "All Users")
        audit_module_filter.options = build_options(modules, "All Modules")
        audit_action_filter.options = build_options(actions, "All Actions")
        if audit_user_filter.value not in [opt.key for opt in audit_user_filter.options]:
            audit_user_filter.value = "all"
        if audit_module_filter.value not in [opt.key for opt in audit_module_filter.options]:
            audit_module_filter.value = "all"
        if audit_action_filter.value not in [opt.key for opt in audit_action_filter.options]:
            audit_action_filter.value = "all"

    def apply_audit_filters():
        audit_filter_state["search"] = (audit_search_field.value or "").strip()
        audit_filter_state["date_range"] = audit_date_filter.value or "last_30_days"
        audit_filter_state["user"] = normalize_audit_filter_value(audit_user_filter.value, "all")
        audit_filter_state["module"] = normalize_audit_filter_value(audit_module_filter.value, "all")
        audit_filter_state["action"] = normalize_audit_filter_value(audit_action_filter.value, "all")
        audit_filter_state["status"] = normalize_audit_filter_value(audit_status_filter.value, "all")
        audit_filter_state["page"] = 1
        load_audit_logs_view()

    def clear_audit_filters():
        audit_search_field.value = ""
        audit_date_filter.value = "last_30_days"
        audit_user_filter.value = "all"
        audit_module_filter.value = "all"
        audit_action_filter.value = "all"
        audit_status_filter.value = "All Status"
        audit_filter_state.update({"page": 1, "search": "", "date_range": "last_30_days", "user": "all", "module": "all", "action": "all", "status": "All Status"})
        load_audit_logs_view()

    def render_summary_cards(summary_payload):
        summary = summary_payload or {}
        cards = [
            ("Total Activities", summary.get("total_activities", 0), "All tracked actions"),
            ("Today", summary.get("today", 0), "Last 24 hours"),
            ("This Week", summary.get("this_week", 0), "Last 7 days"),
            ("This Month", summary.get("this_month", 0), "Current month"),
            ("Failed Actions", summary.get("failed_actions", 0), "Blocked / rejected"),
        ]
        summary_controls = []
        for label, value, hint in cards:
            summary_controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(label, size=11, color=ft.Colors.BLUE_GREY_600, weight=ft.FontWeight.W_500),
                            ft.Text(str(value), size=22, weight=ft.FontWeight.BOLD),
                            ft.Text(hint, size=10, color=ft.Colors.BLUE_GREY_500),
                        ],
                        spacing=3,
                    ),
                    width=170,
                    padding=ft.Padding(14, 12, 14, 12),
                    border_radius=14,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    bgcolor=ft.Colors.BLUE_GREY_50,
                )
            )
        audit_summary_cards.controls = summary_controls

    def format_details_cell(item):
        text = str(item.get("details") or item.get("description") or "—")
        if len(text) > 110:
            text = text[:107] + "..."
        return ft.Text(text, size=11, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)

    def build_audit_details_dialog(item):
        content_rows = []
        for label, key in (["Date & Time", "created_at"], ["User", "actor"], ["Action", "action"], ["Module", "module"], ["Status", "status"], ["IP Address", "ip_address"], ["Description", "details"], ["Additional Details", "metadata"]):
            if key == "metadata":
                value = item.get("metadata") or {}
                if value:
                    content_rows.append(ft.Text(f"{label}: {json.dumps(value, ensure_ascii=False)}", size=12))
                continue
            value = item.get(key)
            if value is None or value == "" or value == "None":
                continue
            content_rows.append(ft.Text(f"{label}: {value}", size=12, selectable=True))
        audit_details_dialog.content = ft.Column(content_rows or [ft.Text("No additional details available.", size=12)], spacing=8, tight=True)
        audit_details_dialog.open = True
        page.update()

    def set_audit_pagination(page_count, current_page, total_items=0):
        page_count = max(1, int(page_count or 1))
        current_page = max(1, int(current_page or 1))
        current_page = min(current_page, page_count)
        audit_filter_state["page_count"] = page_count
        audit_filter_state["page"] = current_page

        buttons = [ft.TextButton("Previous", on_click=lambda _: advance_audit_page(-1), disabled=current_page <= 1)]
        if page_count > 0:
            for page_num in range(1, min(5, page_count) + 1):
                button_style = ft.ButtonStyle(color=ft.Colors.BLUE if page_num == current_page else None)
                buttons.append(
                    ft.TextButton(
                        str(page_num),
                        on_click=lambda _, target_page=page_num: go_to_audit_page(target_page),
                        style=button_style,
                    )
                )
            if page_count > 5:
                buttons.append(ft.Text("...", size=12, color=ft.Colors.BLUE_GREY_600))
                buttons.append(ft.TextButton(str(page_count), on_click=lambda _, target_page=page_count: go_to_audit_page(target_page)))
        buttons.append(ft.TextButton("Next", on_click=lambda _: advance_audit_page(1), disabled=current_page >= page_count))
        audit_pagination_bar.controls = [build_audit_results_label(total_items, current_page, audit_filter_state.get("limit", 10))] + buttons

    def go_to_audit_page(target_page):
        max_page = max(1, audit_filter_state.get("page_count", 1))
        target_page = max(1, min(int(target_page), max_page))
        audit_filter_state["page"] = target_page
        load_audit_logs_view()

    def advance_audit_page(step):
        current_page = audit_filter_state.get("page", 1)
        max_page = max(1, audit_filter_state.get("page_count", 1))
        target = max(1, min(int(current_page) + int(step), max_page))
        go_to_audit_page(target)

    def load_audit_logs_view():
        try:
            params = {
                "page": audit_filter_state.get("page", 1),
                "limit": audit_filter_state.get("limit", 10),
                "date_range": audit_filter_state.get("date_range", "last_30_days"),
            }
            if audit_filter_state.get("search"):
                params["search"] = audit_filter_state["search"]
            if audit_filter_state.get("user") and audit_filter_state["user"] not in ("all", "All Users"):
                params["user"] = audit_filter_state["user"]
            if audit_filter_state.get("module") and audit_filter_state["module"] not in ("all", "All Modules"):
                params["module"] = audit_filter_state["module"]
            if audit_filter_state.get("action") and audit_filter_state["action"] not in ("all", "All Actions"):
                params["action"] = audit_filter_state["action"]
            if audit_filter_state.get("status") and audit_filter_state["status"] not in ("All Status", "all"):
                params["status"] = audit_filter_state["status"]

            response = requests.get(f"{BACKEND_URL}/audit/logs", headers=get_admin_headers(), verify=False, params=params, timeout=20)
            if response.status_code != 200:
                raise ValueError(response.text)

            payload = response.json()
            items = payload.get("items") or []
            summary = payload.get("summary") or {}
            render_summary_cards(summary)
            update_audit_filter_options(payload)

            rows = []
            for item in items:
                status = item.get("status") or "Success"
                rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(format_audit_datetime(item.get("created_at")), size=11)),
                            ft.DataCell(ft.Text(str(item.get("actor") or "—"), size=11)),
                            ft.DataCell(ft.Text(str(item.get("action") or "—"), size=11)),
                            ft.DataCell(ft.Text(str(item.get("module") or item.get("target_type") or "—"), size=11)),
                            ft.DataCell(format_details_cell(item)),
                            ft.DataCell(render_status_badge(status)),
                        ],
                        on_select_changed=lambda e, payload_item=item: build_audit_details_dialog(payload_item) if payload_item else None,
                    )
                )
            if not rows:
                rows = [
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text("No audit logs found for the selected filters.", size=11)),
                        ft.DataCell(ft.Text("—")),
                        ft.DataCell(ft.Text("—")),
                        ft.DataCell(ft.Text("—")),
                        ft.DataCell(ft.Text("—")),
                        ft.DataCell(ft.Text("—")),
                    ])
                ]
            audit_logs_table.rows = rows

            total_items = payload.get("total") or 0
            current_page = payload.get("page") or 1
            total_pages = payload.get("pages") or 1
            set_audit_pagination(total_pages, current_page, total_items)
            audit_pagination_bar.alignment = ft.MainAxisAlignment.SPACE_BETWEEN
        except Exception:
            sample_rows = AUDIT_LOGS_SAMPLE
            audit_logs_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(format_audit_datetime(item.get("created_at", "")), size=11)),
                    ft.DataCell(ft.Text(str(item.get("actor", "Admin")), size=11)),
                    ft.DataCell(ft.Text(str(item.get("action", "USER_LOGIN")), size=11)),
                    ft.DataCell(ft.Text(str(item.get("target_type", "Auth")), size=11)),
                    ft.DataCell(ft.Text(str(item.get("details", "Sample audit log entry.")), size=11)),
                    ft.DataCell(render_status_badge(item.get("status", "Success"))),
                ])
                for item in sample_rows
            ]
            failed_count = sum(1 for item in sample_rows if str(item.get("status", "Success")).lower() == "failed")
            today_count = sum(1 for item in sample_rows if item.get("created_at") and datetime.fromisoformat(str(item["created_at"]).replace("Z", "+00:00")).date() == datetime.now(timezone.utc).date())
            render_summary_cards({
                "total_activities": len(sample_rows),
                "today": today_count,
                "this_week": len(sample_rows),
                "this_month": len(sample_rows),
                "failed_actions": failed_count,
            })
            set_audit_pagination(max(1, (len(sample_rows) + 9) // 10), 1, len(sample_rows))

        page.update()

    audit_filter_bar.controls = [
        audit_search_field,
        audit_date_filter,
        audit_user_filter,
        audit_module_filter,
        audit_action_filter,
        audit_status_filter,
        ft.ElevatedButton("Apply Filters", on_click=lambda _: apply_audit_filters()),
        ft.TextButton("Clear Filters", on_click=lambda _: clear_audit_filters()),
    ]
    audit_filter_bar.wrap = True

    def on_export_audit_logs(_):
        page.snack_bar = ft.SnackBar(
            ft.Text("Export continues using the existing backend export route."),
            open=True,
        )
        page.update()

    audit_action_bar.controls = [
        ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=lambda _: load_audit_logs_view()),
        ft.OutlinedButton("Export", icon=ft.Icons.DOWNLOAD, on_click=on_export_audit_logs),
    ]

    def audit_logs_view():
        try:
            if audit_details_dialog not in page.overlay:
                page.overlay.append(audit_details_dialog)
            audit_filter_state["page"] = 1
            load_audit_logs_view()
            return build_audit_logs_view(
                audit_logs_table,
                load_audit_logs_view,
                surface_card,
                section_header,
                summary_cards=audit_summary_cards,
                filter_bar=surface_card(
                    ft.Column(
                        [
                            ft.Text("Filters", size=13, weight=ft.FontWeight.BOLD),
                            audit_filter_bar,
                        ],
                        spacing=10,
                        tight=True,
                    ),
                    padding=14,
                    expand=False,
                ),
                action_bar=surface_card(
                    ft.Row(
                        audit_action_bar.controls,
                        spacing=8,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    expand=False,
                ),
                pagination_bar=surface_card(
                    ft.Row(
                        audit_pagination_bar.controls,
                        spacing=8,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    expand=False,
                ),
                details_dialog=audit_details_dialog,
            )
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

    documents_data = []
    archived_documents_data = []

    def get_document_status_style(status):
        normalized = (status or "").strip().lower()
        if normalized in {"pending", "under review"}:
            return ft.Colors.ORANGE_700, ft.Colors.ORANGE_50
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
        options=[ft.dropdown.Option("All"), ft.dropdown.Option("Pending"), ft.dropdown.Option("Received"), ft.dropdown.Option("Approved"), ft.dropdown.Option("Returned"), ft.dropdown.Option("Archived")],
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
    documents_filter_priority = ft.Dropdown(
        label="Priority",
        width=120,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("Low"),
            ft.dropdown.Option("Medium"),
            ft.dropdown.Option("High"),
        ],
        value="All",
    )
    documents_status_filter = documents_filter_status
    documents_category_filter = documents_filter_category
    documents_type_filter = documents_filter_type
    documents_assigned_filter = documents_filter_office


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

    pending_restore_document = None
    archived_restore_dialog = ft.AlertDialog(
        title=ft.Text("Restore Document"),
        content=ft.Text("Are you sure you want to restore this document to the active document records?"),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_archived_restore_dialog()),
            ft.Button("Restore", bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, on_click=lambda _: run_restore_archived_document_action()),
        ],
    )
    page.overlay.append(archived_restore_dialog)

    pending_permanent_delete_document = None
    archived_delete_dialog = ft.AlertDialog(
        title=ft.Text("Delete Archived Document Permanently"),
        content=ft.Text("This action permanently deletes the archived document and cannot be undone. Are you sure you want to continue?"),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_archived_delete_dialog()),
            ft.Button("Delete Permanently", bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, on_click=lambda _: run_permanent_delete_archived_document_action()),
        ],
    )
    page.overlay.append(archived_delete_dialog)

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
            ft.dropdown.Option("Pending"),
            ft.dropdown.Option("Approved"),
            ft.dropdown.Option("Returned"),
        ],
        value="Pending",
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

    qr_label_dialog_content = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)
    qr_label_download_dialog = ft.AlertDialog(
        title=ft.Text("Download QR Labels"),
        content=ft.Container(content=qr_label_dialog_content, padding=14, width=560, height=420),
        actions=[
            ft.TextButton("Close", on_click=lambda _: close_qr_label_download_dialog()),
            ft.TextButton("Deselect All", on_click=lambda _: clear_selected_qr_documents()),
            ft.Button("Download PDF", icon=ft.Icons.DOWNLOAD, on_click=lambda _: download_selected_qr_labels()),
        ],
    )
    page.overlay.append(qr_label_download_dialog)

    registration_title = ft.TextField(label="Title", width=680)
    registration_description = ft.TextField(label="Description", multiline=True, min_lines=2, max_lines=3, width=680)
    registration_category = ft.Dropdown(
        label="Category",
        width=330,
        options=[
            ft.dropdown.Option("Legislation"),
            ft.dropdown.Option("Policy"),
            ft.dropdown.Option("Report"),
        ],
        value="Legislation",
    )
    registration_document_type = ft.Dropdown(
        label="Document Type",
        width=330,
        options=[
            ft.dropdown.Option("Ordinance"),
            ft.dropdown.Option("Resolution"),
            ft.dropdown.Option("Committee Report"),
        ],
        value="Ordinance",
    )
    registration_current_office = ft.Dropdown(
        label="Current Office",
        width=330,
        options=[
            ft.dropdown.Option("SB Secretariat"),
            ft.dropdown.Option("Office of the Mayor"),
            ft.dropdown.Option("Committee on Health"),
        ],
        value="SB Secretariat",
    )
    registration_assigned_to = ft.TextField(label="Assigned To", width=330)
    registration_author = ft.TextField(label="Author", width=330)
    registration_priority = ft.Dropdown(
        label="Priority",
        width=330,
        options=[
            ft.dropdown.Option("Low"),
            ft.dropdown.Option("Medium"),
            ft.dropdown.Option("High"),
        ],
        value="Medium",
    )
    registration_attachment = None
    registration_attachment_label = ft.Text("No file selected", size=12, color=ft.Colors.BLUE_GREY_600)
    file_picker = ft.FilePicker(on_result=lambda e: None)
    page.overlay.append(file_picker)

    def _on_registration_file(e):
        nonlocal registration_attachment
        try:
            if getattr(e, 'files', None):
                f = e.files[0]
                attachment_path = getattr(e, 'path', None) or getattr(f, 'path', None)
                if attachment_path and not os.path.isabs(attachment_path) and not os.path.exists(attachment_path):
                    attachment_path = os.path.abspath(attachment_path)
                registration_attachment = {
                    "path": attachment_path,
                    "name": getattr(f, 'name', None),
                }
                filename = registration_attachment["name"] or ""
                registration_attachment_label.value = filename or "No file selected"

                if filename:
                    title_candidate = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").strip()
                    if title_candidate and not (registration_title.value or "").strip():
                        registration_title.value = title_candidate.title()

                    ext = os.path.splitext(filename)[1].lower().lstrip('.')
                    if ext and not (registration_document_type.value or "").strip():
                        type_map = {
                            "pdf": "Resolution",
                            "doc": "Committee Report",
                            "docx": "Committee Report",
                            "xls": "Resolution",
                            "xlsx": "Resolution",
                            "ppt": "Committee Report",
                            "pptx": "Committee Report",
                            "txt": "Ordinance",
                            "csv": "Resolution",
                            "jpg": "Resolution",
                            "jpeg": "Resolution",
                            "png": "Resolution",
                            "gif": "Resolution",
                        }
                        registration_document_type.value = type_map.get(ext, "Ordinance")
            else:
                registration_attachment = None
                registration_attachment_label.value = "No file selected"
        except Exception:
            registration_attachment = None
            registration_attachment_label.value = "No file selected"
        page.update()

    # attach handler to file_picker
    file_picker.on_result = _on_registration_file

    def registration_section(title):
        return ft.Text(
            title.upper(),
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_700,
        )

    registration_upload_area = ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.UPLOAD_FILE, color=ft.Colors.BLUE_700, size=24),
                    padding=10,
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    border_radius=10,
                ),
                ft.Column(
                    [
                        ft.Text("Choose document file", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_800),
                        registration_attachment_label,
                    ],
                    spacing=3,
                    expand=True,
                ),
                ft.OutlinedButton("Choose file", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=lambda _: file_picker.pick_files()),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        width=680,
        padding=12,
        bgcolor=ft.Colors.BLUE_GREY_50,
        border=ft.border.all(1, ft.Colors.BLUE_GREY_200),
        border_radius=10,
    )

    register_document_dialog = ft.AlertDialog(
        title=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color=ft.Colors.BLUE_700, size=22),
                    padding=9,
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    border_radius=10,
                ),
                ft.Column(
                    [
                        ft.Text("Register Document", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                        ft.Text("Add a new legislative document record.", size=12, color=ft.Colors.BLUE_GREY_600),
                    ],
                    spacing=2,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Column(
            [
                registration_section("Basic Information"),
                registration_title,
                registration_description,
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                registration_section("Document Classification"),
                ft.Row([registration_category, registration_document_type], spacing=12, wrap=True),
                registration_priority,
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                registration_section("Assignment"),
                ft.Row([registration_current_office, registration_assigned_to], spacing=12, wrap=True),
                registration_author,
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                registration_section("Document File"),
                registration_upload_area,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            width=700,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_register_document_dialog()),
            ft.Button("Save Document", icon=ft.Icons.SAVE_OUTLINED, on_click=lambda _: submit_register_document(), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
        ],
    )
    page.overlay.append(register_document_dialog)

    def close_qr_scan_dialog():
        qr_scan_dialog.open = False
        page.update()

    def close_qr_monitor_dialog():
        qr_monitor_dialog.open = False
        page.update()

    def clear_selected_qr_documents():
        selected_qr_document_ids.clear()
        refresh_qr_selection_badge()
        apply_document_search_to_current_view()
        close_qr_label_download_dialog()
        page.update()

    def close_qr_label_download_dialog():
        qr_label_download_dialog.open = False
        page.update()

    def open_qr_label_download_dialog(_=None):
        selected_ids = sorted(selected_qr_document_ids)
        qr_label_dialog_content.controls = []
        if not selected_ids:
            qr_label_dialog_content.controls = [
                ft.Text("No documents are currently selected for QR label printing.", size=13, color=ft.Colors.BLUE_GREY_700),
                ft.Text("Select rows in the Documents table first, then open this dialog again.", size=12, color=ft.Colors.BLUE_GREY_600),
            ]
        else:
            selected_doc_lines = []
            for doc_id in selected_ids:
                match = next((doc for doc in documents_data if doc.get("id") == doc_id), None)
                if match:
                    selected_doc_lines.append(
                        ft.Text(
                            f"{match.get('tracking_number', '-')} — {match.get('title', '-')} — {match.get('current_office', '-')}",
                            size=12,
                            color=ft.Colors.BLUE_GREY_800,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        )
                    )

            qr_label_dialog_content.controls = [
                ft.Text("Selected Documents", size=15, weight=ft.FontWeight.BOLD),
                ft.Text(f"{len(selected_ids)} document(s) ready for QR label export", size=12, color=ft.Colors.BLUE_GREY_700),
                ft.Container(
                    content=ft.Column(
                        controls=selected_doc_lines,
                        spacing=8,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    width="100%",
                    height=260,
                    border=ft.Border(
                        top=ft.BorderSide(1, ft.Colors.BLUE_GREY_200),
                        right=ft.BorderSide(1, ft.Colors.BLUE_GREY_200),
                        bottom=ft.BorderSide(1, ft.Colors.BLUE_GREY_200),
                        left=ft.BorderSide(1, ft.Colors.BLUE_GREY_200),
                    ),
                    border_radius=8,
                    padding=10,
                    bgcolor=ft.Colors.WHITE,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ]
        qr_label_download_dialog.open = True
        page.update()

    def close_register_document_dialog():
        register_document_dialog.open = False
        page.update()

    def open_register_document_dialog(_=None):
        nonlocal registration_attachment
        registration_title.value = ""
        registration_description.value = ""
        registration_category.value = "Legislation"
        registration_document_type.value = "Ordinance"
        registration_current_office.value = "SB Secretariat"
        registration_assigned_to.value = ""
        registration_author.value = ""
        registration_priority.value = "Medium"
        registration_attachment = None
        registration_attachment_label.value = "No file selected"
        register_document_dialog.open = True
        page.update()

    # --- Multiple / Bulk Registration dialog and upload flow (browser-safe) ---
    bulk_import_files = []  # list of dicts: {name, size, tmp_name, status, progress}
    bulk_selected_list = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=0)
    bulk_selected_count = ft.Text("Selected Files (0)", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_800)
    bulk_selected_list_container = ft.Container(
        content=bulk_selected_list,
        width=640,
        height=200,
        visible=False,
        padding=8,
        border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
        border_radius=8,
        bgcolor=ft.Colors.WHITE,
    )
    bulk_common_title = ft.TextField(label="Common Title (optional)", width=320)
    bulk_common_description = ft.TextField(label="Common Description", multiline=True, min_lines=2, max_lines=3, width=320)
    bulk_common_category = ft.Dropdown(label="Category", width=210, options=[ft.dropdown.Option("Legislation"), ft.dropdown.Option("Policy"), ft.dropdown.Option("Report")], value="Legislation")
    bulk_common_document_type = ft.Dropdown(label="Document Type", width=210, options=[ft.dropdown.Option("Ordinance"), ft.dropdown.Option("Resolution"), ft.dropdown.Option("Committee Report")], value="Ordinance")
    bulk_common_current_office = ft.Dropdown(label="Current Office", width=210, options=[ft.dropdown.Option("SB Secretariat"), ft.dropdown.Option("Office of the Mayor"), ft.dropdown.Option("Committee on Health")], value="SB Secretariat")
    bulk_common_assigned_to = ft.TextField(label="Assigned To", width=210)
    bulk_common_author = ft.TextField(label="Author", width=210)
    bulk_common_priority = ft.Dropdown(label="Priority", width=210, options=[ft.dropdown.Option("Low"), ft.dropdown.Option("Medium"), ft.dropdown.Option("High")], value="Medium")

    bulk_file_picker = ft.FilePicker(on_result=lambda e: None, on_upload=lambda e: None)
    page.overlay.append(bulk_file_picker)

    def _render_bulk_selected_list():
        bulk_selected_list.controls = []
        bulk_selected_count.value = f"Selected Files ({len(bulk_import_files)})"
        if not bulk_import_files:
            bulk_selected_list.controls.append(ft.Text("No files selected", size=11, color=ft.Colors.BLUE_GREY_600))
        bulk_selected_list_container.visible = bool(bulk_import_files)
        for item in bulk_import_files:
            status_text = item.get("status", "")
            row_controls = [
                ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=18, color=ft.Colors.BLUE_700),
                ft.Container(content=ft.Text(item.get("name", "-"), size=12, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=190, alignment=ft.Alignment.CENTER_LEFT),
                ft.Text(f"{(item.get('size') or 0)//1024} KB", size=11, color=ft.Colors.BLUE_GREY_600),
                ft.Text(status_text, size=11, color=ft.Colors.GREEN_700 if status_text == "Ready" else ft.Colors.BLUE_GREY_700),
            ]
            if item.get("progress") is not None:
                row_controls.append(ft.ProgressBar(value=item.get("progress", 0.0), width=100))
            row_controls.append(ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remove file", on_click=lambda e, nm=item.get("tmp_name"): _remove_tmp_file(nm)))
            bulk_selected_list.controls.append(
                ft.Container(
                    content=ft.Row(row_controls, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(4, 6, 4, 6),
                    border=ft.border.only(bottom=ft.border.all(1, ft.Colors.BLUE_GREY_100)),
                )
            )
        page.update()

    def _remove_tmp_file(tmp_name):
        nonlocal bulk_import_files
        bulk_import_files = [i for i in bulk_import_files if i.get("tmp_name") != tmp_name]
        _render_bulk_selected_list()

    def _on_bulk_pick(e):
        nonlocal bulk_import_files
        files = getattr(e, "files", None) or []
        if not files:
            return
        # Request server-generated temporary upload URLs tied to the authenticated user
        files_meta = []
        for f in files:
            name = getattr(f, "name", None) or ""
            size = getattr(f, "size", None) or 0
            files_meta.append({"filename": name, "size": size})

        try:
            resp = requests.post(f"{BACKEND_URL}/documents/uploads/create_tmp_uploads", json={"files": files_meta}, headers=get_admin_headers(), verify=False, timeout=30)
            if resp.status_code != 200:
                raise Exception(resp.text)
            body = resp.json()
            upload_items = []
            for info in body.get("files", []):
                if not info.get("ok"):
                    bulk_import_files.append({"name": info.get("filename"), "size": 0, "tmp_name": None, "status": f"Rejected: {info.get('reason')}", "progress": 0.0})
                    continue
                name = info.get("filename")
                tmp_name = info.get("tmp_name")
                upload_url = info.get("upload_url")
                bulk_import_files.append({"name": name, "size": 0, "tmp_name": tmp_name, "status": "Queued", "progress": 0.0})
                upload_items.append(FilePickerUploadFile(name=name, upload_url=upload_url, method="PUT"))

            _render_bulk_selected_list()
            try:
                bulk_file_picker.upload(upload_items)
            except Exception as exc:
                show_document_notice(f"Upload start failed: {exc}")
        except Exception as exc:
            show_document_notice(f"Failed to create upload URLs: {exc}")

    def _on_bulk_upload(e):
        # e: FilePickerUploadEvent
        fname = getattr(e, "file_name", None)
        progress = getattr(e, "progress", None)
        error = getattr(e, "error", None)
        for item in bulk_import_files:
            if item.get("name") == fname:
                if error:
                    item["status"] = f"Error: {error}"
                    item["progress"] = 0.0
                else:
                    if progress is None:
                        item["progress"] = 1.0
                        item["status"] = "Ready"
                    else:
                        item["progress"] = progress
                        item["status"] = f"Uploading {int(progress*100)}%"
                break
        _render_bulk_selected_list()

    bulk_file_picker.on_result = _on_bulk_pick
    bulk_file_picker.on_upload = _on_bulk_upload

    def open_bulk_register_document_dialog(_=None):
        # reset
        nonlocal bulk_import_files
        bulk_import_files = []
        _render_bulk_selected_list()
        bulk_common_title.value = ""
        bulk_common_description.value = ""
        bulk_common_assigned_to.value = ""
        bulk_common_author.value = ""
        bulk_register_dialog.open = True
        page.update()

    def bulk_section_label(title, subtitle):
        return ft.Column(
            [
                ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                ft.Text(subtitle, size=11, color=ft.Colors.BLUE_GREY_600),
            ],
            spacing=2,
        )

    bulk_upload_area = ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED, color=ft.Colors.BLUE_700, size=32),
                ft.Text("Drag and drop files here", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_800),
                ft.Text("or", size=11, color=ft.Colors.BLUE_GREY_600),
                ft.OutlinedButton(
                    "Choose files",
                    icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                    on_click=lambda _: bulk_file_picker.pick_files(file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["pdf", "doc", "docx"], allow_multiple=True),
                ),
                ft.Text("You can select multiple files at once.", size=10, color=ft.Colors.BLUE_GREY_600),
                bulk_selected_count,
                bulk_selected_list_container,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=5,
        ),
        width=680,
        padding=14,
        border=ft.border.all(1, ft.Colors.BLUE_GREY_200),
        border_radius=10,
        bgcolor=ft.Colors.BLUE_GREY_50,
    )

    bulk_register_dialog = ft.AlertDialog(
        title=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.NOTE_ADD_OUTLINED, color=ft.Colors.BLUE_700, size=23),
                    padding=9,
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    border_radius=10,
                ),
                ft.Column(
                    [
                        ft.Text("Multiple Document Registration", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                        ft.Text("Upload and register multiple documents at once.", size=12, color=ft.Colors.BLUE_GREY_600),
                    ],
                    spacing=2,
                ),
                ft.IconButton(icon=ft.Icons.CLOSE, tooltip="Close", on_click=lambda _: close_bulk_register_document_dialog()),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Column(
            [
                bulk_section_label("1. Upload Files", "Select PDF or Word files (PDF, DOC, DOCX)."),
                bulk_upload_area,
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                bulk_section_label("2. Common Document Information", "These details will be applied to all uploaded documents."),
                ft.Row([bulk_common_title, bulk_common_description], spacing=12, wrap=True),
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                bulk_section_label("3. Document Details", "Set the classification and assignment for all uploaded documents."),
                ft.Row([bulk_common_category, bulk_common_document_type, bulk_common_priority], spacing=12, wrap=True),
                ft.Row([bulk_common_current_office, bulk_common_assigned_to, bulk_common_author], spacing=12, wrap=True),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            width=700,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_bulk_register_document_dialog()),
            ft.Button("Validate Files", icon=ft.Icons.CHECK_OUTLINED, on_click=lambda _: _validate_bulk_files(), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
            ft.Button("Confirm Bulk Register", icon=ft.Icons.SAVE_OUTLINED, on_click=lambda _: _confirm_bulk_register(), bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE),
        ],
    )
    page.overlay.append(bulk_register_dialog)

    def close_bulk_register_document_dialog():
        bulk_register_dialog.open = False
        page.update()

    def _validate_bulk_files():
        if not bulk_import_files:
            show_document_notice("No files selected")
            return
        tmp_names = [i.get("tmp_name") for i in bulk_import_files]
        try:
            response = requests.post(f"{BACKEND_URL}/documents/bulk-register/validate_tmp", json={"tmp_names": tmp_names}, headers=get_admin_headers(), verify=False, timeout=60)
            if response.status_code != 200:
                raise Exception(response.text)
            payload = response.json()
            for row in payload.get("files", []):
                for item in bulk_import_files:
                    if item.get("tmp_name") == row.get("tmp_name") or item.get("name") == row.get("filename"):
                        if row.get("valid"):
                            item["status"] = "Ready"
                            item["progress"] = 1.0
                        else:
                            item["status"] = f"Invalid: {', '.join(row.get('errors', []))}"
                            item["progress"] = 0.0
            _render_bulk_selected_list()
        except Exception as exc:
            show_document_notice(f"Bulk validation failed: {exc}")

    def _confirm_bulk_register():
        if not bulk_import_files:
            show_document_notice("No files to register")
            return
        tmp_names = [i.get("tmp_name") for i in bulk_import_files]
        payload = {
            "tmp_names": tmp_names,
            "title": (bulk_common_title.value or None),
            "description": (bulk_common_description.value or None),
            "category": (bulk_common_category.value or None),
            "document_type": (bulk_common_document_type.value or None),
            "current_office": (bulk_common_current_office.value or None),
            "assigned_to": (bulk_common_assigned_to.value or None),
            "author": (bulk_common_author.value or None),
            "priority": (bulk_common_priority.value or None),
        }
        try:
            response = requests.post(f"{BACKEND_URL}/documents/bulk-register/confirm_tmp", json=payload, headers=get_admin_headers(), verify=False, timeout=180)
            if response.status_code != 200:
                raise Exception(response.text)
            result = response.json()
            show_document_notice(f"Bulk registration completed: {result.get('registered',0)} created, {result.get('failed',0)} failed.")
            close_bulk_register_document_dialog()
            load_documents_table()
        except Exception as exc:
            show_document_notice(f"Bulk registration failed: {exc}")

    def submit_register_document(_=None):
        title = (registration_title.value or "").strip()
        if not title:
            show_document_notice("Title is required to register a document.")
            return

        payload = {
            "title": title,
            "description": (registration_description.value or "").strip() or None,
            "category": (registration_category.value or "").strip() or None,
            "document_type": (registration_document_type.value or "").strip() or None,
            "current_office": (registration_current_office.value or "").strip() or None,
            "assigned_to": (registration_assigned_to.value or "").strip() or None,
            "author": (registration_author.value or "").strip() or None,
            "priority": (registration_priority.value or "Medium").strip() or "Medium",
        }

        try:
            # if a file was chosen, send multipart/form-data with file and form fields
            if registration_attachment and registration_attachment.get("path"):
                data = {k: v for k, v in payload.items() if v is not None}
                attachment_path = registration_attachment["path"]
                if not os.path.isabs(attachment_path):
                    attachment_path = os.path.abspath(attachment_path)
                with open(attachment_path, "rb") as fh:
                    files = {
                        "file": (
                            registration_attachment.get("name") or os.path.basename(attachment_path),
                            fh,
                            mimetypes.guess_type(attachment_path)[0] or "application/octet-stream",
                        )
                    }
                    response = requests.post(
                        f"{BACKEND_URL}/documents/register",
                        data=data,
                        files=files,
                        headers=get_admin_headers(),
                        verify=False,
                        timeout=60,
                    )
            else:
                response = requests.post(
                    f"{BACKEND_URL}/documents/register",
                    data={k: v for k, v in payload.items() if v is not None},
                    headers=get_admin_headers(),
                    verify=False,
                    timeout=15,
                )
            if response.status_code not in {200, 201}:
                try:
                    error_json = response.json()
                    error_detail = error_json.get("detail", response.text)
                except Exception:
                    error_detail = response.text
                raise Exception(f"{response.status_code} {error_detail}")
            register_document_dialog.open = False
            page.update()
            load_documents_table()
            show_document_notice("Document registered successfully.")
        except Exception as exc:
            show_document_notice(f"Document registration failed: {exc}")

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
        recent_generated_qrs = payload.get('recent_generated_qrs') or []
        if recent_generated_qrs:
            summary.append(ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100))
            summary.append(ft.Text("Recent generated QR codes", size=13, weight=ft.FontWeight.BOLD))
            for qr in recent_generated_qrs[:8]:
                summary.append(
                    ft.Text(
                        f"{qr.get('tracking_number', 'N/A')} — {qr.get('qr_code_value', 'N/A')} — {qr.get('created_at', 'N/A')}",
                        size=12,
                    )
                )
        documents = payload.get('documents') or []
        if documents:
            summary.append(ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100))
            summary.append(ft.Text("Recent documents", size=13, weight=ft.FontWeight.BOLD))
            for doc in documents[:8]:
                summary.append(ft.Text(f"{doc.get('tracking_number', 'N/A')} — {doc.get('status', 'N/A')} — {doc.get('current_office', 'N/A')}", size=12))
        return summary

    def load_qr_monitor_data():
        try:
            response = requests.get(f"{BACKEND_URL}/documents/qr/monitor", headers=get_admin_headers(), verify=False, timeout=10)
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
        scan_status_dropdown.value = "Pending"
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
            "status": scan_status_dropdown.value or "Pending",
        }
        try:
            response = requests.post(f"{BACKEND_URL}/documents/scan", json=payload, headers=get_admin_headers(), verify=False, timeout=10)
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

    selected_qr_document_ids = set()

    def refresh_qr_selection_badge():
        if selected_qr_document_ids:
            documents_notice.value = f"{len(selected_qr_document_ids)} QR labels selected"
        else:
            documents_notice.value = ""
        page.update()

    documents_table = ft.DataTable(
        columns=[
            ft.DataColumn(label=make_document_header("Select", 78)),
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
        expand=False,
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
            ft.DataColumn(label=make_document_header("Tracking No.", 140)),
            ft.DataColumn(label=make_document_header("Title", 320)),
            ft.DataColumn(label=make_document_header("Document Type", 150)),
            ft.DataColumn(label=make_document_header("Date Archived", 150)),
            ft.DataColumn(label=make_document_header("Archived By", 150)),
        ],
        rows=[],
        width=1100,
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

    def close_archived_restore_dialog():
        nonlocal pending_restore_document
        pending_restore_document = None
        archived_restore_dialog.open = False
        page.update()

    def confirm_restore_archived_document(doc):
        nonlocal pending_restore_document
        pending_restore_document = doc
        archived_restore_dialog.open = True
        page.update()

    def run_restore_archived_document_action():
        nonlocal pending_restore_document
        document = pending_restore_document
        close_archived_restore_dialog()
        if not document:
            return
        try:
            response = requests.post(
                f"{BACKEND_URL}/documents/{document.get('id')}/restore",
                headers=get_admin_headers(),
                verify=False,
                timeout=10,
            )
            if response.status_code != 200:
                raise Exception(response.text)
            show_document_notice("Document restored successfully.")
            load_documents_table()
            load_archived_documents_table()
        except Exception as exc:
            show_document_notice(f"Restore failed: {exc}")

    def close_archived_delete_dialog():
        nonlocal pending_permanent_delete_document
        pending_permanent_delete_document = None
        archived_delete_dialog.open = False
        page.update()

    def confirm_permanent_delete_archived_document(doc):
        nonlocal pending_permanent_delete_document
        pending_permanent_delete_document = doc
        archived_delete_dialog.open = True
        page.update()

    def run_permanent_delete_archived_document_action():
        nonlocal pending_permanent_delete_document
        document = pending_permanent_delete_document
        close_archived_delete_dialog()
        if not document:
            return
        try:
            response = requests.delete(
                f"{BACKEND_URL}/documents/{document.get('id')}/permanent",
                headers=get_admin_headers(),
                verify=False,
                timeout=10,
            )
            if response.status_code != 200:
                raise Exception(response.text)
            show_document_notice("Archived document permanently deleted.")
            load_archived_documents_table()
        except Exception as exc:
            show_document_notice(f"Permanent delete failed: {exc}")

    def download_selected_qr_labels():
        selected_ids = sorted(str(doc_id) for doc_id in selected_qr_document_ids if doc_id is not None)
        if not selected_ids:
            show_document_notice("Select one or more documents to download QR labels.")
            return
        try:
            response = requests.get(
                f"{BACKEND_URL}/documents/qr/labels",
                params={"ids": ",".join(selected_ids)},
                headers=get_admin_headers(),
                verify=False,
                timeout=30,
                stream=True,
            )
            if response.status_code != 200:
                raise Exception(response.text)
            download_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(download_dir, exist_ok=True)
            file_path = os.path.join(download_dir, "qr_labels.pdf")
            with open(file_path, "wb") as handle:
                handle.write(response.content)
            os.startfile(file_path)
            show_document_notice(f"Downloaded QR labels for {len(selected_ids)} selected document(s).")
        except Exception as exc:
            show_document_notice(f"QR label download failed: {exc}")

    def show_document_details(doc):
        try:
            response = requests.get(f"{BACKEND_URL}/documents/{doc.get('id')}", headers=get_admin_headers(), verify=False, timeout=10)
            if response.status_code == 200:
                doc = normalize_document(response.json())
            else:
                raise Exception(response.text)
        except Exception as exc:
            show_document_notice(f"Unable to load document details: {exc}")
            return

        qr_image = ft.Image(width=220, height=220, fit=ft.ImageFit.CONTAIN)

        def update_qr_image(document_id: int | None):
            if not document_id:
                qr_image.src_base64 = ""
                return
            try:
                response = requests.get(
                    f"{BACKEND_URL}/documents/{document_id}/qr-image",
                    headers=get_admin_headers(),
                    verify=False,
                    timeout=10,
                )
                if response.status_code != 200:
                    raise Exception(response.text)
                qr_image.src_base64 = base64.b64encode(response.content).decode("ascii")
            except Exception as exc:
                show_document_notice(f"Unable to load QR image: {exc}")
                qr_image.src_base64 = ""

        update_qr_image(doc.get("id"))
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
                                ft.Text("Scanable QR", size=12, color=ft.Colors.BLUE_GREY_600),
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
        completed_count = sum(1 for doc in documents_data if (doc.get("status") or "").lower() in {"approved", "completed"})
        archived_count = sum(1 for doc in documents_data if (doc.get("status") or "").lower() == "archived")
        summary_items = [
            {"title": "Total Documents", "value": str(total_documents), "detail": "Tracked records", "icon": ft.Icons.DESCRIPTION_OUTLINED, "accent": ft.Colors.BLUE_700},
            {"title": "Pending", "value": str(pending_count), "detail": "Awaiting attention", "icon": ft.Icons.HOURGLASS_EMPTY_OUTLINED, "accent": ft.Colors.ORANGE_700},
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
            "date_archived": doc.get("date_archived") or doc.get("archived_at") or "-",
            "archived_by": doc.get("archived_by") or "-",
            "created_by": doc.get("created_by") or "-",
            "author": doc.get("author") or "-",
            "session": doc.get("session") or "-",
            "date_registered": doc.get("date_registered") or doc.get("created_at") or "-",
            "attachment_name": doc.get("attachment_name") or "-",
            "remarks": doc.get("remarks") or "",
            "attachments": doc.get("attachments") or [],
            "archived": bool(doc.get("archived", False)),
        }

    def delete_document_record(document_id):
        try:
            response = requests.delete(f"{BACKEND_URL}/documents/{document_id}", headers=get_admin_headers(), verify=False, timeout=10)
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
            doc_id = doc.get("id")
            title_cell = ft.DataCell(
                ft.Tooltip(
                    message=document_title,
                    content=ft.Container(
                        content=ft.Text(
                            document_title,
                            size=13,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            no_wrap=True,
                        ),
                        width=260,
                        padding=ft.Padding(left=4, top=0, right=4, bottom=0),
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                )
            )
            actions = []
            if has_permission("view_document_details"):
                actions.append(ft.PopupMenuItem(content=ft.Text("View Details"), on_click=lambda _, d=doc: show_document_details(d)))
            if has_permission("download_documents"):
                actions.append(ft.PopupMenuItem(content=ft.Text("Download"), on_click=lambda _: show_document_notice("Download action preview enabled.")))
            if has_permission("edit_documents"):
                actions.append(ft.PopupMenuItem(content=ft.Text("Edit"), on_click=lambda _: show_document_notice("Edit action available.")))
            if has_permission("archive_documents"):
                actions.append(ft.PopupMenuItem(content=ft.Text("Archive Document"), on_click=lambda _, d=doc: confirm_delete_document(d)))
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(
                            ft.Checkbox(
                                value=doc_id in selected_qr_document_ids,
                                on_change=lambda e, doc_id_value=doc_id: (
                                    selected_qr_document_ids.add(doc_id_value) if e.control.value else selected_qr_document_ids.discard(doc_id_value),
                                    refresh_qr_selection_badge(),
                                ),
                            )
                        ),
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
                ft.Tooltip(
                    message=document_title,
                    content=ft.Container(
                        content=ft.Text(
                            document_title,
                            size=13,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            no_wrap=True,
                        ),
                        width=260,
                        padding=ft.Padding(left=4, top=0, right=4, bottom=0),
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                )
            )
            actions = []
            if has_permission("view_document_details"):
                actions.append(ft.PopupMenuItem(content=ft.Text("View Details"), on_click=lambda _, d=doc: show_document_details(d)))
            if include_archive_action and has_permission("archive_documents"):
                actions.append(ft.PopupMenuItem(content=ft.Text("Archive Document"), on_click=lambda _, d=doc: confirm_delete_document(d)))
            if not include_archive_action and has_permission("restore_documents"):
                actions.append(ft.PopupMenuItem(content=ft.Text("Restore Document"), on_click=lambda _, d=doc: confirm_restore_archived_document(d)))
            if not include_archive_action and has_permission("delete_documents"):
                actions.append(ft.PopupMenuItem(content=ft.Text("Delete Document"), on_click=lambda _, d=doc: confirm_permanent_delete_archived_document(d)))
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
            visible_documents = sorted(visible_documents, key=lambda doc: str(doc.get("date_archived") or doc.get("archived_at") or doc.get("date_received") or ""), reverse=False)
        elif documents_sort_filter.value == "Title":
            visible_documents = sorted(visible_documents, key=lambda doc: str(doc.get("title", "")).lower(), reverse=False)
        else:
            visible_documents = sorted(visible_documents, key=lambda doc: str(doc.get("date_archived") or doc.get("archived_at") or doc.get("date_received") or ""), reverse=True)

        rows = []
        for doc in visible_documents:
            archive_title = str(doc.get("title", "-") or "-")
            date_archived = doc.get("date_archived") or doc.get("archived_at") or doc.get("date_received") or "-"
            archived_by = doc.get("archived_by") or "-"
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(
                            ft.Container(
                                content=ft.PopupMenuButton(
                                    icon=ft.Icons.MORE_VERT,
                                    tooltip="Archived document actions",
                                    items=[
                                        *([ft.PopupMenuItem(content=ft.Text("View Details"), on_click=lambda _, d=doc: show_document_details(d))] if has_permission("view_document_details") else []),
                                        *([ft.PopupMenuItem(content=ft.Text("Restore"), on_click=lambda _, d=doc: confirm_restore_archived_document(d))] if has_permission("restore_documents") else []),
                                        *([ft.PopupMenuItem(content=ft.Text("Delete Permanently"), on_click=lambda _, d=doc: confirm_permanent_delete_archived_document(d))] if has_permission("delete_documents") else []),
                                    ],
                                ),
                                width=90,
                                alignment=ft.Alignment.CENTER,
                            )
                        ),
                        ft.DataCell(ft.Container(content=ft.Text(str(doc.get("tracking_number", doc.get("id", "-"))), size=13), width=140, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Tooltip(message=archive_title, content=ft.Container(content=ft.Text(archive_title, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True), width=300, padding=ft.Padding(left=4, top=0, right=4, bottom=0), alignment=ft.Alignment.CENTER_LEFT))),
                        ft.DataCell(ft.Container(content=ft.Text(str(doc.get("document_type", "-")), size=13), width=150, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(format_frontend_date(date_archived), size=13), width=150, alignment=ft.Alignment.CENTER_LEFT)),
                        ft.DataCell(ft.Container(content=ft.Text(str(archived_by), size=13), width=150, alignment=ft.Alignment.CENTER_LEFT)),
                    ]
                )
            )
        archived_documents_table.rows = rows
        archived_documents_empty_state.visible = len(rows) == 0
        update_document_result_indicator(visible_documents, visible_count=len(rows))
        page.update()

    def load_archived_documents_table():
        try:
            # Permission check to avoid unnecessary backend calls when user cannot view documents
            if not has_permission("view_documents"):
                archived_documents_data[:] = []
                archived_documents_table.rows = []
                archived_documents_empty_state.visible = True
                archived_documents_notice.value = "Unable to load archived documents: Permission denied"
                page.update()
                return

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
            response = requests.get(f"{BACKEND_URL}/documents", params=params, headers=get_admin_headers(), verify=False, timeout=10)
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
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                archived_documents_table,
                            ],
                            width=1600,
                            scroll=ft.ScrollMode.AUTO,
                            spacing=0,
                            alignment=ft.MainAxisAlignment.START,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        width="100%",
                        height=520,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    ),
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
            if documents_filter_priority.value and documents_filter_priority.value != "All":
                params["priority"] = documents_filter_priority.value
            if documents_filter_start_date.value:
                params["start_date"] = documents_filter_start_date.value
            if documents_filter_end_date.value:
                params["end_date"] = documents_filter_end_date.value
            response = requests.get(f"{BACKEND_URL}/documents", params=params, headers=get_admin_headers(), verify=False, timeout=10)
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
            # Check permissions locally before requesting documents to avoid backend permission errors.
            if not has_permission("view_documents"):
                documents_data[:] = []
                documents_table.rows = []
                documents_empty_state.visible = True
                documents_notice.value = "Unable to load documents: Permission denied"
                page.update()
                return

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
            if documents_filter_priority.value and documents_filter_priority.value != "All":
                params["priority"] = documents_filter_priority.value
            if documents_filter_start_date.value:
                params["start_date"] = documents_filter_start_date.value
            if documents_filter_end_date.value:
                params["end_date"] = documents_filter_end_date.value
            response = requests.get(f"{BACKEND_URL}/documents", params=params, headers=get_admin_headers(), verify=False, timeout=10)
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
        documents_filter_priority.value = "All"
        documents_sort_filter.value = "Newest"
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
                "search_field": documents_search_field if has_permission("search_documents") else None,
                "status_filter": documents_status_filter if has_permission("filter_documents") else None,
                "category_filter": documents_category_filter if has_permission("filter_documents") else None,
                "type_filter": documents_type_filter if has_permission("filter_documents") else None,
                "priority_filter": documents_filter_priority if has_permission("filter_documents") else None,
                "assigned_filter": documents_assigned_filter if has_permission("filter_documents") else None,
                "register_button": ft.Button("Register Document", icon=ft.Icons.ADD, on_click=lambda _: open_register_document_dialog()) if has_permission("register_documents") else None,
                "bulk_register_button": ft.Button("Multiple Registration", icon=ft.Icons.UPLOAD_FILE, on_click=lambda _: open_bulk_register_document_dialog()) if has_permission("import_documents") else None,
                "refresh_button": ft.Button("Refresh", icon=ft.Icons.REFRESH, on_click=lambda _: reset_document_filters()),
                "qr_monitor_button": ft.OutlinedButton("QR Monitor", icon=ft.Icons.QR_CODE_2, on_click=lambda _: open_qr_monitor()) if has_permission("view_qr_tracking") else None,
                "qr_labels_button": ft.OutlinedButton("Download QR Labels", icon=ft.Icons.PRINT, on_click=lambda _: open_qr_label_download_dialog()) if has_permission("print_qr_codes") else None,
                "export_button": None,
                "print_button": None,
                "import_button": None,
                "filter_button": ft.OutlinedButton("Apply", icon=ft.Icons.FILTER_LIST, on_click=lambda _: load_documents_table()),
                "reset_filter_button": None,
                "sort_filter": documents_sort_filter,
                "start_date_filter": documents_filter_start_date,
                "end_date_filter": documents_filter_end_date,
                "empty_state_button": None,
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
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        default_settings = {
            "appearance": {"theme": "Dark" if is_dark else "Light", "accent": "LGU Tolosa Blue"},
            "notifications": {"document_updates": True, "qr_tracking_updates": True, "document_requests": True, "account_notifications": True, "system_announcements": False},
            "document_preferences": {"default_view": "Table", "records_per_page": "25", "remember_filters": True, "confirm_destructive": True},
            "qr_tracking": {"confirm_receipt": True, "show_tracking_history": True, "scanner_sound": False, "scanner_feedback": True},
            "security": {"remember_device": True, "login_notifications": True},
        }

        try:
            saved_settings_raw = page.client_storage.get("sb_settings")
            if saved_settings_raw:
                saved_settings = json.loads(saved_settings_raw)
                for key, value in saved_settings.items():
                    if isinstance(value, dict):
                        default_settings.setdefault(key, {})
                        for nested_key, nested_value in value.items():
                            default_settings[key][nested_key] = nested_value
        except Exception:
            pass

        settings_state = default_settings

        def save_settings():
            try:
                page.client_storage.set("sb_settings", json.dumps(settings_state))
                page.snack_bar = ft.SnackBar(ft.Text("Settings saved successfully."), open=True)
                page.update()
            except Exception:
                page.snack_bar = ft.SnackBar(ft.Text("Unable to save local settings in this browser session."), open=True)
                page.update()

        def make_row(label, control, note=None):
            row_controls = [
                ft.Text(label, size=12, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200, width=220),
                control,
            ]
            if note:
                row_controls.append(ft.Text(note, size=11, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400))
            return ft.Row(row_controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True)

        def save_button_row():
            return ft.Row([
                ft.ElevatedButton("Save Changes", icon=ft.Icons.SAVE_OUTLINED, on_click=lambda _: save_settings()),
            ], alignment=ft.MainAxisAlignment.END)

        theme_dropdown = ft.Dropdown(
            value=settings_state["appearance"]["theme"],
            width=180,
            options=[
                ft.dropdown.Option("Light", "Light"),
                ft.dropdown.Option("Dark", "Dark"),
                ft.dropdown.Option("System Default", "System Default"),
            ],
        )

        def on_theme_change(_):
            selected_theme = theme_dropdown.value or "Light"
            settings_state["appearance"] = {**settings_state.get("appearance", {}), "theme": selected_theme}
            if hasattr(page, "client_storage"):
                page.client_storage.set("sb_night_mode", selected_theme == "Dark")
            page.theme_mode = ft.ThemeMode.DARK if selected_theme == "Dark" else ft.ThemeMode.LIGHT
            page.update()

        theme_dropdown.on_change = on_theme_change

        default_view_dropdown = ft.Dropdown(
            value=settings_state["document_preferences"]["default_view"],
            width=170,
            options=[ft.dropdown.Option("Table", "Table"), ft.dropdown.Option("Compact Table", "Compact Table")],
        )
        default_view_dropdown.on_change = lambda e: settings_state.__setitem__("document_preferences", {**settings_state.get("document_preferences", {}), "default_view": default_view_dropdown.value or "Table"})

        records_per_page_dropdown = ft.Dropdown(
            value=str(settings_state["document_preferences"]["records_per_page"]),
            width=120,
            options=[ft.dropdown.Option("10", "10"), ft.dropdown.Option("25", "25"), ft.dropdown.Option("50", "50")],
        )
        records_per_page_dropdown.on_change = lambda e: settings_state.__setitem__("document_preferences", {**settings_state.get("document_preferences", {}), "records_per_page": records_per_page_dropdown.value or "25"})

        appearance_card = surface_card(
            ft.Column([
                section_header("Appearance", "Customize the application's visual appearance.", ft.Icons.PALETTE_OUTLINED, ft.Colors.BLUE_700),
                ft.Divider(height=1),
                make_row("Theme", theme_dropdown),
            ], spacing=12),
            padding=18,
            expand=False,
        )

        def switch_row(label, key, section_name):
            value = settings_state.get(section_name, {}).get(key, False)

            def on_switch_change(e):
                section_state = settings_state.get(section_name, {})
                settings_state[section_name] = {**section_state, key: bool(e.control.value)}

            switch = ft.Switch(value=value, active_color=ft.Colors.BLUE_700, on_change=on_switch_change)
            return make_row(label, switch)

        notifications_card = surface_card(
            ft.Column([
                section_header("Notifications", "Control application notifications.", ft.Icons.NOTIFICATIONS_OUTLINED, ft.Colors.BLUE_700),
                ft.Divider(height=1),
                switch_row("Document Updates", "document_updates", "notifications"),
                switch_row("QR Tracking Updates", "qr_tracking_updates", "notifications"),
                switch_row("Document Requests", "document_requests", "notifications"),
                switch_row("Account Notifications", "account_notifications", "notifications"),
                switch_row("System Announcements", "system_announcements", "notifications"),
            ], spacing=10),
            padding=18,
            expand=False,
        )

        document_preferences_card = surface_card(
            ft.Column([
                section_header("Document Preferences", "Customize how documents are displayed.", ft.Icons.DESCRIPTION_OUTLINED, ft.Colors.BLUE_700),
                ft.Divider(height=1),
                make_row("Default Document View", default_view_dropdown),
                make_row("Records Per Page", records_per_page_dropdown),
                switch_row("Remember Last Used Filters", "remember_filters", "document_preferences"),
                switch_row("Confirmation Before Destructive Actions", "confirm_destructive", "document_preferences"),
            ], spacing=10),
            padding=18,
            expand=False,
        )

        qr_tracking_card = surface_card(
            ft.Column([
                section_header("QR & Tracking", "Customize QR scanning and tracking behavior.", ft.Icons.QR_CODE_2, ft.Colors.BLUE_700),
                ft.Divider(height=1),
                switch_row("Confirm Receipt After Scanning", "confirm_receipt", "qr_tracking"),
                switch_row("Show Tracking History After Scan", "show_tracking_history", "qr_tracking"),
                switch_row("Scanner Sound", "scanner_sound", "qr_tracking"),
                switch_row("Scanner Feedback", "scanner_feedback", "qr_tracking"),
            ], spacing=10),
            padding=18,
            expand=False,
        )

        def open_password_notice(_):
            page.snack_bar = ft.SnackBar(ft.Text("Password change is handled through My Account."), open=True)
            page.update()

        security_card = surface_card(
            ft.Column([
                section_header("Security", "Manage account security preferences.", ft.Icons.SECURITY, ft.Colors.BLUE_700),
                ft.Divider(height=1),
                switch_row("Remember This Device", "remember_device", "security"),
                switch_row("Login Notifications", "login_notifications", "security"),
                ft.Row([
                    ft.Text("Password", size=12, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200, width=220),
                    ft.OutlinedButton("Change Password", icon=ft.Icons.LOCK_RESET, on_click=open_password_notice),
                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
            ], spacing=10),
            padding=18,
            expand=False,
        )

        system_config_visible = has_permission("modify_system_settings") or current_user_role == "Super Administrator"
        system_configuration_card = None
        if system_config_visible:
            system_configuration_card = surface_card(
                ft.Column([
                    section_header("System Configuration", "Authorized administration settings for the application.", ft.Icons.SETTINGS_APPLICATIONS_OUTLINED, ft.Colors.BLUE_700),
                    ft.Divider(height=1),
                    ft.Text("Organization Information", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Text("LGU Tolosa Legislative Document Tracking System", size=12, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                    ft.Text("Document Configuration", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Text("Default document status, filing preferences, and office configuration remain managed by the existing system setup.", size=12, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                    ft.Text("QR Configuration", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Text("QR tracking preferences are controlled through the QR & Tracking settings card and the current tracking workflow.", size=12, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                    ft.Text("Notification Configuration", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Text("System-wide announcements and application notifications are configured from the Notifications card.", size=12, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                ], spacing=10),
                padding=18,
                expand=False,
            )

        cards = [appearance_card, notifications_card, document_preferences_card, qr_tracking_card, security_card]
        if system_configuration_card is not None:
            cards.append(system_configuration_card)
        cards.append(save_button_row())

        return ft.Column([
            surface_card(
                ft.Column([
                    section_header("Settings", "Manage your application preferences and system configuration.", ft.Icons.SETTINGS_OUTLINED, ft.Colors.BLUE_700),
                    ft.Divider(height=1),
                ], spacing=12),
                padding=18,
                expand=False,
            ),
            *cards,
        ], spacing=16, expand=False)

    def account_view():
        refresh_runtime_token_if_needed(force=True)
        refreshed_nav = build_nav_items()
        if [item[1] for item in refreshed_nav] != [item[1] for item in nav_items]:
            nav_items[:] = refreshed_nav
            render_shell(
                page,
                current_user,
                logout_user,
                nav_items,
                ft.Column([]),
                initial_selected_index=next(
                    (index for index, item in enumerate(nav_items) if item[1] == "My Account"),
                    0,
                ),
            )
            return ft.Column([])

        is_dark = page.theme_mode == ft.ThemeMode.DARK
        profile_user = {"full_name": None, "username": current_user, "email": None, "role": current_user_role or "Employee", "status": "Active", "created_at": None, "updated_at": None, "last_login": None, "id": None, "permissions": current_user_permissions or []}

        try:
            resp = requests.get(f"{BACKEND_URL}/auth/users", headers=get_admin_headers(), verify=False, timeout=15)
            if resp.status_code == 200:
                users = resp.json() or []
                for user in users:
                    username = (user.get("username") or "").strip()
                    if username and current_user and username.lower() == str(current_user).lower():
                        profile_user.update({
                            "id": user.get("id"),
                            "full_name": user.get("full_name") or user.get("username") or "Not provided",
                            "username": user.get("username") or current_user or "Not provided",
                            "email": user.get("email") or None,
                            "role": user.get("role") or (current_user_role or "Employee"),
                            "status": user.get("status") or "Active",
                            "created_at": user.get("created") or user.get("created_at") or None,
                            "updated_at": user.get("updated_at") or user.get("updated") or None,
                            "last_login": user.get("last_login") or None,
                            "permissions": user.get("permissions") or current_user_permissions or [],
                        })
                        break
        except Exception:
            pass

        def normalize_display(value, fallback="Not provided"):
            if value is None or str(value).strip() == "":
                return fallback
            return str(value).strip()

        def format_date(value):
            if not value:
                return "Not provided"
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return dt.strftime("%B %d, %Y")
            except Exception:
                return str(value)

        def format_datetime(value):
            if not value:
                return "Not provided"
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return dt.strftime("%b %d, %Y %I:%M %p")
            except Exception:
                return str(value)

        def permission_label(value):
            raw = str(value or "").strip()
            if not raw:
                return "Permission"
            return raw.replace("_", " ").title()

        normalized_permissions = []
        raw_permissions = profile_user["permissions"] or []
        if isinstance(raw_permissions, str):
            try:
                raw_permissions = json.loads(raw_permissions)
            except Exception:
                raw_permissions = [raw_permissions]
        if isinstance(raw_permissions, dict):
            raw_permissions = list(raw_permissions.keys())
        for item in raw_permissions:
            if item is None:
                continue
            normalized_permissions.append(str(item).strip())
        normalized_permissions = sorted({item for item in normalized_permissions if item})

        if current_user_role == "Super Administrator" or profile_user["role"] == "Super Administrator":
            permission_summary = ft.Text("Full System Access", weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700 if not is_dark else ft.Colors.GREEN_400)
            permission_groups = []
        else:
            permission_summary = None
            permission_groups = [
                ("Dashboard", ["view_dashboard", "view_analytics"]),
                ("Documents", ["view_documents", "search_documents", "filter_documents", "view_document_details", "register_documents", "edit_documents", "archive_documents", "restore_documents", "download_documents", "print_documents"]),
                ("QR Code", ["generate_qr_codes", "print_qr_codes", "view_qr_tracking"]),
                ("Document Requests", ["view_document_requests", "approve_document_requests", "reject_document_requests", "fulfill_document_requests"]),
                ("Audit Logs", ["view_audit_logs", "export_audit_logs"]),
                ("Analytics", ["view_analytics", "export_analytics"]),
            ]

        status_color = ft.Colors.GREEN_700 if (profile_user["status"] or "Active").lower() == "active" else ft.Colors.AMBER_700 if (profile_user["status"] or "Active").lower() == "pending" else ft.Colors.RED_700
        status_bg = ft.Colors.GREEN_50 if not is_dark else ft.Colors.with_opacity(0.18, ft.Colors.GREEN_700)
        if (profile_user["status"] or "Active").lower() not in {"active", "pending"}:
            status_bg = ft.Colors.RED_50 if not is_dark else ft.Colors.with_opacity(0.18, ft.Colors.RED_700)

        def build_permission_chips(group_name, permitted_values):
            chips = []
            if not permitted_values:
                return ft.Column([ft.Text("No assigned permissions", size=12, color=ft.Colors.BLUE_GREY_500)], spacing=6)
            for value in permitted_values:
                key = str(value).strip().lower().replace(" ", "_")
                if key in {str(p).strip().lower().replace(" ", "_") for p in normalized_permissions}:
                    chips.append(
                        ft.Container(
                            content=ft.Text(permission_label(value), size=11),
                            padding=ft.Padding(8, 4, 8, 4),
                            border_radius=999,
                            bgcolor=ft.Colors.GREEN_50 if not is_dark else ft.Colors.with_opacity(0.18, ft.Colors.GREEN_700),
                            border=ft.border.all(1, ft.Colors.GREEN_200 if not is_dark else ft.Colors.with_opacity(0.3, ft.Colors.GREEN_400)),
                        )
                    )
            if not chips:
                return ft.Text("No permissions assigned in this category.", size=12, color=ft.Colors.BLUE_GREY_500)
            return ft.Wrap(chips, spacing=8, run_spacing=8)

        def open_edit_profile_dialog():
            user_id = profile_user.get("id")
            full_name_field = ft.TextField(label="Full Name", value=profile_user.get("full_name") or "", width=260)
            email_field = ft.TextField(label="Email", value=profile_user.get("email") or "", width=260)
            note_text = ft.Text("You can update your profile details here. Username, role, and permissions remain read-only.", size=12, color=ft.Colors.BLUE_GREY_600)
            error_text = ft.Text("", size=12, color=ft.Colors.RED_700)

            def save_profile(_):
                name = (full_name_field.value or "").strip()
                email = (email_field.value or "").strip()
                if not name or not email:
                    error_text.value = "Full name and email are required."
                    page.update()
                    return
                payload = {
                    "full_name": name,
                    "username": profile_user.get("username") or current_user,
                    "email": email,
                    "role": profile_user.get("role") or current_user_role or "Employee",
                    "status": profile_user.get("status") or "Active",
                    "permissions": normalized_permissions,
                }
                if user_id is None:
                    profile_user["full_name"] = name
                    profile_user["email"] = email
                    page.snack_bar = ft.SnackBar(ft.Text("Profile updated locally for this session."), open=True)
                    page.update()
                    return
                try:
                    response = requests.put(
                        f"{BACKEND_URL}/auth/users/{user_id}",
                        json=payload,
                        headers=get_admin_headers(),
                        verify=False,
                        timeout=20,
                    )
                    if response.status_code != 200:
                        detail = response.text
                        try:
                            detail = response.json().get("detail", detail)
                        except Exception:
                            pass
                        raise ValueError(detail)
                    body = response.json()
                    profile_user["full_name"] = body.get("full_name") or name
                    profile_user["email"] = body.get("email") or email
                    page.snack_bar = ft.SnackBar(ft.Text("Profile updated successfully."), open=True)
                    page.update()
                except Exception as exc:
                    error_text.value = f"Unable to save profile: {exc}"
                    page.update()
                    return
                dialog.open = False
                page.update()

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Edit Profile"),
                content=ft.Container(
                    content=ft.Column([
                        note_text,
                        full_name_field,
                        email_field,
                        error_text,
                    ], width=420, spacing=12),
                    padding=ft.Padding(0, 0, 0, 0),
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: close_dialog(dialog)),
                    ft.Button("Save Changes", on_click=save_profile, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
                ],
            )

            def close_dialog(dialog_ref):
                dialog_ref.open = False
                page.update()

            if dialog not in page.overlay:
                page.overlay.append(dialog)
            dialog.open = True
            page.update()

        avatar_text = (profile_user["full_name"] or profile_user["username"] or "User").split()
        initials = "".join(part[0].upper() for part in avatar_text[:2]) if avatar_text else "U"
        avatar_initials = initials[:2]

        profile_header = surface_card(
            ft.Row([
                ft.Container(
                    content=ft.Text(avatar_initials, size=30, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                    width=84,
                    height=84,
                    border_radius=42,
                    bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.BLUE_700) if not is_dark else ft.Colors.with_opacity(0.2, ft.Colors.BLUE_700),
                    alignment=ft.alignment.center,
                ),
                ft.Column([
                    ft.Row([
                        ft.Text(normalize_display(profile_user["full_name"], "Not provided"), size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900 if not is_dark else ft.Colors.WHITE),
                    ], spacing=8),
                    ft.Row([
                        ft.Container(
                            content=ft.Text(normalize_display(profile_user["role"], "Employee"), size=11, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_700),
                            padding=ft.Padding(10, 4, 10, 4),
                            bgcolor=ft.Colors.BLUE_50 if not is_dark else ft.Colors.with_opacity(0.2, ft.Colors.BLUE_700),
                            border_radius=999,
                        ),
                        ft.Container(
                            content=ft.Text((profile_user["status"] or "Active").title(), size=11, weight=ft.FontWeight.W_500, color=ft.Colors.GREEN_700 if not is_dark else ft.Colors.GREEN_300),
                            padding=ft.Padding(10, 4, 10, 4),
                            bgcolor=ft.Colors.GREEN_50 if not is_dark else ft.Colors.with_opacity(0.2, ft.Colors.GREEN_700),
                            border_radius=999,
                        ),
                    ], spacing=8, wrap=True),
                    ft.Text(normalize_display(profile_user["email"], "Not provided"), size=13, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                    ft.Text(f"Username: {normalize_display(profile_user['username'], 'Not provided')}", size=13, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                ], spacing=8, expand=True),
                ft.Column([
                    ft.Text("Account Details", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_300),
                    ft.Text(f"Role: {normalize_display(profile_user['role'], 'Employee')}", size=12, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Text(f"Status: {(profile_user['status'] or 'Active').title()}", size=12, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Text(f"Created: {format_date(profile_user['created_at'])}", size=12, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Text(f"Updated: {format_date(profile_user['updated_at'])}", size=12, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=22,
            expand=False,
        )

        personal_information_card = surface_card(
            ft.Column([
                ft.Row([
                    ft.Text("Personal Information", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900 if not is_dark else ft.Colors.WHITE),
                    ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Edit profile", on_click=lambda _: open_edit_profile_dialog()),
                ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text("Update your personal account information.", size=12, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                ft.Divider(height=1),
                ft.Row([
                    ft.Column([
                        ft.Text("Full Name", size=11, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400),
                        ft.Text(normalize_display(profile_user["full_name"], "Not provided"), size=14, weight=ft.FontWeight.W_500),
                    ], expand=True),
                    ft.Column([
                        ft.Text("Username", size=11, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400),
                        ft.Text(normalize_display(profile_user["username"], "Not provided"), size=14, weight=ft.FontWeight.W_500),
                    ], expand=True),
                ], spacing=16),
                ft.Column([
                    ft.Text("Email", size=11, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400),
                    ft.Text(normalize_display(profile_user["email"], "Not provided"), size=14, weight=ft.FontWeight.W_500),
                ], spacing=4),
            ], spacing=14),
            padding=18,
            expand=False,
        )

        account_information_card = surface_card(
            ft.Column([
                ft.Text("Account Information", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900 if not is_dark else ft.Colors.WHITE),
                ft.Text("View your account details and metadata.", size=12, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                ft.Divider(height=1),
                ft.Row([
                    ft.Text("Account ID", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=150),
                    ft.Text(f"#{profile_user.get('id') or 'N/A'}", size=13, weight=ft.FontWeight.W_500),
                ]),
                ft.Row([
                    ft.Text("Role", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=150),
                    ft.Text(normalize_display(profile_user["role"], "Employee"), size=13, weight=ft.FontWeight.W_500),
                ]),
                ft.Row([
                    ft.Text("Account Status", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=150),
                    ft.Text((profile_user["status"] or "Active").title(), size=13, weight=ft.FontWeight.W_500),
                ]),
                ft.Row([
                    ft.Text("Account Created", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=150),
                    ft.Text(format_date(profile_user["created_at"]), size=13, weight=ft.FontWeight.W_500),
                ]),
                ft.Row([
                    ft.Text("Last Updated", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=150),
                    ft.Text(format_datetime(profile_user["updated_at"]), size=13, weight=ft.FontWeight.W_500),
                ]),
            ], spacing=12),
            padding=18,
            expand=False,
        )

        permission_group_controls = []
        if permission_groups:
            permission_group_controls = [
                ft.Column([
                    ft.Text(group_name, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    build_permission_chips(group_name, permitted_values),
                ], spacing=6)
                for group_name, permitted_values in permission_groups if permitted_values
            ]

        access_permissions_card = surface_card(
            ft.Column([
                ft.Text("Access & Permissions", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900 if not is_dark else ft.Colors.WHITE),
                ft.Text("Your current system role and assigned permissions.", size=12, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                ft.Divider(height=1),
                ft.Row([
                    ft.Container(content=ft.Text("Role", size=11, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300), padding=ft.Padding(8, 4, 8, 4), bgcolor=ft.Colors.BLUE_GREY_50 if not is_dark else ft.Colors.with_opacity(0.12, ft.Colors.BLUE_GREY_700), border_radius=999),
                    ft.Container(content=ft.Text(normalize_display(profile_user["role"], "Employee"), size=11, weight=ft.FontWeight.W_500), padding=ft.Padding(8, 4, 8, 4), bgcolor=ft.Colors.BLUE_50 if not is_dark else ft.Colors.with_opacity(0.14, ft.Colors.BLUE_700), border_radius=999),
                    ft.Container(content=ft.Text("Account Status", size=11, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300), padding=ft.Padding(8, 4, 8, 4), bgcolor=ft.Colors.BLUE_GREY_50 if not is_dark else ft.Colors.with_opacity(0.12, ft.Colors.BLUE_GREY_700), border_radius=999),
                    ft.Container(content=ft.Text((profile_user["status"] or "Active").title(), size=11, weight=ft.FontWeight.W_500, color=status_color), padding=ft.Padding(8, 4, 8, 4), bgcolor=status_bg, border_radius=999),
                ], spacing=8, wrap=True),
                ft.Column([
                    ft.Text("Assigned Permissions", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900 if not is_dark else ft.Colors.WHITE),
                    permission_summary if permission_summary is not None else ft.Text("", size=0),
                ], spacing=8),
                *permission_group_controls,
            ], spacing=12),
            padding=18,
            expand=False,
        )

        security_card = surface_card(
            ft.Column([
                ft.Text("Security", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900 if not is_dark else ft.Colors.WHITE),
                ft.Text("Manage your account security settings.", size=12, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
                ft.Divider(height=1),
                ft.Row([
                    ft.Text("Password", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=120),
                    ft.Text("••••••••", size=14, weight=ft.FontWeight.W_500),
                    ft.Container(content=ft.OutlinedButton("Change Password", icon=ft.Icons.LOCK_RESET), padding=0),
                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Text("Last Login", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=120),
                    ft.Text(format_datetime(profile_user["last_login"]), size=13, weight=ft.FontWeight.W_500),
                ]),
            ], spacing=12),
            padding=18,
            expand=False,
        )

        account_activity_card = surface_card(
            ft.Column([
                ft.Row([
                    ft.Text("Account Activity", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900 if not is_dark else ft.Colors.WHITE),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(height=1),
                ft.Row([
                    ft.Text("Account Created", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=150),
                    ft.Text(format_date(profile_user["created_at"]), size=13, weight=ft.FontWeight.W_500),
                ]),
                ft.Row([
                    ft.Text("Last Updated", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=150),
                    ft.Text(format_datetime(profile_user["updated_at"]), size=13, weight=ft.FontWeight.W_500),
                ]),
                ft.Row([
                    ft.Text("Last Login", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=150),
                    ft.Text(format_datetime(profile_user["last_login"]), size=13, weight=ft.FontWeight.W_500),
                ]),
                ft.Row([
                    ft.Text("Account Status", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400, width=150),
                    ft.Text((profile_user["status"] or "Active").title(), size=13, weight=ft.FontWeight.W_500),
                ]),
            ], spacing=12),
            padding=18,
            expand=False,
        )

        top_row = ft.Row([
            ft.Icon(ft.Icons.PERSON_OUTLINE, size=20, color=ft.Colors.BLUE_700),
            ft.Column([
                ft.Text("My Account", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900 if not is_dark else ft.Colors.WHITE),
                ft.Text("Manage your profile, account information, and security settings.", size=12, color=ft.Colors.BLUE_GREY_600 if not is_dark else ft.Colors.BLUE_GREY_300),
            ], spacing=2, expand=True),
            ft.ElevatedButton("Edit Profile", icon=ft.Icons.EDIT, on_click=lambda _: open_edit_profile_dialog()),
        ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        content = ft.Column([
            ft.Row([
                ft.Text("My Account", size=12, color=ft.Colors.BLUE_GREY_500 if not is_dark else ft.Colors.BLUE_GREY_400),
            ], spacing=4),
            top_row,
            profile_header,
            ft.ResponsiveRow([
                ft.Column([personal_information_card, security_card], col=6, spacing=16),
                ft.Column([account_information_card, access_permissions_card], col=6, spacing=16),
            ], run_spacing=16, spacing=16),
            account_activity_card,
        ], spacing=16, expand=False)

        return ft.Column([content], expand=False)

    def qr_tracking_view():
        open_qr_monitor()
        return ft.Column(
            [
                section_header(
                    "QR Tracking",
                    "Monitor document QR activity authorized for this account.",
                    ft.Icons.QR_CODE_2,
                    ft.Colors.BLUE_GREY_700,
                ),
                ft.OutlinedButton("Refresh QR Monitor", icon=ft.Icons.REFRESH, on_click=open_qr_monitor),
            ],
            spacing=14,
        )

    def load_user_management_data():
        nonlocal user_management_data
        previous_data = list(user_management_data)
        try:
            response = requests.get(
                f"{BACKEND_URL}/auth/users",
                headers=get_admin_headers(),
                verify=False,
                timeout=20,
            )
            if response.status_code != 200:
                detail = response.text
                try:
                    detail = response.json().get("detail", detail)
                except Exception:
                    detail = response.text
                raise Exception(f"{response.status_code}: {detail}")
            user_management_data = response.json() if response.content else []
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Unable to load users: {exc}"), open=True)
            user_management_data = previous_data
        finally:
            update_users_role_view()

    user_management_data = []

    user_table_holder = ft.Container(width="100%")
    user_no_users_notice = ft.Container(width="100%", visible=False)

    def update_users_role_view(_=None):
        visible_users = filter_user_data()
        user_table_holder.content = build_users_roles_table(
            visible_users,
            lambda item=None: open_view_user_dialog(item or visible_users[0] if visible_users else {}),
            lambda item=None: open_edit_user_dialog(item or visible_users[0] if visible_users else {}),
            lambda item=None: open_reset_password_dialog(item or visible_users[0] if visible_users else {}),
            lambda item=None: delete_user(item or visible_users[0] if visible_users else {}),
        )
        user_no_users_notice.visible = len(visible_users) == 0
        page.update()

    def refresh_user_management_data(_=None):
        load_user_management_data()

    user_search_field = ft.TextField(
        label="Search users...",
        width=260,
        prefix_icon=ft.Icon(ft.Icons.SEARCH, size=18),
        on_change=update_users_role_view,
    )
    user_role_filter = ft.Dropdown(
        label="Role",
        width=180,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("Employee"),
            ft.dropdown.Option("SB Member"),
            ft.dropdown.Option("Super Administrator"),
        ],
        value="All",
        on_change=update_users_role_view,
    )
    user_status_filter = ft.Dropdown(
        label="Account Status",
        width=180,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("Active"),
            ft.dropdown.Option("Inactive"),
        ],
        value="All",
        on_change=update_users_role_view,
    )
    user_permission_filter = ft.Dropdown(
        label="Permission",
        width=260,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("View Documents"),
            ft.dropdown.Option("Search Documents"),
            ft.dropdown.Option("Filter Documents"),
            ft.dropdown.Option("View Document Details"),
            ft.dropdown.Option("Download Documents"),
            ft.dropdown.Option("Print Documents"),
            ft.dropdown.Option("Register Documents"),
            ft.dropdown.Option("Edit Documents"),
            ft.dropdown.Option("Delete Documents"),
            ft.dropdown.Option("Archive Documents"),
            ft.dropdown.Option("Restore Documents"),
            ft.dropdown.Option("Generate QR Codes"),
            ft.dropdown.Option("Print QR Codes"),
            ft.dropdown.Option("View QR Tracking"),
            ft.dropdown.Option("Create Users"),
            ft.dropdown.Option("Edit Users"),
            ft.dropdown.Option("Reset Passwords"),
            ft.dropdown.Option("Activate Users"),
            ft.dropdown.Option("Deactivate Users"),
            ft.dropdown.Option("Delete Users"),
            ft.dropdown.Option("Assign Roles"),
            ft.dropdown.Option("Manage Permissions"),
            ft.dropdown.Option("Add Committee"),
            ft.dropdown.Option("Edit Committee"),
            ft.dropdown.Option("Delete Committee"),
            ft.dropdown.Option("View Audit Logs"),
            ft.dropdown.Option("Export Audit Logs"),
            ft.dropdown.Option("Modify System Settings"),
        ],
        value="All",
        on_change=update_users_role_view,
    )
    user_office_filter = ft.Dropdown(
        label="Department/Office",
        width=180,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("SB Secretariat"),
            ft.dropdown.Option("Office of the Mayor"),
            ft.dropdown.Option("Committee on Health"),
        ],
        value="All",
        on_change=update_users_role_view,
    )

    def filter_user_data():
        query = (user_search_field.value or "").strip().lower()
        terms = [term for term in query.split() if term]
        role_value = user_role_filter.value or "All"
        status_value = user_status_filter.value or "All"
        office_value = user_office_filter.value or "All"
        visible = []

        def matches_term(item, term):
            if not term:
                return True
            fields = [
                (item.get("full_name") or "").lower(),
                (item.get("username") or "").lower(),
                (item.get("email") or "").lower(),
                (item.get("role") or "").lower(),
                (item.get("status") or "").lower(),
                (item.get("department") or "").lower(),
            ]
            fields.extend((p or "").lower() for p in (item.get("permissions") or []))
            if "@" in term:
                return any(term in field for field in fields)
            return any(term in field for field in fields)

        for item in user_management_data:
            if terms and not all(matches_term(item, term) for term in terms):
                continue
            if role_value != "All" and item.get("role") != role_value:
                continue
            if status_value != "All" and item.get("status") != status_value:
                continue
            if office_value != "All" and item.get("department") != office_value:
                continue
            permission_value = user_permission_filter.value or "All"
            if permission_value != "All":
                permissions = [p.lower() for p in (item.get("permissions") or [])]
                if permission_value.lower() not in permissions:
                    continue
            visible.append(item)
        return visible

    def users_roles_view():
        load_user_management_data()
        visible_users = filter_user_data()

        create_button = ft.Button(
            "+ Create User",
            on_click=lambda _: open_create_user_dialog(),
            bgcolor=ft.Colors.BLUE_800,
            color=ft.Colors.WHITE,
        )
        refresh_button = ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=refresh_user_management_data)
        view = build_users_roles_view(
            visible_users,
            user_search_field,
            user_role_filter,
            user_status_filter,
            user_office_filter,
            user_permission_filter,
            create_button,
            refresh_button,
            lambda _: open_create_user_dialog(),
            lambda _, item=None: open_view_user_dialog(item or visible_users[0] if visible_users else {}),
            lambda _, item=None: open_edit_user_dialog(item or visible_users[0] if visible_users else {}),
            lambda _, item=None: open_reset_password_dialog(item or visible_users[0] if visible_users else {}),
            lambda _, item=None: delete_user(item or visible_users[0] if visible_users else {}),
            page,
            surface_card,
            section_header,
            user_table_holder,
            user_no_users_notice,
        )
        update_users_role_view()
        return view

    def open_create_user_dialog():
        full_name = ft.TextField(label="Full Name")
        username = ft.TextField(label="Username")
        email = ft.TextField(label="Email")
        password = ft.TextField(label="Temporary Password", password=True, can_reveal_password=True)
        confirm_password = ft.TextField(label="Confirm Password", password=True, can_reveal_password=True)
        role_choice = ft.Dropdown(
            label="Role",
            options=[
                ft.dropdown.Option("Employee"),
                ft.dropdown.Option("SB Member"),
            ],
            value="Employee",
        )

        permission_area = ft.Column([], spacing=8)
        selected_create_permissions = set()
        create_master_check = ft.Checkbox(label="Select All Permissions", tristate=True, scale=1.05)

        def create_permission_key(label):
            return label.strip().lower().replace(" ", "_")

        def update_create_master():
            total = sum(len(items) for items in EMPLOYEE_PERMISSION_GROUPS.values())
            count = len(selected_create_permissions)
            create_master_check.value = True if count == total else None if count else False

        def set_all_create_permissions(event):
            selected_create_permissions.clear()
            if event.control.value:
                selected_create_permissions.update(create_permission_key(label) for labels in EMPLOYEE_PERMISSION_GROUPS.values() for label in labels)
            render_permission_section()

        def render_permission_section():
            permission_area.controls.clear()
            if role_choice.value == "Employee":
                permission_area.controls.append(ft.Text("Employee Permissions", weight=ft.FontWeight.BOLD, size=16, color=ft.Colors.BLUE_GREY_800))
                permission_area.controls.append(ft.Text("Control access to the features available to this employee.", size=12, color=ft.Colors.BLUE_GREY_600))
                permission_area.controls.append(ft.Row([create_master_check, ft.Text(f"{len(selected_create_permissions)} of {sum(len(items) for items in EMPLOYEE_PERMISSION_GROUPS.values())} permissions selected", size=12)], spacing=12))
                for section_name, perms in EMPLOYEE_PERMISSION_GROUPS.items():
                    group_key = section_name
                    group_count = sum(create_permission_key(perm) in selected_create_permissions for perm in perms)
                    group_check = ft.Checkbox(label=f"Select All  •  {group_count} of {len(perms)} selected", tristate=True, value=True if group_count == len(perms) else None if group_count else False, on_change=lambda event, name=group_key: set_create_group(name, event))
                    permission_area.controls.append(
                        ft.Container(
                            content=ft.ExpansionTile(
                                title=ft.Text(section_name, weight=ft.FontWeight.BOLD, size=13),
                                subtitle=ft.Text(f"{len(perms)} permissions", size=11),
                                leading=ft.Icon(ft.Icons.FOLDER_OUTLINED, color=ft.Colors.BLUE_700),
                                controls=[ft.Column([ft.Row([ft.Checkbox(label=perm, value=create_permission_key(perm) in selected_create_permissions, scale=0.9, on_change=lambda event, key=create_permission_key(perm): update_create_permission(key, event)),], spacing=0) for perm in perms], spacing=2), ft.Row([group_check], spacing=8)],
                                initially_expanded=False,
                                maintain_state=True,
                                bgcolor=ft.Colors.BLUE_GREY_50,
                                collapsed_bgcolor=ft.Colors.WHITE,
                            ),
                            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                            border_radius=10,
                        )
                    )
            else:
                permission_area.controls.append(ft.Text("SB Member Access", weight=ft.FontWeight.BOLD, size=13, color=ft.Colors.BLUE_GREY_800))
                permission_area.controls.append(ft.Column([
                    ft.Checkbox(label="View Documents", value=True, disabled=True),
                    ft.Checkbox(label="Search Documents", value=True, disabled=True),
                    ft.Checkbox(label="Filter Documents", value=True, disabled=True),
                    ft.Checkbox(label="View Document Details", value=True, disabled=True),
                    ft.Checkbox(label="Download Documents", value=True, disabled=True),
                    ft.Checkbox(label="Print Documents", value=True, disabled=True),
                ], spacing=6))
                permission_area.controls.append(ft.Text("SB Members do not have QR Tracking, registration, editing, or user-management access.", size=11, color=ft.Colors.BLUE_GREY_600))
            page.update()

        def update_create_permission(key, event):
            if event.control.value:
                selected_create_permissions.add(key)
            else:
                selected_create_permissions.discard(key)
            update_create_master()
            render_permission_section()

        def set_create_group(group_name, event):
            for label in EMPLOYEE_PERMISSION_GROUPS[group_name]:
                key = create_permission_key(label)
                if event.control.value:
                    selected_create_permissions.add(key)
                else:
                    selected_create_permissions.discard(key)
            update_create_master()
            render_permission_section()

        role_choice.on_change = lambda _: render_permission_section()
        create_master_check.on_change = set_all_create_permissions
        render_permission_section()

        def create_account(_):
            if not full_name.value or not username.value or not email.value:
                error_message.value = "Full name, username, and email are required."
                page.update()
                return

            if password.value != confirm_password.value:
                error_message.value = "Passwords do not match."
                page.update()
                return

            if not password.value:
                error_message.value = "Password is required."
                page.update()
                return

            if not runtime_token and not AUTH_TOKEN:
                error_message.value = "Unable to register user: no admin authentication available."
                page.update()
                return

            permissions = sorted(selected_create_permissions)

            payload = {
                "username": username.value.strip(),
                "password": password.value,
                "full_name": full_name.value.strip(),
                "email": email.value.strip(),
                "role": role_choice.value,
            }
            if permissions:
                payload["permissions"] = str(permissions)

            try:
                response = requests.post(
                    f"{BACKEND_URL}/auth/register",
                    json=payload,
                    headers=get_admin_headers(),
                    verify=False,
                    timeout=20,
                )
                if response.status_code != 200:
                    detail = response.text
                    try:
                        detail = response.json().get("detail", detail)
                    except Exception:
                        pass
                    raise Exception(detail)
                body = response.json()
                created_user = {
                    "full_name": full_name.value,
                    "username": body.get("username", username.value.strip()),
                    "email": email.value,
                    "role": body.get("role", role_choice.value),
                    "status": "Active",
                    "permissions": permissions,
                    "last_login": "—",
                    "created": date.today().strftime("%Y-%m-%d"),
                }
                user_management_data.append(created_user)
                close_dialog(dialog)
                update_users_role_view()
            except Exception as exc:
                error_message.value = f"Account creation failed: {exc}"
                page.update()
                return

        error_message = ft.Text("", color=ft.Colors.RED_700, size=12)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Create User Account"),
            content=ft.Container(
                content=ft.Column([
                    full_name,
                    username,
                    email,
                    password,
                    confirm_password,
                    role_choice,
                    permission_area,
                    error_message,
                ], width=560, scroll=ft.ScrollMode.ALWAYS, spacing=10),
                width=580,
                height=640,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: close_dialog(dialog)),
                ft.Button("Create Account", on_click=create_account, bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE),
            ],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def open_view_user_dialog(user):
        role = user.get("role", "Employee")
        access_summary = ft.Column([])
        if role == "Super Administrator":
            access_summary.controls.append(ft.Text("Full System Access", weight=ft.FontWeight.BOLD, size=14))
            access_summary.controls.append(ft.Text("All permissions are permanently enabled.", color=ft.Colors.BLUE_GREY_700))
        elif role == "SB Member":
            access_summary.controls.append(ft.Text("Read-Only Access", weight=ft.FontWeight.BOLD, size=14))
            for item in ["View Documents", "Search Documents", "Filter Documents", "View Document Details", "Download Documents", "Print Documents"]:
                access_summary.controls.append(ft.Checkbox(label=item, value=True, disabled=True, scale=0.9))
        else:
            access_summary.controls.append(ft.Text("Assigned Permissions", weight=ft.FontWeight.BOLD, size=14))
            for perm in user.get("permissions") or ["View Documents"]:
                access_summary.controls.append(ft.Checkbox(label=perm, value=True, disabled=True, scale=0.9))

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("User Details"),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("User Information", weight=ft.FontWeight.BOLD, size=16),
                    ft.Text(f"Full Name: {user.get('full_name', '-')}") ,
                    ft.Text(f"Username: {user.get('username', '-')}") ,
                    ft.Text(f"Email: {user.get('email', '-')}") ,
                    ft.Text(f"Role: {user.get('role', '-')}") ,
                    ft.Text(f"Account Status: {user.get('status', 'Active')}") ,
                    ft.Text(f"Created Date: {user.get('created', '-')}") ,
                    ft.Text(f"Last Login: {user.get('last_login', '-')}") ,
                    ft.Divider(height=1),
                    ft.Text("Access Summary", weight=ft.FontWeight.BOLD, size=16),
                    access_summary,
                ], width=520, spacing=8),
                width=560,
            ),
            actions=[ft.TextButton("Close", on_click=lambda _: close_dialog(dialog))],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def open_edit_user_dialog(user):
        if user.get("role") == "Super Administrator":
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Super Administrator"),
                content=ft.Column([
                    ft.Text("Full system access", weight=ft.FontWeight.BOLD),
                    ft.Text("All permissions are permanently enabled."),
                    ft.Checkbox(label="Full Access", value=True, disabled=True),
                ], width=420, spacing=10),
                actions=[ft.TextButton("Close", on_click=lambda _: close_dialog(dialog))],
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()
            return

        full_name = ft.TextField(label="Full Name", value=user.get("full_name", ""), width=270)
        username = ft.TextField(label="Username", value=user.get("username", ""), width=270)
        email = ft.TextField(label="Email", value=user.get("email", ""), width=270)
        role_choice = ft.Dropdown(
            label="Role",
            value=user.get("role", "Employee"),
            options=[ft.dropdown.Option("Employee"), ft.dropdown.Option("SB Member")],
            width=270,
            autofocus=False,
        )
        status_choice = ft.Dropdown(
            label="Account Status",
            value=user.get("status", "Active"),
            options=[ft.dropdown.Option("Active"), ft.dropdown.Option("Inactive")],
            width=270,
            autofocus=False,
        )
        permissions_area = ft.Column([], spacing=8)
        error_message = ft.Text("", color=ft.Colors.RED_700, size=12)
        permission_groups = EMPLOYEE_PERMISSION_GROUPS
        group_descriptions = {
            "Dashboard": "Control access to dashboard information.",
            "Documents": "Control actions employees can perform on legislative documents.",
            "QR Code": "Control QR code generation, printing, and tracking access.",
            "Document Requests": "Control access to document request processing.",
            "Users & Roles": "Control employee access to user and role administration.",
            "Committees": "Control committee management permissions.",
            "Audit Logs": "Control access to system activity records.",
            "Analytics": "Control access to analytics and reports.",
            "Settings": "Control access to system configuration.",
        }
        permission_key = lambda label: label.strip().lower().replace(" ", "_")
        raw_permissions = user.get("permissions") or []
        if isinstance(raw_permissions, str):
            try:
                raw_permissions = json.loads(raw_permissions)
            except (TypeError, ValueError):
                try:
                    raw_permissions = ast.literal_eval(raw_permissions)
                except (SyntaxError, ValueError):
                    raw_permissions = [raw_permissions]
        selected_permissions = {permission_key(str(item)) for item in raw_permissions}
        permission_checks = {}
        group_checks = {}
        permission_cards = ft.Column(spacing=8, expand=False)
        permission_search = ft.TextField(label="Search permissions...", prefix_icon=ft.Icons.SEARCH, dense=True)
        permission_summary = ft.Text(size=12, color=ft.Colors.BLUE_GREY_600)
        master_check = ft.Checkbox(label="Select All Permissions", tristate=True, scale=1.05)
        rendering_permissions = False
        expanded_groups = set()
        group_switchers = {}
        group_arrows = {}

        def update_permission_state():
            nonlocal rendering_permissions
            if rendering_permissions:
                return
            rendering_permissions = True
            selected_count = sum(1 for checkbox in permission_checks.values() if checkbox.value)
            total_count = len(permission_checks)
            permission_summary.value = f"{selected_count} of {total_count} permissions selected"
            master_check.value = True if selected_count == total_count and total_count else None if selected_count else False
            for group_name, labels in permission_groups.items():
                count = sum(1 for label in labels if permission_checks[permission_key(label)].value)
                group_checks[group_name].value = True if count == len(labels) else None if count else False
                group_checks[group_name].label = f"Select All  •  {count} of {len(labels)} selected"
            rendering_permissions = False

        def set_group_permissions(group_name, value):
            nonlocal rendering_permissions
            rendering_permissions = True
            for label in permission_groups[group_name]:
                permission_checks[permission_key(label)].value = bool(value)
            rendering_permissions = False
            render_permission_cards()

        def set_all_permissions(value):
            nonlocal rendering_permissions
            rendering_permissions = True
            for checkbox in permission_checks.values():
                checkbox.value = bool(value)
            rendering_permissions = False
            render_permission_cards()

        def render_permission_cards(_=None):
            permission_cards.controls.clear()
            search_text = (permission_search.value or "").strip().lower()
            for group_name, labels in permission_groups.items():
                matching_labels = [label for label in labels if not search_text or search_text in label.lower() or search_text in group_name.lower()]
                if not matching_labels:
                    continue
                permission_list = ft.Column(
                    [
                        ft.Checkbox(
                            label=label,
                            value=permission_checks[permission_key(label)].value,
                            active_color=ft.Colors.BLUE_700,
                            on_change=lambda event, key=permission_key(label): permission_changed(key, event),
                        )
                        for label in matching_labels
                    ],
                    spacing=2,
                )
                def toggle_group(_=None, name=group_name):
                    if name in expanded_groups:
                        expanded_groups.remove(name)
                    else:
                        expanded_groups.add(name)
                    group_arrows[name].name = ft.Icons.KEYBOARD_ARROW_DOWN if name in expanded_groups else ft.Icons.KEYBOARD_ARROW_RIGHT
                    group_switchers[name].content = group_body if name in expanded_groups else ft.Container(height=0)
                    group_switchers[name].update()
                    group_arrows[name].update()

                group_header = ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN if group_name in expanded_groups else ft.Icons.KEYBOARD_ARROW_RIGHT, color=ft.Colors.BLUE_700),
                            ft.Icon(ft.Icons.FOLDER_OUTLINED, color=ft.Colors.BLUE_700),
                            ft.Column([
                                ft.Text(group_name, weight=ft.FontWeight.BOLD, size=13),
                                ft.Text(group_descriptions[group_name], size=11, color=ft.Colors.BLUE_GREY_600),
                            ], spacing=2, expand=True),
                            ft.Text(f"{sum(1 for label in labels if permission_checks[permission_key(label)].value)} / {len(labels)} selected", size=11, color=ft.Colors.BLUE_GREY_600),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(left=12, top=8, right=12, bottom=8),
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    on_click=toggle_group,
                )
                group_body = ft.Column(
                    [
                        ft.Row([group_checks[group_name], ft.Text(f"{len(labels)} permissions", size=11, color=ft.Colors.BLUE_GREY_600)], spacing=8),
                        permission_list,
                    ],
                    spacing=6,
                )
                group_switcher = ft.AnimatedSwitcher(
                    content=group_body if group_name in expanded_groups else ft.Container(height=0),
                    duration=220,
                    reverse_duration=180,
                    transition=ft.AnimatedSwitcherTransition.FADE,
                )
                group_arrows[group_name] = group_header.content.controls[0]
                group_switchers[group_name] = group_switcher
                permission_cards.controls.append(
                    ft.Container(
                        content=ft.Column([group_header, group_switcher], spacing=0),
                        border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                        border_radius=10,
                    )
                )
            update_permission_state()
            page.update()
            """
                        group_body = ft.Column(
                            [
                                group_check,
                                ft.Column([
                                    ft.Checkbox(
                                        label=perm,
                                        value=create_permission_key(perm) in selected_create_permissions,
                                        scale=0.9,
                                        on_change=lambda event, key=create_permission_key(perm): update_create_permission(key, event),
                                    )
                                    for perm in perms
                                ], spacing=2),
                            ],
                            spacing=6,
                            visible=section_name in expanded_groups,
                        )
                        group_header = ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN if section_name in expanded_groups else ft.Icons.KEYBOARD_ARROW_RIGHT, color=ft.Colors.BLUE_700),
                                ft.Icon(ft.Icons.FOLDER_OUTLINED, color=ft.Colors.BLUE_700),
                                ft.Text(section_name, weight=ft.FontWeight.BOLD, size=13, expand=True),
                                ft.Text(f"{group_count} / {len(perms)} selected", size=11, color=ft.Colors.BLUE_GREY_600),
                            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            padding=ft.Padding(left=12, top=8, right=12, bottom=8),
                            bgcolor=ft.Colors.BLUE_GREY_50,
                            on_click=lambda _, name=section_name: (expanded_groups.remove(name) if name in expanded_groups else expanded_groups.add(name), render_permission_section()),
                        )

        def permission_changed(key, event):
                                content=ft.Column([group_header, group_body], spacing=0),
                active_color=ft.Colors.BLUE_700,
                on_change=lambda event, name=group_name: set_group_permissions(name, event.control.value),
            )
            for label in labels:
                key = permission_key(label)
                permission_checks[key] = ft.Checkbox(label=label, value=key in selected_permissions)

        master_check.on_change = lambda event: set_all_permissions(event.control.value)
                        ft.Checkbox(label="Search Documents", value=True, disabled=True),
                        ft.Checkbox(label="Filter Documents", value=True, disabled=True),
                        ft.Checkbox(label="View Document Details", value=True, disabled=True),
                        ft.Checkbox(label="Download Documents", value=True, disabled=True),
                        ft.Checkbox(label="Print Documents", value=True, disabled=True),
                    ], spacing=6))
                    permission_area.controls.append(ft.Text("SB Members do not have QR Tracking, registration, editing, or user-management access.", size=11, color=ft.Colors.BLUE_GREY_600))
                page.update()

            def update_create_permission(key, event):
                if event.control.value:
                    selected_create_permissions.add(key)
                else:
                    selected_create_permissions.discard(key)
                update_create_master()
                render_permission_section()

            def set_create_group(group_name, event):
                for label in EMPLOYEE_PERMISSION_GROUPS[group_name]:
                    key = create_permission_key(label)
                    if event.control.value:
                        selected_create_permissions.add(key)
                    else:
                        selected_create_permissions.discard(key)
                update_create_master()
                render_permission_section()

            role_choice.on_change = lambda _: render_permission_section()
            create_master_check.on_change = set_all_create_permissions
            render_permission_section()

            def create_account(_):
                if not full_name.value or not username.value or not email.value:
                    error_message.value = "Full name, username, and email are required."
                    page.update()
                    return

                if password.value != confirm_password.value:
                    error_message.value = "Passwords do not match."
                    page.update()
                    return

                if not password.value:
                    error_message.value = "Password is required."
                    page.update()
                    return

                if not runtime_token and not AUTH_TOKEN:
                    error_message.value = "Unable to register user: no admin authentication available."
                    page.update()
                    return

                permissions = sorted(selected_create_permissions)

                payload = {
                    "username": username.value.strip(),
                    "password": password.value,
                    "full_name": full_name.value.strip(),
                    "email": email.value.strip(),
                    "role": role_choice.value,
                }
                if permissions:
                    payload["permissions"] = str(permissions)

                try:
                    response = requests.post(
                        f"{BACKEND_URL}/auth/register",
                        json=payload,
                        headers=get_admin_headers(),
                        verify=False,
                        timeout=20,
                    )
                    if response.status_code != 200:
                        detail = response.text
                        try:
                            detail = response.json().get("detail", detail)
                        except Exception:
                            pass
                        raise Exception(detail)
                    body = response.json()
                    created_user = {
                        "full_name": full_name.value,
                        "username": body.get("username", username.value.strip()),
                        "email": email.value,
                        "role": body.get("role", role_choice.value),
                        "status": "Active",
                        "permissions": permissions,
                        "last_login": "-",
                        "created": date.today().strftime("%Y-%m-%d"),
                    }
                    user_management_data.append(created_user)
                    close_dialog(dialog)
                    update_users_role_view()
                except Exception as exc:
                    error_message.value = f"Account creation failed: {exc}"
                    page.update()
                    return

            error_message = ft.Text("", color=ft.Colors.RED_700, size=12)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Create User Account"),
                content=ft.Container(
                    content=ft.Column([
                        full_name,
                        username,
                        email,
                        password,
                        confirm_password,
                        role_choice,
                        permission_area,
                        error_message,
                    ], width=560, scroll=ft.ScrollMode.ALWAYS, spacing=10),
                    width=580,
                    height=640,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: close_dialog(dialog)),
                    ft.Button("Create Account", on_click=create_account, bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE),
                ],
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        def open_view_user_dialog(user):
        permission_search.on_change = render_permission_cards
        render_permission_cards()

        """
        def permission_changed(key, event):
            permission_checks[key].value = event.control.value
            render_permission_cards()

        for group_name, labels in permission_groups.items():
            group_checks[group_name] = ft.Checkbox(
                label="Select All",
                tristate=True,
                active_color=ft.Colors.BLUE_700,
                on_change=lambda event, name=group_name: set_group_permissions(name, event.control.value),
            )
            for label in labels:
                key = permission_key(label)
                permission_checks[key] = ft.Checkbox(label=label, value=key in selected_permissions)

        master_check.on_change = lambda event: set_all_permissions(event.control.value)
        permission_search.on_change = render_permission_cards
        render_permission_cards()

        def collect_permissions():
            return [key for key, checkbox in permission_checks.items() if checkbox.value]

        def save_user(_):
            if not full_name.value.strip() or not username.value.strip() or not email.value.strip():
                error_message.value = "Full name, email, and username are required."
                page.update()
                return
            payload = {
                "full_name": full_name.value.strip(),
                "username": username.value.strip(),
                "email": email.value.strip(),
                "role": role_choice.value,
                "status": status_choice.value,
                "permissions": collect_permissions(),
            }
            try:
                response = requests.put(
                    f"{BACKEND_URL}/auth/users/{user.get('id')}",
                    json=payload,
                    headers=get_admin_headers(),
                    verify=False,
                    timeout=20,
                )
                if response.status_code != 200:
                    detail = response.text
                    try:
                        detail = response.json().get("detail", detail)
                    except Exception:
                        pass
                    raise Exception(detail)
                close_dialog(dialog)
                load_user_management_data()
            except Exception as exc:
                error_message.value = f"Unable to save user: {exc}"
                page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Edit User"),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Manage account information and permissions", size=12, color=ft.Colors.BLUE_GREY_600),
                    ft.Text("Account Information", weight=ft.FontWeight.BOLD, size=14),
                    ft.Row([full_name, username], spacing=10),
                    ft.Row([email, role_choice], spacing=10),
                    status_choice,
                    error_message,
                    ft.Divider(height=1),
                    ft.Text("Employee Permissions", weight=ft.FontWeight.BOLD, size=16),
                    ft.Text("Control access to the features available to this employee.", size=12, color=ft.Colors.BLUE_GREY_600),
                    permission_search,
                    ft.Row([master_check, permission_summary], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    permission_cards,
                ], width=560, spacing=10, scroll=ft.ScrollMode.ALWAYS),
                width=580,
                height=650,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: close_dialog(dialog)),
                ft.Button("Save Changes", on_click=save_user, bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE),
            ],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def open_reset_password_dialog(user):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Reset Password"),
            content=ft.Column([
                ft.Text("Are you sure you want to reset this user's password?"),
                ft.Text(f"User: {user.get('full_name', 'Unknown User')} ({user.get('username', '')})", color=ft.Colors.BLUE_GREY_700),
            ], tight=True, spacing=8),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: close_dialog(dialog)),
                ft.Button("Reset Password", on_click=lambda _: close_dialog(dialog), bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE),
            ],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def delete_user(user):
        if user.get("role") == "Super Administrator":
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Protected Account"),
                content=ft.Text("The Super Administrator account cannot be deleted from this interface."),
                actions=[ft.TextButton("Close", on_click=lambda _: close_dialog(dialog))],
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()
            return

        def confirm_delete():
            try:
                response = requests.delete(
                    f"{BACKEND_URL}/auth/users/{user.get('id')}",
                    headers=get_admin_headers(),
                    verify=False,
                    timeout=15,
                )
                if response.status_code != 200:
                    detail = response.text
                    try:
                        detail = response.json().get("detail", detail)
                    except Exception:
                        pass
                    raise Exception(detail)
                close_dialog(dialog)
                load_user_management_data()
            except Exception as exc:
                close_dialog(dialog)
                page.snack_bar = ft.SnackBar(ft.Text(f"Unable to delete account: {exc}"), open=True)
                page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delete Account"),
            content=ft.Text(f"Permanently delete {user.get('full_name', user.get('username', 'this user'))}? This cannot be undone."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: close_dialog(dialog)),
                ft.Button("Delete", on_click=lambda _: confirm_delete(), bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE),
            ],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def close_dialog(dialog):
        dialog.open = False
        page.update()

    def users_role_page():
        return users_roles_view()

    def logout_user():
        nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
        current_user = None
        current_user_role = None
        current_user_permissions = []
        runtime_token = None
        refresh_token = None
        clear_session_state()
        show_login()

    def archived_documents_view():
        return build_archived_documents_view()

    def open_documents_module():
        target_index = next((idx for idx, (_, label, _) in enumerate(nav_items) if label == "Documents"), 0)
        render_shell(page, current_user, logout_user, nav_items, documents_view(), initial_selected_index=target_index)

    def open_archived_documents_module():
        target_index = next((idx for idx, (_, label, _) in enumerate(nav_items) if label == "Archived Documents"), 1)
        render_shell(page, current_user, logout_user, nav_items, archived_documents_view(), initial_selected_index=target_index)

    def dashboard_view():
        try:
            load_documents_table()
            load_archived_documents_table()
        except Exception:
            pass

        total_docs = len(documents_data) + len(archived_documents_data)
        active_docs = sum(1 for doc in documents_data if (doc.get("status") or "").lower() not in {"approved", "completed", "archived"})
        pending_docs = sum(1 for doc in documents_data if (doc.get("status") or "").lower() == "pending")
        completed_docs = sum(1 for doc in documents_data if (doc.get("status") or "").lower() in {"approved", "completed"})
        archived_docs = len(archived_documents_data)
        users_total = len(user_management_data)
        users_active = sum(1 for user in user_management_data if (user.get("status") or "").lower() == "active")
        users_employees = sum(1 for user in user_management_data if user.get("role") == "Employee")
        users_sb_members = sum(1 for user in user_management_data if user.get("role") == "SB Member")
        summary_items = [
            {"title": "Total Records", "value": str(total_docs), "detail": "Active + archived documents", "icon": ft.Icons.DESCRIPTION_OUTLINED, "accent": ft.Colors.BLUE_700},
            {"title": "Active Documents", "value": str(active_docs), "detail": "Currently in process", "icon": ft.Icons.LIBRARY_ADD_CHECK_OUTLINED, "accent": ft.Colors.GREEN_700},
            {"title": "Pending", "value": str(pending_docs), "detail": "Awaiting action", "icon": ft.Icons.SCHEDULE_OUTLINED, "accent": ft.Colors.ORANGE_700},
            {"title": "Completed", "value": str(completed_docs), "detail": "Finished workflows", "icon": ft.Icons.CHECK_CIRCLE_OUTLINED, "accent": ft.Colors.TEAL_700},
            {"title": "Archived", "value": str(archived_docs), "detail": "Stored records", "icon": ft.Icons.ARCHIVE_OUTLINED, "accent": ft.Colors.BLUE_GREY_700},
        ]

        user_cards = [
            {"title": "Total Users", "value": str(users_total), "detail": "All configured accounts", "icon": ft.Icons.PEOPLE_ALT_OUTLINED, "accent": ft.Colors.BLUE_700},
            {"title": "Active Users", "value": str(users_active), "detail": "Currently enabled accounts", "icon": ft.Icons.CHECK_CIRCLE_OUTLINED, "accent": ft.Colors.GREEN_700},
            {"title": "Employees", "value": str(users_employees), "detail": "Employee accounts", "icon": ft.Icons.WORK_OUTLINED, "accent": ft.Colors.INDIGO_700},
            {"title": "SB Members", "value": str(users_sb_members), "detail": "Read-only members", "icon": ft.Icons.GROUP_OUTLINED, "accent": ft.Colors.PURPLE_700},
        ]

        def metric_card(item):
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(item["icon"], color=item["accent"], size=21),
                                    padding=9,
                                    bgcolor=ft.Colors.BLUE_GREY_50,
                                    border_radius=10,
                                ),
                                ft.Text(item["title"], size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_800),
                            ],
                            spacing=9,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(item["value"], size=26, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                        ft.Text(item["detail"], size=11, color=ft.Colors.BLUE_GREY_600),
                    ],
                    spacing=8,
                ),
                padding=14,
                bgcolor=ft.Colors.WHITE,
                border=ft.border.only(bottom=ft.border.all(3, item["accent"])),
                border_radius=12,
                width=220,
            )

        def quick_action(label, detail, icon, color, on_click):
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, color=ft.Colors.WHITE, size=25),
                        ft.Column(
                            [
                                ft.Text(label, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                ft.Text(detail, size=11, color=ft.Colors.BLUE_GREY_100),
                            ],
                            spacing=3,
                        ),
                        ft.Icon(ft.Icons.ARROW_FORWARD, color=ft.Colors.WHITE, size=20),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(14, 13, 14, 13),
                bgcolor=color,
                border_radius=10,
                on_click=on_click,
                width=300,
            )

        buttons = [
            quick_action("Documents", "Manage all documents", ft.Icons.DESCRIPTION_OUTLINED, ft.Colors.BLUE_800, lambda _: open_documents_module()),
            quick_action("Archived Documents", "View archived records", ft.Icons.ARCHIVE_OUTLINED, ft.Colors.BLUE_700, lambda _: open_archived_documents_module()),
        ]
        if "view_analytics" in {(p or "").strip().lower().replace(" ", "_") for p in (current_user_permissions or [])} or current_user_role == "Super Administrator":
            buttons.append(quick_action("Analytics", "View system analytics", ft.Icons.ANALYTICS_OUTLINED, ft.Colors.BLUE_900, lambda _: render_shell(page, current_user, logout_user, nav_items, analytics_view(), initial_selected_index=next((idx for idx, (_, label, _) in enumerate(nav_items) if label == "Analytics"), 0))))

        normalized_permissions = sorted({str(p).strip().lower().replace(" ", "_") for p in (current_user_permissions or [])})
        if current_user_role == "Super Administrator" and not normalized_permissions:
            normalized_permissions = ["*"]
        elif not normalized_permissions:
            normalized_permissions = ["(none)"]

        dashboard_content = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.DASHBOARD, color=ft.Colors.BLUE_700, size=24),
                                padding=10,
                                bgcolor=ft.Colors.BLUE_GREY_50,
                                border_radius=10,
                            ),
                            ft.Column(
                                [
                                    ft.Text("Dashboard", size=25, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                                    ft.Text("Super Administrator overview and quick access.", size=12, color=ft.Colors.BLUE_GREY_600),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED, color=ft.Colors.AMBER_700, size=25),
                                            padding=10,
                                            bgcolor=ft.Colors.WHITE,
                                            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                                            border_radius=30,
                                        ),
                                        ft.Column(
                                            [
                                                ft.Text(f"Welcome back, {current_user_role or 'User'}!", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                                                ft.Text("Here's what's happening with your system today.", size=11, color=ft.Colors.BLUE_GREY_600),
                                                ft.Text(f"Logged in as {current_user} | Permissions: {', '.join(normalized_permissions)}", size=10, color=ft.Colors.BLUE_GREY_500),
                                            ],
                                            spacing=2,
                                        ),
                                    ],
                                    spacing=10,
                                ),
                                ft.Column(
                                    [
                                        ft.Row([ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=16, color=ft.Colors.BLUE_GREY_600), ft.Text(date.today().strftime("%B %d, %Y"), size=11, color=ft.Colors.BLUE_GREY_700)], spacing=6),
                                        ft.Row([ft.Icon(ft.Icons.ACCESS_TIME_OUTLINED, size=16, color=ft.Colors.BLUE_GREY_600), ft.Text(datetime.now().strftime("%I:%M %p").lstrip("0"), size=11, color=ft.Colors.BLUE_GREY_700)], spacing=6),
                                    ],
                                    spacing=5,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            wrap=True,
                        ),
                        padding=12,
                        bgcolor=ft.Colors.BLUE_GREY_50,
                        border_radius=10,
                    ),
                    ft.Text("Overview", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                    ft.Row([metric_card(item) for item in summary_items], spacing=10, run_spacing=10, wrap=True),
                    ft.Text("Quick Access", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                    ft.Row(buttons, spacing=12, run_spacing=12, wrap=True),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.PEOPLE_ALT_OUTLINED, color=ft.Colors.BLUE_700, size=21),
                            ft.Text("User & Document Summary", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                        ],
                        spacing=8,
                    ),
                    ft.Row([metric_card(item) for item in user_cards], spacing=10, run_spacing=10, wrap=True),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.SHIELD_OUTLINED, color=ft.Colors.BLUE_700, size=22),
                                ft.Column(
                                    [
                                        ft.Text("System Overview", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                                        ft.Text("Monitor and manage your legislative document tracking system efficiently.", size=11, color=ft.Colors.BLUE_GREY_600),
                                    ],
                                    spacing=2,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=12,
                        bgcolor=ft.Colors.BLUE_GREY_50,
                        border_radius=10,
                    ),
                ],
                spacing=14,
            ),
            width="100%",
            padding=22,
            bgcolor=ft.Colors.BLUE_GREY_50,
            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
            border_radius=18,
        )

        return ft.Column([dashboard_content], spacing=12, tight=True)

    def analytics_view():
        return build_analytics_view(
            current_user,
            get_admin_headers(),
            backend_url=BACKEND_URL,
            open_documents_view=open_documents_module,
            open_archived_view=open_archived_documents_module,
            page=page,
        )

    def users_page_view():
        return users_roles_view()

    def show_login():
        page.clean()
        page.scroll = None
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER
        page.bgcolor = ft.Colors.BLUE_GREY_50
        page.padding = 24

        username_field = ft.TextField(label="Username", prefix_icon=ft.Icons.PERSON_OUTLINE, autofocus=True)
        password_field = ft.TextField(label="Password", password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK_OUTLINE)
        login_error = ft.Text("", size=12, color=ft.Colors.RED_700)

        def attempt_login(_):
            nonlocal current_user, current_user_role, runtime_token, refresh_token
            username = (username_field.value or "").strip()
            password = password_field.value or ""
            login_error.value = ""

            if not username or not password:
                login_error.value = "Please fill out both fields."
                page.update()
                return

            try:
                res = requests.post(f"{BACKEND_URL}/auth/login", data={"username": username, "password": password}, verify=False, timeout=10)
                if res.status_code == 200:
                    payload = res.json()
                    runtime_token = payload.get("access_token")
                    refresh_token = payload.get("refresh_token")
                    role = (payload.get("role") or "Super Administrator").strip()
                    current_user = payload.get("username")
                    current_user_role = role
                    current_user_permissions = payload.get("permissions") or []
                    save_session_state()
                    nav_items[:] = build_nav_items()
                    if nav_items:
                        initial_view = nav_items[0][2]()
                    else:
                        initial_view = ft.Column([ft.Text("No available modules for this account.")])
                    render_shell(page, current_user, logout_user, nav_items, initial_view, initial_selected_index=0)
                    if role not in {"Super Administrator", "Employee", "SB Member"}:
                        page.snack_bar = ft.SnackBar(ft.Text("Your account is not approved for access yet."), open=True)
                        page.update()
                else:
                    detail = res.json().get("detail", "Invalid credentials.") if res.headers.get("content-type", "").startswith("application/json") else "Invalid credentials."
                    login_error.value = detail
                    page.update()
            except Exception as ex:
                login_error.value = f"Connection failed: {ex}"
                page.update()

        def go_back(_=None):
            page.clean()
            page.overlay.clear()
            page.scroll = None
            page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
            page.vertical_alignment = ft.MainAxisAlignment.START
            page.padding = 0
            page.bgcolor = ft.Colors.WHITE
            from frontend.Frontend_Homepage.page import build_homepage_view
            page.add(build_homepage_view(page))
            page.update()

        login_btn = ft.Button("Log In", width=360, on_click=attempt_login, bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE)
        back_btn = ft.TextButton("Go Back", on_click=go_back)

        page.add(
            ft.Container(
                content=ft.ResponsiveRow(
                    [
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Icon(ft.Icons.ACCOUNT_BALANCE_OUTLINED, size=56, color=ft.Colors.AMBER_300),
                                    ft.Text("SANGGUNIAN BAYAN", size=27, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                    ft.Text("MUNICIPALITY OF TOLOSA", size=12, color=ft.Colors.BLUE_GREY_100),
                                    ft.Divider(height=1, color=ft.Colors.BLUE_GREY_400),
                                    ft.Text("Legislative Document Tracking Management System", size=15, color=ft.Colors.BLUE_GREY_100),
                                    ft.Text("Secure access for authorized personnel managing municipal legislative records.", size=13, color=ft.Colors.BLUE_GREY_200),
                                ],
                                spacing=16,
                                horizontal_alignment=ft.CrossAxisAlignment.START,
                            ),
                            bgcolor=ft.Colors.BLUE_900,
                            padding=ft.Padding(42, 42, 42, 42),
                            col={"xs": 12, "md": 6},
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text("Welcome back", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                                    ft.Text("Sign in to continue to the management system.", size=13, color=ft.Colors.BLUE_GREY_600),
                                    username_field,
                                    password_field,
                                    login_error,
                                    ft.Container(
                                        content=login_btn,
                                        alignment=ft.Alignment.CENTER,
                                    ),
                                    ft.Row([back_btn], alignment=ft.MainAxisAlignment.CENTER),
                                ],
                                spacing=16,
                            ),
                            bgcolor=ft.Colors.WHITE,
                            padding=ft.Padding(42, 42, 42, 42),
                            col={"xs": 12, "md": 6},
                        ),
                    ],
                    spacing=0,
                    run_spacing=0,
                ),
                width=920,
                height=540,
                border_radius=18,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                shadow=ft.BoxShadow(blur_radius=24, spread_radius=1, color="#102a3a26", offset=ft.Offset(0, 10)),
            )
        )
        page.update()

    def build_nav_items():
        items = []

        if has_permission("view_dashboard"):
            items.append((ft.Icons.DASHBOARD_OUTLINED, "Dashboard", lambda: dashboard_view()))
        if has_permission("view_analytics"):
            items.append((ft.Icons.ANALYTICS_OUTLINED, "Analytics", lambda: analytics_view()))

        if has_permission("view_documents"):
            items.append((ft.Icons.DESCRIPTION_OUTLINED, "Documents", lambda: documents_view()))
            items.append((ft.Icons.ARCHIVE_OUTLINED, "Archived Documents", lambda: archived_documents_view()))
        if not is_employee() or has_permission("view_documents"):
            items.append((ft.Icons.GROUP_OUTLINED, "Committees", lambda: committees_view()))
        if has_permission("view_qr_tracking"):
            items.append((ft.Icons.QR_CODE_2, "QR Tracking", qr_tracking_view))
        if current_user_role == "Super Administrator":
            items.append((ft.Icons.PEOPLE_ALT_OUTLINED, "Users & Roles", lambda: users_page_view()))
            items.append((ft.Icons.HISTORY_OUTLINED, "Audit Logs", lambda: audit_logs_view()))
        elif has_permission("view_audit_logs"):
            items.append((ft.Icons.HISTORY_OUTLINED, "Audit Logs", lambda: audit_logs_view()))

        items.append((ft.Icons.PERSON_OUTLINE, "My Account", lambda: account_view()))
        items.append((ft.Icons.SETTINGS_OUTLINED, "Settings", lambda: settings_view()))
        return items

    nav_items = build_nav_items()

    def restore_saved_session():
        nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
        try:
            if not hasattr(page, "client_storage"):
                return False
            saved_access = page.client_storage.get("sb_access_token")
            saved_refresh = page.client_storage.get("sb_refresh_token")
            saved_user = page.client_storage.get("sb_current_user")
            saved_role = page.client_storage.get("sb_current_user_role")
            saved_permissions = page.client_storage.get("sb_current_user_permissions")
            if not saved_access or not saved_user:
                return False
            runtime_token = saved_access
            refresh_token = saved_refresh
            current_user = saved_user
            current_user_role = saved_role or "Super Administrator"
            try:
                current_user_permissions = json.loads(saved_permissions) if saved_permissions else []
            except Exception:
                current_user_permissions = []
            refresh_runtime_token_if_needed(force=True)
            nav_items[:] = build_nav_items()
            initial_view = nav_items[0][2]() if nav_items else ft.Column([ft.Text("No available modules for this account.")])
            render_shell(page, current_user, logout_user, nav_items, initial_view, initial_selected_index=0)
            return True
        except Exception:
            return False

    if not restore_saved_session():
        show_login()


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
