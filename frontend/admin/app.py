import flet as ft
from datetime import date, datetime, timezone

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
import threading
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


def get_admin_headers(access_token=None):
    hdrs = {}
    token_to_use = access_token or AUTH_TOKEN
    if token_to_use:
        hdrs["Authorization"] = f"Bearer {token_to_use}"
    return hdrs


if os.getenv("DEV_HTTP", "0").lower() in ("1", "true", "yes"):
    if BACKEND_URL.startswith("https://"):
        BACKEND_URL = BACKEND_URL.replace("https://", "http://", 1)

from frontend.admin.committees import build_committees_view
from frontend.admin.documents import build_documents_view
from frontend.admin.document_details import open_document_details
from frontend.admin.audit_logs import build_audit_logs_view
from frontend.admin.analytics import build_analytics_view
from frontend.admin.users_roles import (
    OFFICE_EMPLOYEE_PERMISSION_GROUP,
    EMPLOYEE_PERMISSION_GROUPS,
    build_offices_table,
    build_users_roles_table,
    build_users_roles_view,
)
from frontend.admin.reference_data import build_reference_data_view
from frontend.admin.office_dashboard import build_office_overview_view, build_office_queue_view
from frontend.admin.qr_tracking import build_qr_tracking_view
from frontend.admin.todays_documents import build_todays_documents_view
from frontend.admin.admin_shell import render_shell


def clear_stale_session_state(state):
    reset = dict(state or {})
    reset["current_user"] = None
    reset["current_user_role"] = None
    reset["current_user_permissions"] = []
    reset["runtime_token"] = None
    reset["refresh_token"] = None
    return reset


def _read_selected_file_bytes(selected_file):
    if selected_file is None:
        return None
    try:
        if hasattr(selected_file, "read"):
            data = selected_file.read()
            if data is not None:
                return data
    except Exception:
        pass
    candidate_path = getattr(selected_file, "path", None)
    if candidate_path and os.path.exists(candidate_path):
        try:
            with open(candidate_path, "rb") as handle:
                return handle.read()
        except Exception:
            pass
    return None


def _trace_filepicker_file(context, selected_file):
    file_bytes = _read_selected_file_bytes(selected_file)
    raw_bytes = getattr(selected_file, "bytes", None)
    print(
        "FILEPICKER TRACE "
        f"context={context} "
        f"type={type(selected_file)!r} "
        f"name={getattr(selected_file, 'name', None)!r} "
        f"id={getattr(selected_file, 'id', None)!r} "
        f"path={getattr(selected_file, 'path', None)!r} "
        f"has_bytes={hasattr(selected_file, 'bytes')} "
        f"bytes_type={type(raw_bytes)!r} "
        f"bytes_length={len(raw_bytes) if raw_bytes is not None else None} "
        f"has_read={callable(getattr(selected_file, 'read', None))} "
        f"read_result_length={len(file_bytes) if file_bytes is not None else None}",
        flush=True,
    )
    return file_bytes


def _browser_selected_file_needs_upload(selected_file):
    if selected_file is None:
        return False
    if getattr(selected_file, "path", None):
        return False
    if hasattr(selected_file, "read") or hasattr(selected_file, "bytes"):
        return False
    return True


def _route_file_picker_result(current_context, event, single_handler, bulk_handler, replacement_handler):
    if current_context == "single_registration" and callable(single_handler):
        return single_handler(event)
    if current_context == "bulk_registration" and callable(bulk_handler):
        return bulk_handler(event)
    if current_context == "replacement" and callable(replacement_handler):
        return replacement_handler(event)
    return None


def _prepare_single_registration_upload(selected_file, filename, access_token=None):
    if selected_file is None:
        raise ValueError("No file selected")
    safe_name = filename or getattr(selected_file, "name", None) or "document.pdf"
    size = getattr(selected_file, "size", None) or 0
    response = requests.post(
        f"{BACKEND_URL}/documents/uploads/create_tmp_uploads",
        json={"files": [{"filename": safe_name, "size": size}]},
        headers=get_admin_headers(access_token),
        verify=False,
        timeout=30,
    )
    if response.status_code != 200:
        raise Exception(response.text)
    payload = response.json()
    files = payload.get("files", [])
    upload_info = next((item for item in files if item.get("ok")), None)
    if upload_info is None:
        reason = next((item.get("reason") for item in files if item.get("reason")), None)
        if reason == "Unsupported extension":
            raise Exception("Unsupported file type. Choose a PDF, DOC, or DOCX file.")
        raise Exception(reason or "No temporary upload URL was returned")
    return {
        "filename": safe_name,
        "size": size,
        "tmp_name": upload_info.get("tmp_name"),
        "upload_url": upload_info.get("upload_url"),
        "upload_token": upload_info.get("upload_token"),
    }


def _upload_selected_file_via_picker(file_picker_ref, selected_file, filename, access_token=None):
    if selected_file is None or not _browser_selected_file_needs_upload(selected_file):
        return None
    upload_info = _prepare_single_registration_upload(selected_file, filename, access_token=access_token)
    picker_upload = ft.FilePickerUploadFile(
        name=upload_info.get("filename"),
        upload_url=upload_info.get("upload_url"),
        method="PUT",
    )
    file_picker_ref.upload([picker_upload])
    return upload_info


def main(page: ft.Page, session=None):
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
    selected_monitoring_office = None

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

    def can_pass_office_document():
        return (
            (is_employee() or (current_user_role or "").strip().lower() == "super administrator")
            and has_permission("pass_office_documents")
        )

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

    def get_pending_qr_token():
        try:
            if hasattr(page, "client_storage"):
                return page.client_storage.get("sb_pending_qr_token")
        except Exception:
            pass
        return None

    def clear_pending_qr_token():
        try:
            if hasattr(page, "client_storage"):
                page.client_storage.remove("sb_pending_qr_token")
        except Exception:
            pass
        page_state = page.data if isinstance(page.data, dict) else {}
        page_state.pop("qr_authorization", None)
        page.data = page_state

    def _return_to_login_after_qr_details_401():
        nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
        pending_qr_token = get_pending_qr_token()
        current_user = None
        current_user_role = None
        current_user_permissions = []
        runtime_token = None
        refresh_token = None
        clear_session_state()
        if pending_qr_token:
            _save_qr_authorization_state(pending_qr_token, "login_required")
        show_login()

    def _qr_authorization_state():
        page_state = page.data if isinstance(page.data, dict) else {}
        return page_state, page_state.get("qr_authorization")

    def _save_qr_authorization_state(token, status, document_id=None):
        page_state, _ = _qr_authorization_state()
        qr_state = {"token": token, "status": status}
        if status == "authorized" and document_id is not None:
            qr_state["document_id"] = document_id
        page_state["qr_authorization"] = qr_state
        page.data = page_state
        return qr_state

    def _require_qr_reauthentication():
        pending_qr_token = get_pending_qr_token()
        if pending_qr_token:
            _save_qr_authorization_state(pending_qr_token, "login_required")

    def _render_qr_authorization_state(qr_state):
        states = {
            "checking": ("Checking document access...", ""),
            "authorized": (
                "Document Access Authorized",
                "Your account is authorized to access this document through your assigned office.\nPreparing document details...",
            ),
            "no_office": (
                "Office Access Required",
                "Your account is not currently assigned to an office. Please contact the system administrator.",
            ),
            "permission_denied": (
                "Access Denied",
                "You do not have permission to access this document.",
            ),
            "wrong_office": (
                "Access Denied",
                "This document is not associated with your assigned office.",
            ),
            "not_found": (
                "Document Not Found",
                "This QR code does not correspond to an available document.",
            ),
            "server_error": (
                "Unable to verify document access.",
                "Please try again.",
            ),
        }
        title, message = states.get(qr_state.get("status"), states["server_error"])
        controls = [ft.Text(title, size=20, weight=ft.FontWeight.BOLD)]
        if message:
            controls.append(ft.Text(message))
        page.clean()
        page.add(ft.Column(controls, spacing=8))
        page.update()

    def _open_authorized_qr_document(qr_state):
        document_id = qr_state.get("document_id")
        if document_id is None:
            _render_qr_authorization_state(_save_qr_authorization_state(qr_state.get("token"), "server_error"))
            return True
        if qr_state.get("details_opened"):
            _render_qr_authorization_state(qr_state)
            return True

        qr_state["details_opened"] = True
        page_state, _ = _qr_authorization_state()
        page_state["qr_authorization"] = qr_state
        page.data = page_state
        _render_qr_authorization_state(qr_state)
        if not show_document_details({"id": document_id}):
            qr_state["details_opened"] = False
            page_state["qr_authorization"] = qr_state
            page.data = page_state
        return True

    def show_qr_authenticated_state():
        nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
        pending_qr_token = get_pending_qr_token()
        if not pending_qr_token:
            return False

        _, saved_qr_state = _qr_authorization_state()
        if saved_qr_state and saved_qr_state.get("token") == pending_qr_token:
            if saved_qr_state.get("status") == "authorized":
                return _open_authorized_qr_document(saved_qr_state)
            if saved_qr_state.get("status") not in {"login_required", "checking"}:
                _render_qr_authorization_state(saved_qr_state)
                return True
            if saved_qr_state.get("status") == "checking":
                _render_qr_authorization_state(saved_qr_state)
                return True

        if not current_user or not runtime_token:
            _render_qr_authorization_state(_save_qr_authorization_state(pending_qr_token, "login_required"))
            show_login()
            return True

        qr_state = _save_qr_authorization_state(pending_qr_token, "checking")
        _render_qr_authorization_state(qr_state)
        try:
            get_admin_headers()
            if not current_user or not runtime_token:
                _save_qr_authorization_state(pending_qr_token, "login_required")
                show_login()
                return True

            request_url = f"{BACKEND_URL}/documents/qr/{quote(str(pending_qr_token), safe='')}/office"
            headers = {"Authorization": f"Bearer {runtime_token}"}
            response = requests.get(request_url, headers=headers, verify=False, timeout=15)

            if response.status_code == 401:
                refresh_runtime_token_if_needed(force=True)
                if runtime_token:
                    headers = {"Authorization": f"Bearer {runtime_token}"}
                    response = requests.get(request_url, headers=headers, verify=False, timeout=15)
                if not runtime_token:
                    _save_qr_authorization_state(pending_qr_token, "login_required")
                    show_login()
                    return True
                if response.status_code == 401:
                    current_user = None
                    current_user_role = None
                    current_user_permissions = []
                    runtime_token = None
                    refresh_token = None
                    clear_session_state()
                    _save_qr_authorization_state(pending_qr_token, "login_required")
                    show_login()
                    return True

            if response.status_code == 200:
                payload = response.json()
                document_id = payload.get("document_id") if isinstance(payload, dict) else None
                status = "authorized" if document_id is not None else "server_error"
                qr_state = _save_qr_authorization_state(pending_qr_token, status, document_id=document_id)
                if isinstance(payload, dict):
                    qr_state["handoff_status"] = payload.get("handoff_status")
                    page_state, _ = _qr_authorization_state()
                    page_state["qr_authorization"] = qr_state
                    page.data = page_state
                if status == "authorized":
                    _open_authorized_qr_document(qr_state)
                else:
                    _render_qr_authorization_state(qr_state)
            elif response.status_code == 403:
                try:
                    detail = str(response.json().get("detail", "")).strip().lower()
                except (AttributeError, ValueError):
                    detail = ""
                if "office assignment required" in detail:
                    status = "no_office"
                elif "not assigned to your office" in detail:
                    status = "wrong_office"
                else:
                    status = "permission_denied"
                _render_qr_authorization_state(_save_qr_authorization_state(pending_qr_token, status))
            elif response.status_code == 404:
                _render_qr_authorization_state(_save_qr_authorization_state(pending_qr_token, "not_found"))
            else:
                _render_qr_authorization_state(_save_qr_authorization_state(pending_qr_token, "server_error"))
        except Exception:
            _render_qr_authorization_state(_save_qr_authorization_state(pending_qr_token, "server_error"))
        return True

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
            _require_qr_reauthentication()
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
            _require_qr_reauthentication()
            show_login()
            return

    def get_admin_headers(access_token=None):
        refresh_runtime_token_if_needed()
        hdrs = {}
        # Protected admin routes authorize the bearer token server-side.
        token_to_use = access_token or runtime_token or AUTH_TOKEN
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

    reference_categories = []
    reference_document_types = []
    reference_search = ft.TextField(label="Search definitions", width=240, on_change=lambda _: refresh_reference_data_view())
    reference_kind_filter = ft.Dropdown(label="Definition", width=180, value="All", options=[ft.dropdown.Option("All"), ft.dropdown.Option("Categories"), ft.dropdown.Option("Document Types")], on_change=lambda _: refresh_reference_data_view())
    reference_name_field = ft.TextField(label="Name", width=360)
    reference_kind_dialog = "Categories"
    reference_edit_item = None
    reference_dialog = ft.AlertDialog(
        title=ft.Text("Document Definition", size=18, weight=ft.FontWeight.BOLD),
        content=reference_name_field,
        actions=[ft.TextButton("Cancel", on_click=lambda _: close_reference_dialog()), ft.Button("Save", on_click=lambda _: save_reference_definition(), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)],
    )
    page.overlay.append(reference_dialog)

    def load_reference_data():
        nonlocal reference_categories, reference_document_types
        try:
            headers = get_admin_headers()
            categories_response = requests.get(f"{BACKEND_URL}/reference-data/categories", headers=headers, verify=False, timeout=15)
            types_response = requests.get(f"{BACKEND_URL}/reference-data/document-types", headers=headers, verify=False, timeout=15)
            if categories_response.status_code != 200 or types_response.status_code != 200:
                raise Exception(categories_response.text if categories_response.status_code != 200 else types_response.text)
            reference_categories = categories_response.json() or []
            reference_document_types = types_response.json() or []
        except Exception as exc:
            show_document_notice(f"Unable to load document definitions: {exc}")

    def refresh_reference_data_view():
        page.update()

    def close_reference_dialog(_=None):
        reference_dialog.open = False
        page.update()

    def open_reference_create_dialog(kind):
        nonlocal reference_kind_dialog, reference_edit_item
        reference_kind_dialog = "Document Types" if kind == "Document Types" else "Categories"
        reference_edit_item = None
        reference_name_field.value = ""
        reference_dialog.title = ft.Text(f"Add {reference_kind_dialog[:-1]}", size=18, weight=ft.FontWeight.BOLD)
        reference_dialog.open = True
        page.update()

    def open_reference_edit_dialog(kind, item):
        nonlocal reference_kind_dialog, reference_edit_item
        reference_kind_dialog = kind + "s" if kind == "Category" else "Document Types"
        reference_edit_item = item
        reference_name_field.value = item.get("name") or ""
        reference_dialog.title = ft.Text(f"Edit {kind}", size=18, weight=ft.FontWeight.BOLD)
        reference_dialog.open = True
        page.update()

    def save_reference_definition():
        name = (reference_name_field.value or "").strip()
        if not name:
            show_document_notice("Definition name is required.")
            return
        endpoint_kind = "document-types" if reference_kind_dialog == "Document Types" else "categories"
        try:
            if reference_edit_item:
                response = requests.put(f"{BACKEND_URL}/reference-data/{endpoint_kind}/{reference_edit_item.get('id')}", json={"name": name}, headers=get_admin_headers(), verify=False, timeout=15)
            else:
                response = requests.post(f"{BACKEND_URL}/reference-data/{endpoint_kind}", json={"name": name}, headers=get_admin_headers(), verify=False, timeout=15)
            if response.status_code not in {200, 201}:
                raise Exception(response.text)
            close_reference_dialog()
            load_reference_data()
            page.update()
            show_document_notice("Document definition saved.")
        except Exception as exc:
            show_document_notice(f"Unable to save definition: {exc}")

    def toggle_reference_definition(kind, item):
        endpoint_kind = "document-types" if kind == "Document Type" else "categories"
        try:
            response = requests.put(f"{BACKEND_URL}/reference-data/{endpoint_kind}/{item.get('id')}", json={"name": item.get("name"), "is_active": not bool(item.get("is_active", True))}, headers=get_admin_headers(), verify=False, timeout=15)
            if response.status_code != 200:
                raise Exception(response.text)
            load_reference_data()
            page.update()
        except Exception as exc:
            show_document_notice(f"Unable to change definition status: {exc}")

    def reference_data_view():
        load_reference_data()
        load_active_definition_options()
        return build_reference_data_view(reference_categories, reference_document_types, reference_search, reference_kind_filter, open_reference_create_dialog, open_reference_edit_dialog, toggle_reference_definition, load_reference_data, page, section_header)

    documents_data = []
    archived_documents_data = []
    selected_archived_document_ids = set()
    archived_refresh = lambda: None

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

    documents_details_dialog = ft.AlertDialog(
        title=ft.Text("Document Details"),
        content=ft.Container(content=ft.Text(""), padding=8),
        actions=[ft.TextButton("Close", on_click=lambda _: close_documents_details_dialog())],
    )
    page.overlay.append(documents_details_dialog)

    pass_document_dialog = ft.AlertDialog(
        title=ft.Text("Pass Document"),
        content=ft.Container(content=ft.Text(""), padding=8, width=420),
        actions=[ft.TextButton("Cancel", on_click=lambda _: close_pass_document_dialog())],
    )
    page.overlay.append(pass_document_dialog)

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

    documents_bulk_archive_dialog = ft.AlertDialog(
        title=ft.Text("Archive Selected Documents?"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_documents_bulk_archive_dialog()),
            ft.Button("Archive", bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda _: run_bulk_archive_selected_documents()),
        ],
    )
    page.overlay.append(documents_bulk_archive_dialog)

    pending_restore_document = None
    archived_restore_dialog = ft.AlertDialog(
        title=ft.Text("Restore document?"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_archived_restore_dialog()),
            ft.Button("Restore", bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, on_click=lambda _: run_restore_archived_document_action()),
        ],
    )
    page.overlay.append(archived_restore_dialog)

    archived_restore_selected_dialog = ft.AlertDialog(
        title=ft.Text("Restore selected documents?"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_archived_restore_selected_dialog()),
            ft.Button("Restore", bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, on_click=lambda _: run_restore_selected_archived_documents_action()),
        ],
    )
    page.overlay.append(archived_restore_selected_dialog)

    pending_permanent_delete_document = None
    archived_delete_dialog = ft.AlertDialog(
        title=ft.Text("Delete permanently?"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_archived_delete_dialog()),
            ft.Button("Delete Permanently", bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, on_click=lambda _: run_permanent_delete_archived_document_action()),
        ],
    )
    page.overlay.append(archived_delete_dialog)

    archived_delete_selected_dialog = ft.AlertDialog(
        title=ft.Text("Delete selected documents permanently?"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_archived_delete_selected_dialog()),
            ft.Button("Delete Permanently", bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, on_click=lambda _: run_delete_selected_archived_documents_action()),
        ],
    )
    page.overlay.append(archived_delete_selected_dialog)

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

    legislative_year_options = [
        ft.dropdown.Option(str(year))
        for year in range(datetime.now().year, 1899, -1)
    ]

    def _parse_legislative_year(value):
        try:
            year = int(str(value or "").strip())
        except (TypeError, ValueError):
            return None
        return year if 1000 <= year <= datetime.now().year else None

    registration_title = ft.TextField(label="Title", width=680)
    registration_document_number = ft.TextField(label="Legislative Document Number", width=240)
    registration_series_year = ft.Dropdown(
        label="Legislative Year *",
        width=220,
        options=legislative_year_options,
    )
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
    current_file_picker_context = None
    single_registration_upload = {
        "tmp_name": None,
        "upload_url": None,
        "upload_token": None,
        "filename": None,
        "status": "idle",
        "selected_file_source": None,
        "in_progress": False,
    }
    file_picker = ft.FilePicker(on_result=lambda e: None)
    page.overlay.append(file_picker)

    def _on_registration_file(e):
        nonlocal registration_attachment
        try:
            if getattr(e, 'files', None):
                f = e.files[0]
                attachment_path = getattr(e, 'path', None) or getattr(f, 'path', None)
                file_bytes = _trace_filepicker_file("registration", f)
                if attachment_path and not os.path.isabs(attachment_path) and not os.path.exists(attachment_path):
                    attachment_path = os.path.abspath(attachment_path)
                registration_attachment = {
                    "path": attachment_path,
                    "name": getattr(f, 'name', None),
                    "file_bytes": file_bytes,
                    "selected_file_source": f,
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

    def _on_single_upload(e):
        nonlocal single_registration_upload
        fname = getattr(e, "file_name", None)
        error = getattr(e, "error", None)
        progress = getattr(e, "progress", None)
        print(
            "FILEPICKER TRACE "
            f"context=single_upload_event file_name={fname!r} progress={progress!r} error={error!r} "
            f"pending_tmp={single_registration_upload.get('tmp_name')!r}",
            flush=True,
        )
        if error:
            single_registration_upload["status"] = "error"
            single_registration_upload["in_progress"] = False
            show_document_notice(f"Single document upload failed: {error}")
            return
        if progress is not None:
            if progress >= 1.0:
                single_registration_upload["status"] = "uploaded"
                single_registration_upload["in_progress"] = False
                _confirm_single_registration_upload()
            else:
                single_registration_upload["status"] = "uploading"
                single_registration_upload["in_progress"] = True
        else:
            single_registration_upload["status"] = "uploaded"
            single_registration_upload["in_progress"] = False
            _confirm_single_registration_upload()
        page.update()

    def _confirm_single_registration_upload():
        nonlocal single_registration_upload
        if not single_registration_upload.get("tmp_name"):
            show_document_notice("No uploaded document is available to register.")
            return
        title = (registration_title.value or "").strip()
        if not title:
            show_document_notice("Title is required to register a document.")
            return
        series_year = _parse_legislative_year(registration_series_year.value)
        if series_year is None:
            show_document_notice("Legislative Year is required.")
            return
        payload = {
            "tmp_names": [single_registration_upload["tmp_name"]],
            "title": title,
            "document_number": (registration_document_number.value or "").strip() or None,
            "series_year": series_year,
            "description": (registration_description.value or "").strip() or None,
            "category": (registration_category.value or "").strip() or None,
            "document_type": (registration_document_type.value or "").strip() or None,
            "current_office": (registration_current_office.value or "").strip() or None,
            "assigned_to": (registration_assigned_to.value or "").strip() or None,
            "author": (registration_author.value or "").strip() or None,
            "priority": (registration_priority.value or "Medium").strip() or "Medium",
        }
        try:
            refresh_runtime_token_if_needed()
            auth_headers = get_admin_headers(runtime_token)
            response = requests.post(
                f"{BACKEND_URL}/documents/bulk-register/confirm_tmp",
                json=payload,
                headers=auth_headers,
                verify=False,
                timeout=180,
            )
            if response.status_code not in {200, 201}:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise Exception(f"{response.status_code} {detail}")
            result = response.json()
            if not result.get("success", False):
                failures = result.get("errors") or []
                detail = "; ".join(str(item.get("reason", item)) for item in failures if isinstance(item, dict)) or response.text
                raise Exception(detail)
            register_document_dialog.open = False
            page.update()
            load_documents_table()
            show_document_notice("Document registered successfully.")
        except Exception as exc:
            show_document_notice(f"Document registration failed: {exc}")
        finally:
            single_registration_upload = {
                "tmp_name": None,
                "upload_url": None,
                "upload_token": None,
                "filename": None,
                "status": "idle",
                "selected_file_source": None,
                "in_progress": False,
            }

    # attach handler to file_picker
    file_picker.on_result = lambda e: _route_file_picker_result(
        current_file_picker_context,
        e,
        _on_registration_file,
        _on_bulk_pick,
        _on_replacement_file,
    )
    file_picker.on_upload = _on_single_upload

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
                ft.OutlinedButton("Choose file", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=lambda _: file_picker.pick_files(file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["pdf", "doc", "docx"])),
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
                ft.Row([registration_document_number, registration_series_year], spacing=12, wrap=True),
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

    def clear_selected_qr_documents():
        selected_qr_document_ids.clear()
        close_qr_label_download_dialog()
        documents_refresh()

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
        nonlocal current_file_picker_context, single_registration_upload
        current_file_picker_context = None
        single_registration_upload = {
            "tmp_name": None,
            "upload_url": None,
            "upload_token": None,
            "filename": None,
            "status": "idle",
            "selected_file_source": None,
            "in_progress": False,
        }
        register_document_dialog.open = False
        page.update()

    def open_register_document_dialog(_=None):
        nonlocal registration_attachment, current_file_picker_context, single_registration_upload
        current_file_picker_context = "single_registration"
        single_registration_upload = {
            "tmp_name": None,
            "upload_url": None,
            "upload_token": None,
            "filename": None,
            "status": "idle",
            "selected_file_source": None,
            "in_progress": False,
        }
        registration_title.value = ""
        registration_document_number.value = ""
        registration_series_year.value = None
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
    bulk_common_document_number = ft.TextField(label="Legislative Document Number (optional)", width=260)
    bulk_apply_series_year = ft.Dropdown(
        label="Apply Year to All",
        width=190,
        options=legislative_year_options,
    )
    bulk_apply_year_button = ft.OutlinedButton(
        "Apply",
        icon=ft.Icons.CHECK,
        on_click=lambda _: _apply_bulk_year_to_all(),
    )
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
            size_bytes = item.get("size")
            size_text = f"{size_bytes / 1024:.0f} KB" if isinstance(size_bytes, (int, float)) and size_bytes > 0 else "Size unavailable"
            status_control = ft.Text(status_text, size=11, color=ft.Colors.GREEN_700 if status_text == "Ready" else ft.Colors.BLUE_GREY_700)
            def update_file_year(e, target=item):
                target["series_year"] = e.control.value
                e.control.error_text = None

            year_control = ft.Dropdown(
                label="Year *",
                width=112,
                options=legislative_year_options,
                value=str(item.get("series_year") or ""),
                on_change=update_file_year,
            )
            row_controls = [
                ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=18, color=ft.Colors.BLUE_700),
                ft.Container(content=ft.Text(item.get("name", "-"), size=12, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=140, alignment=ft.Alignment.CENTER_LEFT),
                year_control,
                ft.Text(size_text, size=11, color=ft.Colors.BLUE_GREY_600),
                status_control,
            ]
            progress_control = ft.ProgressBar(value=item.get("progress", 0.0), width=70)
            row_controls.append(progress_control)
            row_controls.append(ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remove file", on_click=lambda e, nm=item.get("tmp_name"): _remove_tmp_file(nm)))
            bulk_selected_list.controls.append(
                ft.Container(
                    content=ft.Row(row_controls, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(4, 6, 4, 6),
                    border=ft.border.only(bottom=ft.border.all(1, ft.Colors.BLUE_GREY_100)),
                )
            )
            item["_status_control"] = status_control
            item["_year_control"] = year_control
            item["_progress_control"] = progress_control
        page.update()

    def _remove_tmp_file(tmp_name):
        nonlocal bulk_import_files
        bulk_import_files = [i for i in bulk_import_files if i.get("tmp_name") != tmp_name]
        _render_bulk_selected_list()

    def _apply_bulk_year_to_all():
        year = _parse_legislative_year(bulk_apply_series_year.value)
        if year is None:
            show_document_notice("Choose a valid Legislative Year to apply.")
            return
        for item in bulk_import_files:
            item["series_year"] = str(year)
        _render_bulk_selected_list()

    def _start_bulk_uploads():
        pending_items = [item for item in bulk_import_files if item.get("tmp_name") and item.get("upload_url")]
        if not pending_items:
            return

        upload_files = []
        for item in pending_items:
            item["status"] = "Queued"
            item["progress"] = 0.0
            status_control = item.get("_status_control")
            progress_control = item.get("_progress_control")
            if status_control is not None:
                status_control.value = item["status"]
                status_control.color = ft.Colors.BLUE_GREY_700
            if progress_control is not None:
                progress_control.value = item["progress"]
            upload_files.append(
                ft.FilePickerUploadFile(
                    name=item.get("name") or item.get("upload_name") or item.get("tmp_name"),
                    upload_url=item.get("upload_url"),
                    method="PUT",
                )
            )
        try:
            print(
                "FILEPICKER TRACE "
                f"context=bulk_upload_invocation count={len(upload_files)} "
                f"names={[item.get('name') for item in pending_items]!r}",
                flush=True,
            )
            bulk_file_picker.upload(upload_files)
            for item in pending_items:
                item["status"] = "Uploading"
                item["progress"] = 0.05
                status_control = item.get("_status_control")
                progress_control = item.get("_progress_control")
                if status_control is not None:
                    status_control.value = item["status"]
                    status_control.color = ft.Colors.BLUE_GREY_700
                if progress_control is not None:
                    progress_control.value = item["progress"]
            page.update()
        except Exception as exc:
            print(f"FILEPICKER TRACE context=bulk_upload_exception type={type(exc)!r} message={exc!r}", flush=True)
            for item in pending_items:
                item["status"] = f"Error: {exc}"
                item["progress"] = 0.0
            page.update()

    def _on_bulk_pick(e):
        nonlocal bulk_import_files
        files = getattr(e, "files", None) or []
        if not files:
            return
        # Request server-generated temporary upload URLs tied to the authenticated user
        files_meta = []
        selected_file_map = {}
        for f in files:
            name = getattr(f, "name", None) or ""
            size = getattr(f, "size", None) or 0
            selected_id = getattr(f, "id", None)
            selected_key = selected_id or name or f"{getattr(f, 'path', '')}:{size}"
            file_bytes = _trace_filepicker_file("bulk", f)
            files_meta.append({"filename": name, "size": size})
            selected_file_map[selected_key] = {"size": size, "path": getattr(f, "path", None), "file_bytes": file_bytes, "source": f, "id": selected_id, "key": selected_key}

        try:
            resp = requests.post(f"{BACKEND_URL}/documents/uploads/create_tmp_uploads", json={"files": files_meta}, headers=get_admin_headers(), verify=False, timeout=30)
            if resp.status_code != 200:
                raise Exception(resp.text)
            body = resp.json()
            for info in body.get("files", []):
                if not info.get("ok"):
                    bulk_import_files.append({"name": info.get("filename"), "size": 0, "tmp_name": None, "path": None, "file_bytes": None, "selected_file_source": None, "upload_url": None, "upload_token": None, "upload_name": None, "series_year": None, "status": f"Rejected: {info.get('reason')}", "progress": 0.0})
                    continue
                name = info.get("filename")
                tmp_name = info.get("tmp_name")
                upload_url = info.get("upload_url")
                selected_key = next((key for key, value in selected_file_map.items() if value.get("source") is not None and getattr(value.get("source"), "name", None) == name), None)
                if selected_key is None:
                    selected_key = name
                selected = selected_file_map.get(selected_key, {})
                print(
                    "FILEPICKER TRACE "
                    f"context=bulk_selected_file_map name={name!r} "
                    f"selected_key={selected_key!r} "
                    f"stored_bytes_length={len(selected.get('file_bytes')) if selected.get('file_bytes') is not None else None} "
                    f"stored_source_type={type(selected.get('source'))!r}",
                    flush=True,
                )
                selected_size = selected.get("size", 0)
                selected_path = selected.get("path")
                selected_bytes = selected.get("file_bytes")
                selected_source = selected.get("source")
                upload_name = name
                bulk_import_files.append({
                    "name": name,
                    "size": selected_size,
                    "tmp_name": tmp_name,
                    "path": selected_path,
                    "file_bytes": selected_bytes,
                    "selected_file_source": selected_source,
                    "upload_url": upload_url,
                    "upload_token": info.get("upload_token"),
                    "upload_name": upload_name,
                    "selected_file_id": selected.get("id"),
                    "selected_file_key": selected.get("key"),
                    "series_year": None,
                    "status": "Queued",
                    "progress": 0.0,
                })

            _render_bulk_selected_list()
            _start_bulk_uploads()
        except Exception as exc:
            show_document_notice(f"Failed to create upload URLs: {exc}")

    def _on_bulk_upload(e):
        # e: FilePickerUploadEvent
        fname = getattr(e, "file_name", None)
        progress = getattr(e, "progress", None)
        error = getattr(e, "error", None)
        for item in bulk_import_files:
            item_key = item.get("upload_name") or item.get("tmp_name") or item.get("name")
            if item_key == fname or item.get("name") == fname:
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
                status_control = item.get("_status_control")
                progress_control = item.get("_progress_control")
                if status_control is not None:
                    status_control.value = item.get("status", "")
                    status_control.color = ft.Colors.GREEN_700 if item.get("status") == "Ready" else ft.Colors.BLUE_GREY_700
                if progress_control is not None:
                    progress_control.value = item.get("progress", 0.0)
                break
        page.update()

    bulk_file_picker.on_result = lambda e: _route_file_picker_result(
        current_file_picker_context,
        e,
        _on_registration_file,
        _on_bulk_pick,
        _on_replacement_file,
    )
    bulk_file_picker.on_upload = _on_bulk_upload

    def open_bulk_register_document_dialog(_=None):
        # reset
        nonlocal bulk_import_files, current_file_picker_context
        current_file_picker_context = "bulk_registration"
        bulk_import_files = []
        _render_bulk_selected_list()
        bulk_common_title.value = ""
        bulk_common_document_number.value = ""
        bulk_apply_series_year.value = None
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
                ft.Row([bulk_apply_series_year, bulk_apply_year_button], spacing=8, wrap=True),
                ft.Row([bulk_common_title, bulk_common_description], spacing=12, wrap=True),
                bulk_common_document_number,
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
        nonlocal current_file_picker_context
        current_file_picker_context = None
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

    def _missing_bulk_year_files():
        return [
            item for item in bulk_import_files
            if _parse_legislative_year(item.get("series_year")) is None
        ]

    def _show_missing_bulk_years(items):
        missing_names = []
        for item in items:
            name = item.get("name") or "Unnamed file"
            missing_names.append(name)
            control = item.get("_year_control")
            if control is not None:
                control.error_text = "Required"
        show_document_notice(
            "Cannot complete bulk registration.\n\n"
            "The following documents are missing a Legislative Year:\n"
            + "\n".join(f"- {name}" for name in missing_names)
        )
        page.update()

    def _confirm_bulk_register():
        if not bulk_import_files:
            show_document_notice("No files to register")
            return
        missing_years = _missing_bulk_year_files()
        if missing_years:
            _show_missing_bulk_years(missing_years)
            return
        tmp_names = [i.get("tmp_name") for i in bulk_import_files]
        payload = {
            "tmp_names": tmp_names,
            "documents": [
                {
                    "tmp_name": item.get("tmp_name"),
                    "series_year": _parse_legislative_year(item.get("series_year")),
                }
                for item in bulk_import_files
            ],
            "title": (bulk_common_title.value or None),
            "document_number": (bulk_common_document_number.value or "").strip() or None,
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
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise Exception(detail)
            result = response.json()
            duplicate_errors = [error for error in result.get("errors", []) if error.get("duplicate")]
            for error in duplicate_errors:
                for item in bulk_import_files:
                    if item.get("name") == error.get("filename"):
                        item["status"] = f"Duplicate: {', '.join(error.get('documents', []))}"
                        item["progress"] = 0.0
            errors = result.get("errors", [])
            message = f"Bulk registration completed: {result.get('registered', 0)} created, {result.get('failed', 0)} failed."
            if errors:
                failure_details = [
                    f"{error.get('filename') or 'File'}: {error.get('reason') or 'Unknown error'}"
                    for error in errors[:5]
                ]
                if len(errors) > 5:
                    failure_details.append(f"...and {len(errors) - 5} more")
                message += "\n\nFailed:\n" + "\n".join(failure_details)
            if duplicate_errors:
                _render_bulk_selected_list()
                show_document_notice(message)
            else:
                show_document_notice(message)
                close_bulk_register_document_dialog()
                load_documents_table()
        except Exception as exc:
            show_document_notice(f"Bulk registration failed: {exc}")

    def submit_register_document(_=None):
        nonlocal single_registration_upload
        title = (registration_title.value or "").strip()
        if not title:
            show_document_notice("Title is required to register a document.")
            return
        series_year = _parse_legislative_year(registration_series_year.value)
        if series_year is None:
            show_document_notice("Legislative Year is required.")
            return

        payload = {
            "title": title,
            "document_number": (registration_document_number.value or "").strip() or None,
            "series_year": series_year,
            "description": (registration_description.value or "").strip() or None,
            "category": (registration_category.value or "").strip() or None,
            "document_type": (registration_document_type.value or "").strip() or None,
            "current_office": (registration_current_office.value or "").strip() or None,
            "assigned_to": (registration_assigned_to.value or "").strip() or None,
            "author": (registration_author.value or "").strip() or None,
            "priority": (registration_priority.value or "Medium").strip() or "Medium",
        }

        try:
            refresh_runtime_token_if_needed()
            auth_headers = get_admin_headers(runtime_token)
            if registration_attachment:
                selected_source = registration_attachment.get("selected_file_source")
                filename = registration_attachment.get("name") or "document.pdf"
                print(
                    "FILEPICKER TRACE "
                    f"context=registration_submit_browser_upload name={filename!r} "
                    f"source_type={type(selected_source)!r} path={getattr(selected_source, 'path', None)!r}",
                    flush=True,
                )
                upload_info = _prepare_single_registration_upload(selected_source, filename, access_token=runtime_token)
                single_registration_upload = {
                    "tmp_name": upload_info.get("tmp_name"),
                    "upload_url": upload_info.get("upload_url"),
                    "upload_token": upload_info.get("upload_token"),
                    "filename": upload_info.get("filename"),
                    "status": "queued",
                    "selected_file_source": selected_source,
                    "in_progress": True,
                }
                picker_upload = ft.FilePickerUploadFile(
                    name=upload_info.get("filename"),
                    upload_url=upload_info.get("upload_url"),
                    method="PUT",
                )
                file_picker.upload([picker_upload])
                page.update()
                return

            response = requests.post(
                f"{BACKEND_URL}/documents/register",
                data={k: v for k, v in payload.items() if v is not None},
                headers=auth_headers,
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

    edit_document_id = None
    edit_document_title = ft.TextField(label="Title", width=680)
    edit_document_number = ft.TextField(label="Legislative Document Number", width=240)
    edit_series_year = ft.TextField(label="Series Year", width=180)
    edit_document_description = ft.TextField(label="Description", multiline=True, min_lines=2, max_lines=3, width=680)
    edit_document_category = ft.Dropdown(label="Category", width=330, options=[ft.dropdown.Option("Legislation"), ft.dropdown.Option("Policy"), ft.dropdown.Option("Report")])
    edit_document_type = ft.Dropdown(label="Document Type", width=330, options=[ft.dropdown.Option("Ordinance"), ft.dropdown.Option("Resolution"), ft.dropdown.Option("Committee Report")])
    edit_document_current_office = ft.Dropdown(label="Current Office", width=330, options=[ft.dropdown.Option("SB Secretariat"), ft.dropdown.Option("Office of the Mayor"), ft.dropdown.Option("Committee on Health")])
    edit_document_assigned_to = ft.TextField(label="Assigned To", width=330)
    edit_document_author = ft.TextField(label="Author", width=330)
    edit_document_priority = ft.Dropdown(label="Priority", width=330, options=[ft.dropdown.Option("Low"), ft.dropdown.Option("Medium"), ft.dropdown.Option("High")])
    edit_document_remarks = ft.TextField(label="Remarks", multiline=True, min_lines=2, max_lines=3, width=680)
    edit_document_session = ft.TextField(label="Session", width=330)

    def load_active_definition_options():
        try:
            headers = get_admin_headers()
            category_response = requests.get(f"{BACKEND_URL}/reference-data/categories", params={"active_only": "true"}, headers=headers, verify=False, timeout=15)
            type_response = requests.get(f"{BACKEND_URL}/reference-data/document-types", params={"active_only": "true"}, headers=headers, verify=False, timeout=15)
            if category_response.status_code != 200 or type_response.status_code != 200:
                return
            category_names = [item.get("name") for item in category_response.json() if item.get("name")]
            type_names = [item.get("name") for item in type_response.json() if item.get("name")]
            for control, names in (
                (registration_category, category_names),
                (bulk_common_category, category_names),
                (edit_document_category, category_names),
                (registration_document_type, type_names),
                (bulk_common_document_type, type_names),
                (edit_document_type, type_names),
            ):
                current_value = control.value
                control.options = [ft.dropdown.Option(name) for name in names]
                if current_value and current_value in names:
                    control.value = current_value
                elif not current_value and names:
                    control.value = names[0]
        except Exception:
            pass

    edit_document_dialog = ft.AlertDialog(
        title=ft.Text("Edit Document", size=20, weight=ft.FontWeight.BOLD),
        content=ft.Column(
            [
                ft.Text("Update document information. Tracking number, attachment, QR, visibility, and archive state are preserved.", size=12, color=ft.Colors.BLUE_GREY_600),
                edit_document_title,
                ft.Row([edit_document_number, edit_series_year], spacing=12, wrap=True),
                edit_document_description,
                ft.Row([edit_document_category, edit_document_type], spacing=12, wrap=True),
                ft.Row([edit_document_current_office, edit_document_assigned_to], spacing=12, wrap=True),
                ft.Row([edit_document_author, edit_document_priority, edit_document_session], spacing=12, wrap=True),
                edit_document_remarks,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            width=700,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_edit_document_dialog()),
            ft.Button("Save Changes", icon=ft.Icons.SAVE_OUTLINED, on_click=lambda _: submit_edit_document(), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
        ],
    )
    page.overlay.append(edit_document_dialog)

    def _set_edit_dropdown_value(control, value):
        normalized = (value or "").strip()
        if normalized and not any(getattr(option, "key", None) == normalized or getattr(option, "text", None) == normalized for option in control.options):
            control.options.append(ft.dropdown.Option(normalized))
        control.value = normalized or None

    def close_edit_document_dialog(_=None):
        edit_document_dialog.open = False
        page.update()

    def open_edit_document_dialog(document):
        nonlocal edit_document_id
        edit_document_id = document.get("id")
        if not edit_document_id:
            show_document_notice("Unable to edit document: document ID is missing.")
            return
        edit_document_title.value = str(document.get("title") or "").strip()
        edit_document_number.value = str(document.get("document_number") or "").strip()
        edit_series_year.value = str(document.get("series_year") or "").strip()
        edit_document_description.value = str(document.get("description") or "").strip()
        _set_edit_dropdown_value(edit_document_category, document.get("category"))
        _set_edit_dropdown_value(edit_document_type, document.get("document_type"))
        _set_edit_dropdown_value(edit_document_current_office, document.get("current_office"))
        edit_document_assigned_to.value = "" if document.get("assigned_to") in (None, "-") else str(document.get("assigned_to"))
        edit_document_author.value = "" if document.get("author") in (None, "-") else str(document.get("author"))
        _set_edit_dropdown_value(edit_document_priority, document.get("priority") or "Medium")
        edit_document_remarks.value = str(document.get("remarks") or "").strip()
        edit_document_session.value = "" if document.get("session") in (None, "-") else str(document.get("session"))
        edit_document_dialog.open = True
        page.update()

    def submit_edit_document(_=None):
        if not edit_document_id:
            show_document_notice("Unable to edit document: no document is selected.")
            return
        title = (edit_document_title.value or "").strip()
        if not title:
            show_document_notice("Title is required.")
            return
        payload = {
            "title": title,
            "document_number": (edit_document_number.value or "").strip() or None,
            "series_year": (edit_series_year.value or "").strip() or None,
            "description": (edit_document_description.value or "").strip() or None,
            "category": (edit_document_category.value or "").strip() or None,
            "document_type": (edit_document_type.value or "").strip() or None,
            "current_office": (edit_document_current_office.value or "").strip() or None,
            "assigned_to": (edit_document_assigned_to.value or "").strip() or None,
            "author": (edit_document_author.value or "").strip() or None,
            "priority": (edit_document_priority.value or "").strip() or None,
            "remarks": (edit_document_remarks.value or "").strip() or None,
            "session": (edit_document_session.value or "").strip() or None,
        }
        try:
            response = requests.put(
                f"{BACKEND_URL}/documents/{edit_document_id}",
                json=payload,
                headers=get_admin_headers(),
                verify=False,
                timeout=15,
            )
            if response.status_code != 200:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise Exception(f"{response.status_code} {detail}")
            edit_document_dialog.open = False
            page.update()
            load_documents_table()
            show_document_notice("Document updated successfully.")
        except Exception as exc:
            show_document_notice(f"Document update failed: {exc}")

    def make_document_header(label, width):
        return ft.Container(
            content=ft.Text(label, weight=ft.FontWeight.BOLD, size=12),
            width=width,
            alignment=ft.Alignment.CENTER_LEFT,
            padding=ft.Padding(0, 0, 0, 0),
        )

    selected_qr_document_ids = set()
    documents_refresh = lambda: None

    def show_document_notice(message):
        page.snack_bar = ft.SnackBar(ft.Text(message), open=True)
        page.update()

    def close_pass_document_dialog():
        pass_document_dialog.open = False
        page.update()

    def open_pass_document_dialog(document):
        if not isinstance(document, dict):
            show_document_notice("No document selected for handoff.")
            return
        if not can_pass_office_document():
            show_document_notice("You do not have permission to pass this document.")
            return

        document_id = document.get("id")
        if not document_id:
            show_document_notice("This document cannot be passed because it is missing an ID.")
            return

        office_loading = ft.Text("Loading available offices...", size=12, color=ft.Colors.BLUE_GREY_600)
        office_error = ft.Text("", size=12, color=ft.Colors.RED_700)
        office_selector = ft.Dropdown(
            label="Receiving Office",
            width=400,
            disabled=True,
            options=[],
            on_change=lambda _: submit_button.update() if False else None,
        )
        submit_button = ft.Button(
            "Pass Document",
            bgcolor=ft.Colors.BLUE_700,
            color=ft.Colors.WHITE,
            disabled=True,
            on_click=lambda _: None,
        )

        def refresh_submit_button_state():
            submit_button.disabled = office_selector.disabled or office_selector.value in (None, "")
            if hasattr(pass_document_dialog, "update"):
                pass_document_dialog.update()

        office_selector.on_change = lambda _: refresh_submit_button_state()

        def load_available_offices():
            office_selector.options = []
            office_selector.disabled = True
            office_selector.value = None
            office_loading.value = "Loading available offices..."
            office_error.value = ""
            refresh_submit_button_state()
            page.update()
            try:
                headers = {}
                if runtime_token:
                    headers["Authorization"] = f"Bearer {runtime_token}"
                if not runtime_token:
                    refresh_runtime_token_if_needed(force=True)
                    if runtime_token:
                        headers["Authorization"] = f"Bearer {runtime_token}"
                if not runtime_token:
                    raise RuntimeError("Your session has expired. Please sign in again.")
                response = requests.get(
                    f"{BACKEND_URL}/offices/available-for-handoff",
                    headers=headers,
                    verify=False,
                    timeout=15,
                )
                if response.status_code == 401:
                    refresh_runtime_token_if_needed(force=True)
                    if not runtime_token:
                        raise RuntimeError("Your session has expired. Please sign in again.")
                    headers = {"Authorization": f"Bearer {runtime_token}"}
                    response = requests.get(
                        f"{BACKEND_URL}/offices/available-for-handoff",
                        headers=headers,
                        verify=False,
                        timeout=15,
                    )
                if response.status_code != 200:
                    try:
                        detail = response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else str(response.text)
                    except Exception:
                        detail = str(response.text)
                    raise RuntimeError(detail or "Unable to load available offices.")
                offices = response.json() or []
                options = []
                for item in offices:
                    office_name = item.get("name") or "Unknown Office"
                    office_code = item.get("office_code")
                    label = office_name if not office_code else f"{office_name} ({office_code})"
                    options.append(ft.dropdown.Option(key=str(item.get("id")), text=label))
                office_selector.options = options
                office_selector.disabled = False
                if not options:
                    office_loading.value = "No receiving offices are available for this document."
                    office_selector.value = None
                    submit_button.disabled = True
                else:
                    office_loading.value = f"{len(options)} office(s) available for handoff."
                    office_selector.value = None
                    submit_button.disabled = True
                page.update()
            except Exception as exc:
                office_error.value = str(exc) if str(exc) else "Unable to load receiving offices."
                office_loading.value = ""
                office_selector.options = []
                office_selector.disabled = True
                office_selector.value = None
                submit_button.disabled = True
                page.update()

        def submit_handoff(_):
            selected_office_id = office_selector.value
            if selected_office_id in (None, ""):
                office_error.value = "Please select a receiving office before continuing."
                page.update()
                return
            if not isinstance(document, dict):
                office_error.value = "This document is no longer available to pass."
                page.update()
                return

            selected_office_name = next(
                (option.text for option in office_selector.options if str(option.key) == str(selected_office_id)),
                "the selected office",
            )
            submit_button.disabled = True
            office_loading.value = "Submitting handoff..."
            office_error.value = ""
            page.update()
            try:
                headers = {}
                if runtime_token:
                    headers["Authorization"] = f"Bearer {runtime_token}"
                if not runtime_token:
                    refresh_runtime_token_if_needed(force=True)
                    if runtime_token:
                        headers["Authorization"] = f"Bearer {runtime_token}"
                if not runtime_token:
                    raise RuntimeError("Your session has expired. Please sign in again.")
                response = requests.post(
                    f"{BACKEND_URL}/documents/{document_id}/handoffs",
                    json={"receiving_office_id": int(selected_office_id)},
                    headers=headers,
                    verify=False,
                    timeout=20,
                )
                if response.status_code == 401:
                    refresh_runtime_token_if_needed(force=True)
                    if not runtime_token:
                        raise RuntimeError("Your session has expired. Please sign in again.")
                    headers = {"Authorization": f"Bearer {runtime_token}"}
                    response = requests.post(
                        f"{BACKEND_URL}/documents/{document_id}/handoffs",
                        json={"receiving_office_id": int(selected_office_id)},
                        headers=headers,
                        verify=False,
                        timeout=20,
                    )
                if response.status_code == 200:
                    close_pass_document_dialog()
                    show_document_notice(
                        f"Document {document.get('tracking_number') or document_id} has been passed to {selected_office_name}. Status: Pending Receipt"
                    )
                    try:
                        if callable(office_dashboard_refresh):
                            office_dashboard_refresh()
                    except Exception:
                        pass
                    try:
                        show_document_details(document)
                    except Exception:
                        pass
                    return

                try:
                    payload = response.json()
                    detail = str(payload.get("detail") or payload.get("message") or response.text)
                except Exception:
                    detail = str(response.text)
                lower_detail = detail.lower()
                if response.status_code == 403:
                    office_error.value = detail or "You are not authorized to pass this document."
                elif response.status_code == 404:
                    office_error.value = "The selected document or receiving office could not be found."
                elif response.status_code == 409:
                    if "pending" in lower_detail or "already exists" in lower_detail:
                        office_error.value = "This document already has a pending handoff and cannot be passed again until it is received."
                    else:
                        office_error.value = detail or "The selected receiving office is not available for this handoff."
                else:
                    office_error.value = detail or "Unable to pass the document right now. Please try again."
                office_loading.value = ""
                submit_button.disabled = False
                page.update()
            except Exception as exc:
                office_error.value = str(exc) or "Unable to pass the document right now. Please try again."
                office_loading.value = ""
                submit_button.disabled = False
                page.update()

        submit_button.on_click = submit_handoff
        pass_document_dialog.title = ft.Text("Pass Document")
        pass_document_dialog.content = ft.Container(
            content=ft.Column(
                [
                    ft.Text(f"Document: {document.get('tracking_number') or document.get('id') or '—'}", size=12, weight=ft.FontWeight.W_600),
                    ft.Text(f"Title: {document.get('title') or '—'}", size=12, color=ft.Colors.BLUE_GREY_700),
                    office_loading,
                    office_error,
                    office_selector,
                    ft.Text("Review the receiving office and confirm before sending the handoff.", size=11, color=ft.Colors.BLUE_GREY_600),
                ],
                spacing=8,
                tight=True,
            ),
            padding=8,
            width=440,
        )
        pass_document_dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda _: close_pass_document_dialog()),
            submit_button,
        ]
        pass_document_dialog.open = True
        load_available_offices()
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

    def close_documents_bulk_archive_dialog():
        documents_bulk_archive_dialog.open = False
        page.update()

    def open_documents_bulk_archive_dialog():
        if not selected_qr_document_ids:
            return
        count = len(selected_qr_document_ids)
        documents_bulk_archive_dialog.title = ft.Text("Archive Selected Documents?")
        documents_bulk_archive_dialog.content = ft.Text(
            f"You are about to archive {count} document(s).\nThese documents will be moved from active Documents to Archived Documents."
        )
        documents_bulk_archive_dialog.open = True
        page.update()

    def run_bulk_archive_selected_documents():
        close_documents_bulk_archive_dialog()
        failed = []
        archived_count = 0
        for doc_id in list(selected_qr_document_ids):
            try:
                backend_api("DELETE", f"/documents/{doc_id}")
                archived_count += 1
            except Exception as exc:
                failed.append((doc_id, str(exc)))
        selected_qr_document_ids.clear()
        load_documents_table()
        if failed:
            show_document_notice(f"Archived {archived_count}; {len(failed)} failed: {failed[0][1]}")
        else:
            show_document_notice(f"{archived_count} document(s) archived. They are in Archived Documents.")

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

    def describe_document(doc):
        return f"{doc.get('tracking_number') or 'This document'} · {doc.get('title') or 'Untitled'}"

    def describe_selected_archived():
        names = [describe_document(doc) for doc in archived_documents_data if doc.get("id") in selected_archived_document_ids]
        hidden = len(selected_archived_document_ids) - len(names[:5])
        return "\n".join(names[:5]) + (f"\n…and {hidden} more" if hidden > 0 else "")

    def close_archived_restore_dialog():
        nonlocal pending_restore_document
        pending_restore_document = None
        archived_restore_dialog.open = False
        page.update()

    def confirm_restore_archived_document(doc):
        nonlocal pending_restore_document
        pending_restore_document = doc
        archived_restore_dialog.content = ft.Text(f"{describe_document(doc)}\n\nIt goes back on the Documents list with its office, file and history.")
        archived_restore_dialog.open = True
        page.update()

    def run_restore_archived_document_action():
        nonlocal pending_restore_document
        document = pending_restore_document
        close_archived_restore_dialog()
        if not document:
            return
        try:
            backend_api("POST", f"/documents/{document.get('id')}/restore")
            selected_archived_document_ids.discard(document.get("id"))
            show_document_notice(f"Restored {document.get('tracking_number') or 'the document'}. It is back on Documents.")
        except Exception as exc:
            show_document_notice(f"Restore failed: {exc}")
        archived_refresh()

    def close_archived_restore_selected_dialog():
        archived_restore_selected_dialog.open = False
        page.update()

    def open_archived_restore_selected_dialog():
        if not selected_archived_document_ids:
            return
        archived_restore_selected_dialog.title = ft.Text(f"Restore {len(selected_archived_document_ids)} document(s)?")
        archived_restore_selected_dialog.content = ft.Text(describe_selected_archived() + "\n\nThey go back on the Documents list.")
        archived_restore_selected_dialog.open = True
        page.update()

    def run_archived_bulk_action(method, path_suffix, done_text):
        failed = []
        succeeded = 0
        for doc_id in list(selected_archived_document_ids):
            try:
                backend_api(method, f"/documents/{doc_id}{path_suffix}")
                selected_archived_document_ids.discard(doc_id)
                succeeded += 1
            except Exception as exc:
                failed.append(str(exc))
        if failed:
            show_document_notice(f"{done_text} {succeeded}; {len(failed)} failed: {failed[0]}")
        else:
            show_document_notice(f"{done_text} {succeeded} document(s).")
        archived_refresh()

    def run_restore_selected_archived_documents_action():
        close_archived_restore_selected_dialog()
        run_archived_bulk_action("POST", "/restore", "Restored")

    def close_archived_delete_dialog():
        nonlocal pending_permanent_delete_document
        pending_permanent_delete_document = None
        archived_delete_dialog.open = False
        page.update()

    def close_archived_delete_selected_dialog():
        archived_delete_selected_dialog.open = False
        page.update()

    def open_archived_delete_selected_dialog():
        if not selected_archived_document_ids:
            return
        archived_delete_selected_dialog.title = ft.Text(f"Delete {len(selected_archived_document_ids)} document(s) permanently?")
        archived_delete_selected_dialog.content = ft.Text(describe_selected_archived() + "\n\nTheir records, files and tracking history are deleted. This cannot be undone.")
        archived_delete_selected_dialog.open = True
        page.update()

    def run_delete_selected_archived_documents_action():
        close_archived_delete_selected_dialog()
        run_archived_bulk_action("DELETE", "/permanent", "Permanently deleted")

    def confirm_permanent_delete_archived_document(doc):
        nonlocal pending_permanent_delete_document
        pending_permanent_delete_document = doc
        archived_delete_dialog.content = ft.Text(f"{describe_document(doc)}\n\nIts record, file and tracking history are deleted. This cannot be undone.")
        archived_delete_dialog.open = True
        page.update()

    def run_permanent_delete_archived_document_action():
        nonlocal pending_permanent_delete_document
        document = pending_permanent_delete_document
        close_archived_delete_dialog()
        if not document:
            return
        try:
            backend_api("DELETE", f"/documents/{document.get('id')}/permanent")
            selected_archived_document_ids.discard(document.get("id"))
            show_document_notice(f"Permanently deleted {document.get('tracking_number') or 'the document'}.")
        except Exception as exc:
            show_document_notice(f"Permanent delete failed: {exc}")
        archived_refresh()

    def download_selected_qr_labels():
        selected_ids = sorted(doc_id for doc_id in selected_qr_document_ids if doc_id is not None)
        if not selected_ids:
            show_document_notice("Select one or more documents to download QR labels.")
            return
        try:
            download_url = backend_api("POST", "/documents/qr/labels/download-token", json={"ids": selected_ids}).get("download_url")
            if not download_url:
                raise Exception("Download link was not returned")
            page.launch_url(download_url)
            close_qr_label_download_dialog()
            show_document_notice(f"Downloading QR labels for {len(selected_ids)} document(s).")
        except Exception as exc:
            show_document_notice(f"QR label download failed: {exc}")

    class DetailsSessionExpired(Exception):
        pass

    def details_api(method, path, **kwargs):
        """backend_api for the details dialog; an employee whose session lapsed is signed in again first."""
        def send():
            return requests.request(method, f"{BACKEND_URL}{path}", headers=get_admin_headers(), verify=False, timeout=15, **kwargs)

        response = send()
        if response.status_code == 401 and is_employee():
            refresh_runtime_token_if_needed(force=True)
            if not runtime_token:
                raise DetailsSessionExpired("Your session has expired. Please sign in again.")
            response = send()
        if response.status_code == 401 and is_employee():
            raise DetailsSessionExpired("Your session has expired. Please sign in again.")
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise Exception(detail)
        return response.json() if response.content else {}

    def load_document_qr_image(document_id):
        if is_employee() and not has_permission("view_qr_tracking"):
            return None
        try:
            response = requests.get(f"{BACKEND_URL}/documents/{document_id}/qr-image", headers=get_admin_headers(), verify=False, timeout=10)
            if response.status_code == 200:
                return base64.b64encode(response.content).decode("ascii")
        except Exception:
            pass
        return None

    def refresh_after_document_change():
        for refresh in (office_dashboard_refresh, documents_refresh):
            try:
                refresh()
            except Exception:
                pass

    def show_document_details(doc):
        if is_employee() and not runtime_token:
            _return_to_login_after_qr_details_401()
            return False
        try:
            open_document_details(
                page,
                documents_details_dialog,
                details_api,
                doc.get("id"),
                normalize=normalize_document,
                load_qr_image=load_document_qr_image,
                can_edit=has_permission("edit_documents"),
                can_download=has_permission("download_documents"),
                can_print=has_permission("print_documents"),
                open_pass=open_pass_document_dialog,
                open_edit=open_edit_document_dialog,
                preview=preview_document_pdf,
                download=download_document_attachment,
                on_change=refresh_after_document_change,
            )
        except DetailsSessionExpired:
            _return_to_login_after_qr_details_401()
            return False
        except Exception as exc:
            show_document_notice(f"Unable to load document details: {exc}")
            return False
        return True

    # QR generation/print functionality removed from frontend.

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
            "canonical_qr_url": doc.get("canonical_qr_url") or doc.get("qr_code_value") or "-",
            "attachment_name": doc.get("attachment_name") or "-",
            "remarks": doc.get("remarks") or "",
            "attachments": doc.get("attachments") or [],
            "document_number": doc.get("document_number"),
            "series_year": doc.get("series_year"),
            "current_office_id": doc.get("current_office_id"),
            "is_public": bool(doc.get("is_public", False)),
            "archived": bool(doc.get("archived", False)),
        }

    def delete_document_record(document_id):
        try:
            backend_api("DELETE", f"/documents/{document_id}")
            load_documents_table()
            show_document_notice("Document archived. It is in Archived Documents.")
        except Exception as exc:
            show_document_notice(f"Archive failed: {exc}")

    def preview_document_pdf(doc):
        attachments = [item for item in doc.get("attachments", []) if isinstance(item, dict)]
        pdf_attachment = next((item for item in attachments if (item.get("mime_type") or "").lower() == "application/pdf" or str(item.get("original_filename") or "").lower().endswith(".pdf")), None)
        if not pdf_attachment:
            show_document_notice("No PDF attachment available for this document.")
            return
        try:
            response = requests.post(
                f"{BACKEND_URL}/documents/{doc.get('id')}/attachments/{pdf_attachment.get('id')}/preview-token",
                headers=get_admin_headers(), verify=False, timeout=10,
            )
            if response.status_code != 200:
                raise Exception(response.text)
            preview_url = response.json().get("preview_url")
            if not preview_url:
                raise Exception("Preview URL was not returned")
            page.launch_url(preview_url)
        except Exception as exc:
            show_document_notice(f"Unable to preview PDF: {exc}")

    def print_document_pdf(doc):
        attachments = [item for item in doc.get("attachments", []) if isinstance(item, dict)]
        pdf_attachment = next(
            (
                item for item in attachments
                if (item.get("mime_type") or "").lower() == "application/pdf"
                or str(item.get("original_filename") or "").lower().endswith(".pdf")
            ),
            None,
        )
        if not pdf_attachment:
            show_document_notice("No PDF attachment available for printing.")
            return
        try:
            response = requests.post(
                f"{BACKEND_URL}/documents/{doc.get('id')}/attachments/{pdf_attachment.get('id')}/preview-token",
                headers=get_admin_headers(),
                verify=False,
                timeout=10,
            )
            if response.status_code != 200:
                raise Exception(response.text)
            preview_url = response.json().get("preview_url")
            if not preview_url:
                raise Exception("Print preview URL was not returned")
            page.launch_url(preview_url)
            show_document_notice("Print preview opened. Use the browser print command to print the document.")
        except Exception as exc:
            show_document_notice(f"Unable to open print preview: {exc}")

    def download_document_attachment(doc):
        attachments = [item for item in doc.get("attachments", []) if isinstance(item, dict) and item.get("id")]
        if not attachments:
            show_document_notice("No attachment available for this document.")
            return

        attachment = attachments[0]
        document_id = doc.get("id")
        attachment_id = attachment.get("id")
        # The app runs in the viewer's browser: hand that browser a download link, since a
        # file saved here would land on the machine running the app, not the viewer's.
        try:
            response = requests.post(
                f"{BACKEND_URL}/documents/{document_id}/attachments/{attachment_id}/download-token",
                headers=get_admin_headers(),
                verify=False,
                timeout=10,
            )
            if response.status_code != 200:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise Exception(f"{response.status_code} {detail}")
            download_url = response.json().get("download_url")
            if not download_url:
                raise Exception("Download link was not returned")
            page.launch_url(download_url)
            filename = attachment.get("original_filename") or "the attachment"
            show_document_notice(f"Downloading {filename} in your browser.")
        except Exception as exc:
            show_document_notice(f"Document download failed: {exc}")

    replace_attachment_document = None
    replace_attachment_record = None
    replacement_file = None
    replacement_file_label = ft.Text("No replacement file selected", size=12, color=ft.Colors.BLUE_GREY_600)
    replace_attachment_picker = ft.FilePicker(on_result=lambda e: None)
    page.overlay.append(replace_attachment_picker)

    def _on_replacement_file(e):
        nonlocal replacement_file
        try:
            if getattr(e, "files", None):
                selected = e.files[0]
                path = getattr(e, "path", None) or getattr(selected, "path", None)
                file_bytes = _trace_filepicker_file("replacement", selected)
                replacement_file = {"path": path, "name": getattr(selected, "name", None), "file_bytes": file_bytes, "selected_file_source": selected}
                replacement_file_label.value = replacement_file.get("name") or "Replacement file selected"
            else:
                replacement_file = None
                replacement_file_label.value = "No replacement file selected"
        except Exception:
            replacement_file = None
            replacement_file_label.value = "No replacement file selected"
        page.update()

    replace_attachment_picker.on_result = lambda e: _route_file_picker_result(
        current_file_picker_context,
        e,
        _on_registration_file,
        _on_bulk_pick,
        _on_replacement_file,
    )
    replace_attachment_dialog = ft.AlertDialog(
        title=ft.Text("Replace Attachment", size=20, weight=ft.FontWeight.BOLD),
        content=ft.Column(
            [
                ft.Text("The replacement must be a PDF, DOC, or DOCX file and must not duplicate existing file content.", size=12, color=ft.Colors.BLUE_GREY_600),
                ft.Text("Current attachment", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700),
                ft.Text("-", size=13),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.UPLOAD_FILE, color=ft.Colors.BLUE_700, size=22),
                        ft.Column([ft.Text("Replacement file", size=13, weight=ft.FontWeight.BOLD), replacement_file_label], spacing=3, expand=True),
                        ft.OutlinedButton("Choose file", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=lambda _: replace_attachment_picker.pick_files(file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["pdf", "doc", "docx"])),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
            width=620,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_replace_attachment_dialog()),
            ft.Button("Replace Attachment", icon=ft.Icons.UPLOAD_FILE, on_click=lambda _: submit_replace_attachment(), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
        ],
    )
    page.overlay.append(replace_attachment_dialog)

    def close_replace_attachment_dialog(_=None):
        nonlocal current_file_picker_context
        current_file_picker_context = None
        replace_attachment_dialog.open = False
        page.update()

    def open_replace_attachment_dialog(doc):
        nonlocal replace_attachment_document, replace_attachment_record, replacement_file, current_file_picker_context
        current_file_picker_context = "replacement"
        attachments = [item for item in doc.get("attachments", []) if isinstance(item, dict) and item.get("id")]
        if not attachments:
            show_document_notice("No attachment is available to replace.")
            return
        replace_attachment_document = doc
        replace_attachment_record = attachments[0]
        replacement_file = None
        replacement_file_label.value = "No replacement file selected"
        current_label = replace_attachment_dialog.content.controls[2]
        current_label.value = str(replace_attachment_record.get("original_filename") or doc.get("attachment_name") or "-")
        replace_attachment_dialog.open = True
        page.update()

    def submit_replace_attachment(_=None):
        if not replace_attachment_document or not replace_attachment_record:
            show_document_notice("No attachment is selected for replacement.")
            return
        if not replacement_file:
            show_document_notice("Choose a replacement file first.")
            return
        path = replacement_file.get("path")
        name = replacement_file.get("name") or "replacement.pdf"
        file_bytes = replacement_file.get("file_bytes")
        if file_bytes is None:
            file_bytes = _read_selected_file_bytes(replacement_file.get("selected_file_source"))
            print(
                "FILEPICKER TRACE "
                f"context=replacement_submit_reread result_length={len(file_bytes) if file_bytes is not None else None}",
                flush=True,
            )
            if file_bytes is None:
                if not path or not os.path.exists(path):
                    show_document_notice("Choose a replacement file first.")
                    return
                if not os.path.isabs(path):
                    path = os.path.abspath(path)
                with open(path, "rb") as handle:
                    file_bytes = handle.read()
        try:
            response = requests.post(
                f"{BACKEND_URL}/documents/{replace_attachment_document.get('id')}/attachments/{replace_attachment_record.get('id')}/replace",
                files={"file": (name, file_bytes, mimetypes.guess_type(name)[0] or "application/octet-stream")},
                headers=get_admin_headers(),
                verify=False,
                timeout=60,
            )
            if response.status_code != 200:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise Exception(f"{response.status_code} {detail}")
            close_replace_attachment_dialog()
            load_documents_table()
            show_document_notice("Attachment replaced successfully.")
        except Exception as exc:
            show_document_notice(f"Attachment replacement failed: {exc}")

    def set_document_visibility(doc, is_public):
        document_id = doc.get("id")
        if not document_id:
            show_document_notice("Unable to change visibility: document ID is missing.")
            return
        try:
            response = requests.put(
                f"{BACKEND_URL}/documents/{document_id}",
                json={"is_public": bool(is_public)},
                headers=get_admin_headers(),
                verify=False,
                timeout=15,
            )
            if response.status_code != 200:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise Exception(f"{response.status_code} {detail}")
            load_documents_table()
            show_document_notice(f"Document is now {'public' if is_public else 'private'}.")
        except Exception as exc:
            show_document_notice(f"Visibility update failed: {exc}")

    def load_archived_documents_table():
        archived_refresh()

    def load_documents_table():
        documents_refresh()

    def documents_view():
        nonlocal documents_refresh
        if not has_permission("view_documents"):
            return ft.Column([ft.Text("You do not have access to documents.")])
        # The register, multiple registration and edit dialogs take their category and type options from here.
        load_active_definition_options()
        view, documents_refresh = build_documents_view(
            page,
            backend_api,
            surface_card,
            section_header,
            normalize=normalize_document,
            selection=selected_qr_document_ids,
            loaded=documents_data,
            can_search=has_permission("search_documents"),
            can_filter=has_permission("filter_documents"),
            can_register=has_permission("register_documents"),
            can_import=has_permission("import_documents"),
            can_archive=has_permission("archive_documents"),
            can_print_qr=has_permission("print_qr_codes"),
            can_view_details=has_permission("view_document_details"),
            can_download=has_permission("download_documents"),
            can_print=has_permission("print_documents"),
            can_edit=has_permission("edit_documents"),
            open_details=show_document_details,
            open_register=open_register_document_dialog,
            open_bulk_register=open_bulk_register_document_dialog,
            open_edit=open_edit_document_dialog,
            open_replace_attachment=open_replace_attachment_dialog,
            preview=preview_document_pdf,
            print_document=print_document_pdf,
            download=download_document_attachment,
            set_visibility=set_document_visibility,
            archive=confirm_delete_document,
            archive_selected=open_documents_bulk_archive_dialog,
            qr_labels=open_qr_label_download_dialog,
        )
        return view

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
            default_system_settings = {
                "organization_name": "LGU Tolosa",
                "system_name": "LGU Tolosa Legislative Document Tracking System",
                "public_portal_enabled": True,
                "maintenance_mode": False,
                "session_timeout_minutes": 60,
                "upload_max_size_mb": 25,
            }
            try:
                resp = requests.get(f"{BACKEND_URL}/system-settings", headers=get_admin_headers(), verify=False, timeout=15)
                if resp.status_code == 200:
                    remote_settings = resp.json().get("settings") or {}
                    default_system_settings.update({key: value for key, value in remote_settings.items() if key in default_system_settings})
            except Exception:
                pass

            org_name_field = ft.TextField(label="Organization Name", value=str(default_system_settings.get("organization_name", "LGU Tolosa")), width=360)
            system_name_field = ft.TextField(label="System Name", value=str(default_system_settings.get("system_name", "LGU Tolosa Legislative Document Tracking System")), width=360)
            maintenance_switch = ft.Switch(label="Maintenance Mode", value=bool(default_system_settings.get("maintenance_mode", False)))
            public_portal_switch = ft.Switch(label="Public Portal Enabled", value=bool(default_system_settings.get("public_portal_enabled", True)))
            session_timeout_field = ft.TextField(label="Session Timeout (minutes)", value=str(default_system_settings.get("session_timeout_minutes", 60)), width=180)
            upload_size_field = ft.TextField(label="Max Upload Size (MB)", value=str(default_system_settings.get("upload_max_size_mb", 25)), width=180)

            def save_system_settings(_):
                try:
                    payload = {
                        "settings": {
                            "organization_name": (org_name_field.value or "LGU Tolosa").strip() or "LGU Tolosa",
                            "system_name": (system_name_field.value or "LGU Tolosa Legislative Document Tracking System").strip() or "LGU Tolosa Legislative Document Tracking System",
                            "maintenance_mode": bool(maintenance_switch.value),
                            "public_portal_enabled": bool(public_portal_switch.value),
                            "session_timeout_minutes": int(str(session_timeout_field.value or "60").strip() or "60"),
                            "upload_max_size_mb": int(str(upload_size_field.value or "25").strip() or "25"),
                        }
                    }
                    response = requests.put(f"{BACKEND_URL}/system-settings", headers=get_admin_headers(), json=payload, verify=False, timeout=15)
                    if response.status_code == 200:
                        page.snack_bar = ft.SnackBar(ft.Text("System settings saved successfully."), open=True)
                    else:
                        detail = response.json().get("detail", "Unable to save system settings.") if response.headers.get("content-type", "").startswith("application/json") else "Unable to save system settings."
                        page.snack_bar = ft.SnackBar(ft.Text(str(detail)[:180]), open=True)
                except Exception as exc:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Unable to save system settings: {exc}"), open=True)
                page.update()

            system_configuration_card = surface_card(
                ft.Column([
                    section_header("System Configuration", "Authorized administration settings for the application.", ft.Icons.SETTINGS_APPLICATIONS_OUTLINED, ft.Colors.BLUE_700),
                    ft.Divider(height=1),
                    ft.Text("Organization Information", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Row([org_name_field, system_name_field], wrap=True, spacing=12),
                    ft.Text("Operational Controls", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Row([
                        maintenance_switch,
                        public_portal_switch,
                    ], wrap=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Text("Storage and Session Settings", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_700 if not is_dark else ft.Colors.BLUE_GREY_200),
                    ft.Row([session_timeout_field, upload_size_field], wrap=True, spacing=12),
                    ft.Row([
                        ft.ElevatedButton("Save System Settings", icon=ft.Icons.SAVE_OUTLINED, on_click=save_system_settings),
                    ], alignment=ft.MainAxisAlignment.END),
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
                ("Today's Documents", ["set_documents_for_sb_members"]),
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
        return build_qr_tracking_view(
            page, backend_api, surface_card, section_header,
            open_details=show_document_details if has_permission("view_document_details") else None,
        )

    office_options = []
    office_management_data = []

    def load_office_options():
        nonlocal office_options
        try:
            response = requests.get(
                f"{BACKEND_URL}/auth/offices",
                headers=get_admin_headers(),
                verify=False,
                timeout=20,
            )
            if response.status_code != 200:
                raise Exception(response.text)
            office_options = response.json() if response.content else []
        except Exception as exc:
            office_options = []
            page.snack_bar = ft.SnackBar(ft.Text(f"Unable to load offices: {exc}"), open=True)

    def load_office_management_data():
        nonlocal office_management_data
        try:
            response = requests.get(
                f"{BACKEND_URL}/offices",
                headers=get_admin_headers(),
                verify=False,
                timeout=20,
            )
            if response.status_code != 200:
                raise Exception(response.text)
            office_management_data = response.json() if response.content else []
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Unable to load office management: {exc}"), open=True)

    def refresh_office_filter_options():
        selected = user_office_filter.value or "All"
        source = office_management_data or office_options
        names = [item.get("name") for item in source if item.get("name")]
        user_office_filter.options = [ft.dropdown.Option("All")] + [ft.dropdown.Option(name) for name in names]
        user_office_filter.value = selected if selected == "All" or selected in names else "All"

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
    office_table_holder = ft.Container(width="100%")
    user_no_users_notice = ft.Container(width="100%", visible=False)

    def update_users_role_view(_=None):
        visible_users = filter_user_data()
        user_table_holder.content = build_users_roles_table(
            visible_users,
            lambda item=None: open_view_user_dialog(item or visible_users[0] if visible_users else {}),
            lambda item=None: open_edit_user_dialog(item or visible_users[0] if visible_users else {}),
            lambda item=None: open_reset_password_dialog(item or visible_users[0] if visible_users else {}),
            lambda item=None: delete_user(item or visible_users[0] if visible_users else {}),
            unlock_user=unlock_user if current_user_role == "Super Administrator" else None,
        )
        office_table_holder.content = build_offices_table(
            office_management_data,
            open_edit_office_dialog,
            open_view_office_users_dialog,
        )
        user_no_users_notice.visible = len(visible_users) == 0
        page.update()

    def refresh_user_management_data(_=None):
        load_office_options()
        load_office_management_data()
        refresh_office_filter_options()
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
        load_office_options()
        load_office_management_data()
        refresh_office_filter_options()
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
            offices_data=office_management_data,
            create_office=open_create_office_dialog,
            edit_office=open_edit_office_dialog,
            view_office_users=open_view_office_users_dialog,
            office_table_holder=office_table_holder,
            create_employee=lambda _: open_create_user_dialog(employee_only=True),
            unlock_user=unlock_user if current_user_role == "Super Administrator" else None,
        )
        update_users_role_view()
        return view

    def refresh_office_data():
        load_office_options()
        load_office_management_data()
        refresh_office_filter_options()
        load_user_management_data()

    def open_office_form_dialog(office=None):
        editing = office is not None
        office_name = ft.TextField(label="Office Name", value=(office or {}).get("name", ""), autofocus=True)
        office_code = ft.TextField(label="Office Code", value=(office or {}).get("office_code", ""))
        office_status = ft.Dropdown(
            label="Status",
            options=[ft.dropdown.Option("Active"), ft.dropdown.Option("Inactive")],
            value="Active" if not editing or office.get("is_active") else "Inactive",
        )
        error_message = ft.Text("", color=ft.Colors.RED_700, size=12)

        def save_office(_):
            if not office_name.value or not office_name.value.strip() or not office_code.value or not office_code.value.strip():
                error_message.value = "Office name and office code are required."
                page.update()
                return
            payload = {
                "name": office_name.value.strip(),
                "office_code": office_code.value.strip(),
                "is_active": office_status.value == "Active",
            }
            try:
                response = requests.put(
                    f"{BACKEND_URL}/offices/{office.get('id')}",
                    json=payload,
                    headers=get_admin_headers(),
                    verify=False,
                    timeout=20,
                ) if editing else requests.post(
                    f"{BACKEND_URL}/offices",
                    json=payload,
                    headers=get_admin_headers(),
                    verify=False,
                    timeout=20,
                )
                if response.status_code not in (200, 201):
                    try:
                        detail = response.json().get("detail", response.text)
                    except Exception:
                        detail = response.text
                    raise Exception(detail)
                close_dialog(dialog)
                refresh_office_data()
            except Exception as exc:
                error_message.value = f"Unable to {'update' if editing else 'create'} office: {exc}"
                page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Edit Office" if editing else "Add Office"),
            content=ft.Column([office_name, office_code, office_status, error_message], tight=True, spacing=10),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: close_dialog(dialog)),
                ft.Button(
                    "Save Changes" if editing else "Create Office",
                    on_click=save_office,
                    bgcolor=ft.Colors.BLUE_800,
                    color=ft.Colors.WHITE,
                ),
            ],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def open_create_office_dialog(_=None):
        open_office_form_dialog()

    def open_edit_office_dialog(office):
        open_office_form_dialog(office)

    def open_view_office_users_dialog(office):
        try:
            response = requests.get(
                f"{BACKEND_URL}/offices/{office.get('id')}/users",
                headers=get_admin_headers(),
                verify=False,
                timeout=20,
            )
            if response.status_code != 200:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise Exception(detail)
            office_users = response.json() if response.content else []
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Unable to load office users: {exc}"), open=True)
            page.update()
            return
        user_rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(user.get("full_name") or user.get("username") or "-")),
                    ft.DataCell(ft.Text(user.get("username") or "-")),
                    ft.DataCell(ft.Text(user.get("role") or "-")),
                    ft.DataCell(ft.Text(user.get("status") or "-")),
                ]
            )
            for user in office_users
        ]
        content = (
            ft.Row(
                [
                    ft.DataTable(
                        columns=[ft.DataColumn(ft.Text(label)) for label in ("Name", "Username", "Role", "Status")],
                        rows=user_rows,
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
            )
            if office_users
            else ft.Text("No users are assigned to this office.", size=13, color=ft.Colors.BLUE_GREY_600)
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Users in {office.get('name') or 'Office'}"),
            content=ft.Container(content=content, width=760),
            actions=[ft.TextButton("Close", on_click=lambda _: close_dialog(dialog))],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def open_create_user_dialog(employee_only=False):
        full_name = ft.TextField(label="Full Name")
        username = ft.TextField(label="Username")
        email = ft.TextField(label="Email")
        password = ft.TextField(label="Temporary Password", password=True, can_reveal_password=True)
        confirm_password = ft.TextField(label="Confirm Password", password=True, can_reveal_password=True)
        role_choice = None if employee_only else ft.Dropdown(
            label="Role",
            options=[
                ft.dropdown.Option("Employee"),
                ft.dropdown.Option("SB Member"),
            ],
            value="Employee",
        )
        office_placeholder = "Select an office" if employee_only else "Unassigned"
        office_choice = ft.Dropdown(
            label="Department/Office",
            options=[ft.dropdown.Option(office_placeholder)] + [
                ft.dropdown.Option(item["name"])
                for item in office_options
                if item.get("name")
            ],
            value=office_placeholder,
        )

        permission_area = ft.Column([], spacing=8)
        selected_create_permissions = set()
        create_master_check = ft.Checkbox(label="Select All Permissions", tristate=True, scale=1.05)
        office_permission_labels = OFFICE_EMPLOYEE_PERMISSION_GROUP["Office Workflow"]

        def selected_role():
            return "Employee" if employee_only else role_choice.value

        def create_permission_key(label):
            return label.strip().lower().replace(" ", "_")

        def create_permission_groups():
            groups = dict(EMPLOYEE_PERMISSION_GROUPS)
            if selected_role() == "Employee" and office_choice.value != office_placeholder:
                groups.update(OFFICE_EMPLOYEE_PERMISSION_GROUP)
            return groups

        def update_create_master():
            groups = create_permission_groups()
            total = sum(len(items) for items in groups.values())
            count = sum(
                create_permission_key(label) in selected_create_permissions
                for labels in groups.values()
                for label in labels
            )
            create_master_check.value = True if count == total else None if count else False

        def set_all_create_permissions(event):
            selected_create_permissions.clear()
            if event.control.value:
                selected_create_permissions.update(
                    create_permission_key(label)
                    for labels in create_permission_groups().values()
                    for label in labels
                )
            render_permission_section()

        def render_permission_section():
            permission_area.controls.clear()
            office_choice.visible = employee_only or selected_role() == "Employee"
            if not office_choice.visible:
                office_choice.value = office_placeholder
            if employee_only:
                has_office = office_choice.value != office_placeholder
                permission_area.controls.extend([
                    ft.Text("Office Access", weight=ft.FontWeight.BOLD, size=14, color=ft.Colors.BLUE_GREY_800),
                    ft.Text(
                        "This employee will automatically receive access to:" if has_office else "Select an office to automatically assign the standard office permissions.",
                        size=12,
                        color=ft.Colors.BLUE_GREY_600,
                    ),
                ])
                if has_office:
                    permission_area.controls.append(ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=ft.Colors.GREEN_700),
                            ft.Text(label, size=12, color=ft.Colors.BLUE_GREY_800),
                        ], spacing=8)
                        for label in office_permission_labels
                    ], spacing=4))
            elif selected_role() == "Employee":
                permission_groups = create_permission_groups()
                permission_count = sum(len(items) for items in permission_groups.values())
                permission_area.controls.append(ft.Text("Employee Permissions", weight=ft.FontWeight.BOLD, size=16, color=ft.Colors.BLUE_GREY_800))
                permission_area.controls.append(ft.Text("Control access to the features available to this employee.", size=12, color=ft.Colors.BLUE_GREY_600))
                selected_count = sum(
                    create_permission_key(label) in selected_create_permissions
                    for labels in permission_groups.values()
                    for label in labels
                )
                permission_area.controls.append(ft.Row([create_master_check, ft.Text(f"{selected_count} of {permission_count} permissions selected", size=12)], spacing=12))
                for section_name, perms in permission_groups.items():
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
            for label in create_permission_groups()[group_name]:
                key = create_permission_key(label)
                if event.control.value:
                    selected_create_permissions.add(key)
                else:
                    selected_create_permissions.discard(key)
            update_create_master()
            render_permission_section()

        if role_choice is not None:
            role_choice.on_change = lambda _: render_permission_section()
        office_choice.on_change = lambda _: render_permission_section()
        create_master_check.on_change = set_all_create_permissions
        render_permission_section()

        def create_account(_):
            if not full_name.value or not username.value or not email.value:
                error_message.value = "Full name, username, and email are required."
                page.update()
                return

            if not password.value:
                error_message.value = "Password is required."
                page.update()
                return

            selected_office = next(
                (
                    item for item in office_options
                    if selected_role() == "Employee" and item.get("name") == office_choice.value
                ),
                None,
            )
            if employee_only and selected_office is None:
                error_message.value = "Please select a Department/Office."
                page.update()
                return

            if password.value != confirm_password.value:
                error_message.value = "Passwords do not match."
                page.update()
                return

            if not runtime_token and not AUTH_TOKEN:
                error_message.value = "Unable to register user: no admin authentication available."
                page.update()
                return

            payload = {
                "username": username.value.strip(),
                "password": password.value,
                "full_name": full_name.value.strip(),
                "email": email.value.strip(),
                "role": selected_role(),
            }
            if selected_office:
                payload["office_id"] = selected_office.get("id")
            available_permissions = {
                create_permission_key(label)
                for labels in create_permission_groups().values()
                for label in labels
            }
            permissions = sorted(selected_create_permissions & available_permissions)
            if not employee_only and (permissions or selected_office):
                payload["permissions"] = permissions

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
                    "id": body.get("id"),
                    "full_name": full_name.value,
                    "username": body.get("username", username.value.strip()),
                    "email": email.value,
                    "role": body.get("role") or selected_role(),
                    "office_id": body.get("office_id"),
                    "department": office_choice.value if selected_office else None,
                    "status": "Active",
                    "permissions": body.get("permissions", permissions),
                    "last_login": "—",
                    "created": date.today().strftime("%Y-%m-%d"),
                }
                user_management_data.append(created_user)
                close_dialog(dialog)
                refresh_office_data()
            except Exception as exc:
                error_message.value = f"Account creation failed: {exc}"
                page.update()
                return

        error_message = ft.Text("", color=ft.Colors.RED_700, size=12)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Create Employee Account" if employee_only else "Create User Account"),
            content=ft.Container(
                content=ft.Column([
                    full_name,
                    username,
                    email,
                    password,
                    confirm_password,
                    *([role_choice] if role_choice is not None else []),
                    office_choice,
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
                    ft.Text(f"Department/Office: {user.get('department') or 'Unassigned'}") ,
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
        full_name = ft.TextField(label="Full Name", value=user.get("full_name", ""), width=270)
        username = ft.TextField(label="Username", value=user.get("username", ""), width=270)
        email = ft.TextField(label="Email", value=user.get("email", ""), width=270)
        is_super_admin = user.get("role") == "Super Administrator"
        edit_office_options = list(office_options)
        current_office = next(
            (item for item in office_management_data if item.get("id") == user.get("office_id")),
            None,
        )
        if current_office and all(item.get("id") != current_office.get("id") for item in edit_office_options):
            edit_office_options.append(current_office)
        selected_office = next(
            (item for item in edit_office_options if item.get("id") == user.get("office_id")),
            None,
        )
        role_choice = ft.Dropdown(
            label="Role",
            value=user.get("role", "Employee"),
            options=[ft.dropdown.Option("Employee"), ft.dropdown.Option("SB Member"), ft.dropdown.Option("Super Administrator")],
            width=270,
            autofocus=False,
            disabled=is_super_admin,
        )
        office_choice = ft.Dropdown(
            label="Department/Office",
            options=[ft.dropdown.Option("Unassigned")] + [
                ft.dropdown.Option(item["name"])
                for item in edit_office_options
                if item.get("name")
            ],
            value=(selected_office or {}).get("name") or user.get("department") or "Unassigned",
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
        permission_groups = dict(EMPLOYEE_PERMISSION_GROUPS)
        if user.get("role") == "Employee" and user.get("office_id") is not None:
            permission_groups.update(OFFICE_EMPLOYEE_PERMISSION_GROUP)
        group_descriptions = {
            "Dashboard": "Control access to dashboard information.",
            "Documents": "Control actions employees can perform on legislative documents.",
            "QR Code": "Control QR code generation, printing, and tracking access.",
            "Today's Documents": "Let this employee set the documents SB Members see for the day.",
            "Users & Roles": "Control employee access to user and role administration.",
            "Committees": "Control committee management permissions.",
            "Audit Logs": "Control access to system activity records.",
            "Analytics": "Control access to analytics and reports.",
            "Settings": "Control access to system configuration.",
            "Office Workflow": "Control this employee's access to future office document functions.",
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
            if role_choice.value == "Super Administrator":
                permission_cards.controls.append(ft.Text("Full system access. Super Administrator permissions cannot be reduced here.", size=12, color=ft.Colors.BLUE_GREY_600))
                update_permission_state()
                page.update()
                return
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
            if is_super_admin:
                payload["permissions"] = ["*"]
            selected_office = next(
                (item for item in edit_office_options if item.get("name") == office_choice.value),
                None,
            )
            payload["office_id"] = selected_office.get("id") if selected_office else None
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
                refresh_office_data()
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
                    office_choice,
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
        new_password = ft.TextField(label="New Password", password=True, can_reveal_password=True)
        confirm_password = ft.TextField(label="Confirm New Password", password=True, can_reveal_password=True)
        error_message = ft.Text("", color=ft.Colors.RED_700, size=12)

        def reset_password(_):
            if not new_password.value:
                error_message.value = "New password is required."
                page.update()
                return
            if new_password.value != confirm_password.value:
                error_message.value = "Passwords do not match."
                page.update()
                return
            if len(new_password.value) < 8:
                error_message.value = "Password must be at least 8 characters long."
                page.update()
                return
            try:
                response = requests.post(
                    f"{BACKEND_URL}/auth/users/{user.get('id')}/reset-password",
                    json={
                        "new_password": new_password.value,
                        "confirm_password": confirm_password.value,
                    },
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
                page.snack_bar = ft.SnackBar(ft.Text("User password reset successfully."), open=True)
                page.update()
            except Exception as exc:
                error_message.value = f"Unable to reset password: {exc}"
                page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Reset Password"),
            content=ft.Column([
                ft.Text("Are you sure you want to reset this user's password?"),
                ft.Text(f"User: {user.get('full_name', 'Unknown User')} ({user.get('username', '')})", color=ft.Colors.BLUE_GREY_700),
                new_password,
                confirm_password,
                error_message,
            ], tight=True, spacing=8),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: close_dialog(dialog)),
                ft.Button("Reset Password", on_click=reset_password, bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE),
            ],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def delete_user(user):
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

    def unlock_user(user):
        def confirm_unlock():
            try:
                response = requests.post(
                    f"{BACKEND_URL}/auth/users/{user.get('id')}/unlock",
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
                page.snack_bar = ft.SnackBar(ft.Text(f"{user.get('username', 'User')} can sign in again."), open=True)
                load_user_management_data()
            except Exception as exc:
                close_dialog(dialog)
                page.snack_bar = ft.SnackBar(ft.Text(f"Unable to unlock account: {exc}"), open=True)
                page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Unlock Login"),
            content=ft.Text(
                f"{user.get('full_name', user.get('username', 'This user'))} is locked out after too many failed logins. "
                "Unlock now so they can sign in again?"
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: close_dialog(dialog)),
                ft.Button("Unlock", on_click=lambda _: confirm_unlock(), bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE),
            ],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def close_dialog(dialog):
        dialog.open = False
        page.update()

    def backend_api(method, path, **kwargs):
        response = requests.request(method, f"{BACKEND_URL}{path}", headers=get_admin_headers(), verify=False, timeout=15, **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise Exception(detail)
        return response.json() if response.content else {}

    def todays_documents_page():
        return build_todays_documents_view(page, backend_api, surface_card, section_header)

    def users_role_page():
        return users_roles_view()

    def logout_user():
        nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
        if runtime_token:
            try:
                requests.post(
                    f"{BACKEND_URL}/auth/logout",
                    headers={"Authorization": f"Bearer {runtime_token}"},
                    verify=False,
                    timeout=10,
                )
            except Exception:
                pass
        current_user = None
        current_user_role = None
        current_user_permissions = []
        runtime_token = None
        refresh_token = None
        clear_session_state()
        clear_pending_qr_token()
        show_login()

    def archived_documents_view():
        nonlocal archived_refresh
        if not has_permission("view_documents"):
            return ft.Column([ft.Text("You do not have access to archived documents.")])
        view, archived_refresh = build_documents_view(
            page,
            backend_api,
            surface_card,
            section_header,
            normalize=normalize_document,
            selection=selected_archived_document_ids,
            loaded=archived_documents_data,
            archived=True,
            can_search=has_permission("search_documents"),
            can_filter=has_permission("filter_documents"),
            can_view_details=has_permission("view_document_details"),
            can_restore=has_permission("restore_documents"),
            can_delete=has_permission("delete_documents"),
            open_details=show_document_details,
            restore=confirm_restore_archived_document,
            restore_selected=open_archived_restore_selected_dialog,
            delete_permanently=confirm_permanent_delete_archived_document,
            delete_selected=open_archived_delete_selected_dialog,
        )
        return view

    def open_documents_module():
        target_index = next((idx for idx, (_, label, *_) in enumerate(nav_items) if label == "Documents"), 0)
        render_shell(page, current_user, logout_user, nav_items, documents_view(), initial_selected_index=target_index)

    def open_archived_documents_module():
        target_index = next((idx for idx, (_, label, *_) in enumerate(nav_items) if label == "Archived Documents"), 0)
        render_shell(page, current_user, logout_user, nav_items, archived_documents_view(), initial_selected_index=target_index)

    def dashboard_view():
        analytics_payload = {}
        try:
            analytics_response = requests.get(
                f"{BACKEND_URL}/analytics",
                headers=get_admin_headers(),
                verify=False,
                timeout=10,
            )
            if analytics_response.status_code == 200 and analytics_response.content:
                analytics_payload = analytics_response.json() or {}
        except Exception:
            analytics_payload = {}

        try:
            load_documents_table()
            load_archived_documents_table()
        except Exception:
            pass

        fallback_total_docs = len(documents_data) + len(archived_documents_data)
        fallback_active_docs = sum(1 for doc in documents_data if (doc.get("status") or "").lower() not in {"approved", "completed", "archived"})
        fallback_pending_docs = sum(1 for doc in documents_data if (doc.get("status") or "").lower() == "pending")
        fallback_completed_docs = sum(1 for doc in documents_data if (doc.get("status") or "").lower() in {"approved", "completed"})
        fallback_archived_docs = len(archived_documents_data)
        fallback_users_total = len(user_management_data)
        fallback_users_active = sum(1 for user in user_management_data if (user.get("status") or "").lower() == "active")
        fallback_users_inactive = sum(1 for user in user_management_data if (user.get("status") or "").lower() != "active")

        overview = analytics_payload.get("overview") or {}
        user_metrics = analytics_payload.get("users") or {}

        total_docs = overview.get("total_documents", fallback_total_docs)
        active_docs = overview.get("active_documents", fallback_active_docs)
        pending_docs = overview.get("pending_documents", fallback_pending_docs)
        completed_docs = overview.get("completed_documents", fallback_completed_docs)
        archived_docs = overview.get("archived_documents", fallback_archived_docs)
        users_total = user_metrics.get("total", fallback_users_total)
        users_active = user_metrics.get("active", fallback_users_active)
        users_inactive = user_metrics.get("inactive", fallback_users_inactive)
        users_employees = sum(1 for user in user_management_data if user.get("role") == "Employee")
        users_sb_members = sum(1 for user in user_management_data if user.get("role") == "SB Member")
        summary_items = [
            {"title": "Total Documents", "value": str
            (total_docs), "detail": "Active + archived documents", "icon": ft.Icons.DESCRIPTION_OUTLINED, "accent": ft.Colors.BLUE_700},
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
            {"title": "Inactive Users", "value": str(users_inactive), "detail": "Disabled accounts", "icon": ft.Icons.PERSON_OFF_OUTLINED, "accent": ft.Colors.RED_700},
        ]

        recent_activity = analytics_payload.get("recent_activity") or []
        activity_rows = []
        for item in recent_activity[:5]:
            activity = str(item.get("activity") or "Activity")
            actor = str(item.get("actor") or "System")
            target = str(item.get("tracking_number") or "-")
            timestamp = str(item.get("created_at") or "-").replace("T", " ").replace("Z", "")
            if "." in timestamp:
                timestamp = timestamp.split(".", 1)[0]
            target_text = f"Target: {target}" if target != "-" else "System event"
            activity_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.HISTORY_OUTLINED, size=18, color=ft.Colors.BLUE_700),
                            ft.Column(
                                [
                                    ft.Text(activity, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                                    ft.Text(f"{actor} - {target_text}", size=11, color=ft.Colors.BLUE_GREY_600),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Text(timestamp, size=10, color=ft.Colors.BLUE_GREY_500),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=8,
                    bgcolor=ft.Colors.WHITE,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    border_radius=8,
                )
            )
        if not activity_rows:
            activity_rows.append(ft.Text("No recent system activity", size=12, color=ft.Colors.BLUE_GREY_600))

        recent_activity_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.HISTORY_OUTLINED, color=ft.Colors.BLUE_700, size=21),
                            ft.Text("Recent System Activity", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                        ],
                        spacing=8,
                    ),
                    *activity_rows,
                ],
                spacing=8,
            ),
            padding=12,
            bgcolor=ft.Colors.BLUE_GREY_50,
            border_radius=10,
        )

        recent_security_events = analytics_payload.get("recent_security_events") or []
        security_rows = []
        for event in recent_security_events[:5]:
            status = str(event.get("status") or "Success")
            action = str(event.get("action") or "Security event")
            actor = str(event.get("actor") or "System")
            target = str(event.get("target_id") or "-")
            details = str(event.get("details") or "")
            timestamp = str(event.get("created_at") or "-").replace("T", " ").replace("Z", "")
            if "." in timestamp:
                timestamp = timestamp.split(".", 1)[0]
            security_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.SECURITY_OUTLINED,
                                size=18,
                                color=ft.Colors.RED_700 if status == "Failed" else ft.Colors.BLUE_700,
                            ),
                            ft.Column(
                                [
                                    ft.Text(action, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                                    ft.Text(f"{actor} - {target}", size=11, color=ft.Colors.BLUE_GREY_600),
                                    ft.Text(details, size=10, color=ft.Colors.BLUE_GREY_500, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS) if details else ft.Text(status, size=10, color=ft.Colors.BLUE_GREY_500),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Text(timestamp, size=10, color=ft.Colors.BLUE_GREY_500),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=8,
                    bgcolor=ft.Colors.WHITE,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    border_radius=8,
                )
            )
        if not security_rows:
            security_rows.append(ft.Text("No recent security events", size=12, color=ft.Colors.BLUE_GREY_600))

        recent_security_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SECURITY_OUTLINED, color=ft.Colors.RED_700, size=21),
                            ft.Text("Recent Security Events", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                        ],
                        spacing=8,
                    ),
                    *security_rows,
                ],
                spacing=8,
            ),
            padding=12,
            bgcolor=ft.Colors.BLUE_GREY_50,
            border_radius=10,
        )

        def format_storage_size(value):
            try:
                amount = float(value or 0)
            except (TypeError, ValueError):
                return "Unavailable"
            units = ("B", "KB", "MB", "GB", "TB")
            unit_index = 0
            while amount >= 1024 and unit_index < len(units) - 1:
                amount /= 1024
                unit_index += 1
            return f"{amount:.1f} {units[unit_index]}"

        storage_data = analytics_payload.get("storage") or {}
        storage_status = str(storage_data.get("status") or "unavailable").capitalize()
        storage_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.STORAGE_OUTLINED, color=ft.Colors.BLUE_700, size=21),
                            ft.Text("Storage Usage", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                        ],
                        spacing=8,
                    ),
                    ft.Text(f"Status: {storage_status}", size=11, color=ft.Colors.BLUE_GREY_700),
                    ft.Text(
                        f"Document storage: {format_storage_size(storage_data.get('document_storage_bytes'))} ({storage_data.get('stored_document_files', 0)} files)",
                        size=11,
                        color=ft.Colors.BLUE_GREY_700,
                    ),
                    ft.Text(
                        f"Temporary uploads: {format_storage_size(storage_data.get('temporary_upload_storage_bytes'))} ({storage_data.get('temporary_upload_files', 0)} files)",
                        size=11,
                        color=ft.Colors.BLUE_GREY_700,
                    ),
                    ft.Text(
                        f"Available disk: {format_storage_size(storage_data.get('available_disk_bytes'))}",
                        size=11,
                        color=ft.Colors.BLUE_GREY_700,
                    ),
                ],
                spacing=7,
            ),
            padding=12,
            bgcolor=ft.Colors.BLUE_GREY_50,
            border_radius=10,
        )

        health_payload = {}
        try:
            health_response = requests.get(
                f"{BACKEND_URL}/health",
                headers=get_admin_headers(),
                verify=False,
                timeout=10,
            )
            if health_response.status_code == 200 and health_response.content:
                health_payload = health_response.json() or {}
        except Exception:
            health_payload = {}

        health_components = [
            ("Backend", health_payload.get("backend") or {}),
            ("Database", health_payload.get("database") or {}),
            ("Document Storage", health_payload.get("document_storage") or {}),
            ("Temporary Upload Storage", health_payload.get("temporary_upload_storage") or {}),
        ]
        health_rows = []
        for label, component in health_components:
            status = str(component.get("status") or "unavailable").capitalize()
            status_color = ft.Colors.GREEN_700 if status == "Operational" else ft.Colors.ORANGE_700 if status == "Warning" else ft.Colors.RED_700
            health_rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CIRCLE, size=10, color=status_color),
                        ft.Text(label, size=11, color=ft.Colors.BLUE_GREY_700, expand=True),
                        ft.Text(status, size=11, weight=ft.FontWeight.BOLD, color=status_color),
                    ],
                    spacing=7,
                )
            )

        system_health_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.MONITOR_HEART_OUTLINED, color=ft.Colors.GREEN_700, size=21),
                            ft.Text("System Health", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                        ],
                        spacing=8,
                    ),
                    *health_rows,
                ],
                spacing=8,
            ),
            padding=12,
            bgcolor=ft.Colors.BLUE_GREY_50,
            border_radius=10,
        )

        def analytics_summary(title, values):
            rows = [ft.Text(title, size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900)]
            if values:
                for label, count in list(values.items())[:6]:
                    rows.append(ft.Text(f"{label}: {count}", size=11, color=ft.Colors.BLUE_GREY_700))
            else:
                rows.append(ft.Text("No data available", size=11, color=ft.Colors.BLUE_GREY_600))
            return ft.Container(
                content=ft.Column(rows, spacing=5),
                padding=10,
                bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                border_radius=8,
                width=250,
            )

        monthly_values = {
            str(item.get("label") or item.get("month") or "-"): item.get("count", 0)
            for item in (analytics_payload.get("monthly_activity") or [])
        }
        document_analytics_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.ANALYTICS_OUTLINED, color=ft.Colors.BLUE_700, size=21),
                            ft.Text("Document Analytics", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        [
                            analytics_summary("By Status", analytics_payload.get("status_breakdown") or {}),
                            analytics_summary("By Document Type", analytics_payload.get("document_types") or {}),
                            analytics_summary("By Category", analytics_payload.get("document_categories") or {}),
                            analytics_summary("Monthly Activity", monthly_values),
                        ],
                        spacing=10,
                        wrap=True,
                    ),
                ],
                spacing=8,
            ),
            padding=12,
            bgcolor=ft.Colors.BLUE_GREY_50,
            border_radius=10,
        )

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
            buttons.append(quick_action("Analytics", "View system analytics", ft.Icons.ANALYTICS_OUTLINED, ft.Colors.BLUE_900, lambda _: render_shell(page, current_user, logout_user, nav_items, analytics_view(), initial_selected_index=next((idx for idx, (_, label, *_) in enumerate(nav_items) if label == "Analytics"), 0))))

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
                    document_analytics_section,
                    ft.Row(
                        [
                            ft.Container(content=recent_activity_section, width=520),
                            ft.Container(content=recent_security_section, width=520),
                        ],
                        spacing=12,
                        wrap=True,
                    ),
                    ft.Row(
                        [
                            ft.Container(content=storage_section, width=520),
                            ft.Container(content=system_health_section, width=520),
                        ],
                        spacing=12,
                        wrap=True,
                    ),
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

    def sessions_view():
        table_holder = ft.Container(width="100%")
        notice = ft.Text("", size=12, color=ft.Colors.RED_700)

        def load_sessions(_=None):
            try:
                response = requests.get(
                    f"{BACKEND_URL}/auth/sessions",
                    headers=get_admin_headers(),
                    verify=False,
                    timeout=15,
                )
                if response.status_code != 200:
                    raise Exception(response.text)
                sessions = response.json() or []
                rows = []
                for item in sessions:
                    rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(item.get("username") or "-", size=12)),
                        ft.DataCell(ft.Text(str(item.get("created_at") or "-").replace("T", " ").split(".", 1)[0], size=12)),
                        ft.DataCell(ft.Text(str(item.get("last_activity") or "-").replace("T", " ").split(".", 1)[0], size=12)),
                        ft.DataCell(ft.Text(str(item.get("expires_at") or "-").replace("T", " ").split(".", 1)[0], size=12)),
                        ft.DataCell(ft.OutlinedButton("Revoke", icon=ft.Icons.BLOCK, on_click=lambda _, session_id=item.get("session_id"): revoke_session(session_id))),
                    ]))
                table_holder.content = ft.DataTable(
                    columns=[ft.DataColumn(ft.Text(label, weight=ft.FontWeight.BOLD)) for label in ("User", "Created", "Last Activity", "Expires", "Action")],
                    rows=rows,
                    column_spacing=24,
                )
                notice.value = "No active sessions." if not sessions else ""
            except Exception as exc:
                notice.value = f"Unable to load sessions: {exc}"
            page.update()

        def revoke_session(session_id):
            try:
                response = requests.post(
                    f"{BACKEND_URL}/auth/sessions/{session_id}/revoke",
                    headers=get_admin_headers(),
                    verify=False,
                    timeout=15,
                )
                if response.status_code != 200:
                    raise Exception(response.text)
                load_sessions()
            except Exception as exc:
                notice.value = f"Unable to revoke session: {exc}"
                page.update()

        view = surface_card(
            ft.Column([
                section_header("Active Sessions", "Monitor and revoke active user sessions.", ft.Icons.SECURITY_OUTLINED, ft.Colors.BLUE_700),
                ft.Row([ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=load_sessions)], spacing=8),
                notice,
                table_holder,
            ], spacing=12, tight=True),
            padding=18,
        )
        load_sessions()
        return view

    def show_login():
        page.clean()
        mobile_scroll = (page.width or 1024) <= 600
        page.scroll = ft.ScrollMode.AUTO if mobile_scroll else None
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.START if mobile_scroll else ft.MainAxisAlignment.CENTER
        page.bgcolor = ft.Colors.BLUE_GREY_50
        page.padding = 24

        username_field = ft.TextField(label="Username", prefix_icon=ft.Icons.PERSON_OUTLINE, autofocus=True)
        password_field = ft.TextField(label="Password", password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK_OUTLINE)
        login_error = ft.Text("", size=12, color=ft.Colors.RED_700)

        def attempt_login(_):
            nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
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
                    if show_qr_authenticated_state():
                        return
                    if role == "SB Member":
                        from frontend.sb_member.app import main as sb_member_main
                        sb_member_main(page, session=payload)
                        return
                    if role == "Employee":
                        from frontend.employee.app import main as employee_main
                        employee_main(page, session=payload)
                        return
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
            if get_pending_qr_token():
                clear_pending_qr_token()
                page.go("/")
                return
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
                height=None if mobile_scroll else 540,
                border_radius=18,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                shadow=ft.BoxShadow(blur_radius=24, spread_radius=1, color="#102a3a26", offset=ft.Offset(0, 10)),
            )
        )
        page.update()

    office_dashboard_refresh = lambda: None

    def office_dashboard_index():
        return next((idx for idx, (_, label, *_) in enumerate(nav_items) if label == "Office Dashboard"), 0)

    def office_overview_view():
        def open_office(office):
            nonlocal selected_monitoring_office
            selected_monitoring_office = office
            render_shell(page, current_user, logout_user, nav_items, office_monitoring_view(office), initial_selected_index=office_dashboard_index())

        return build_office_overview_view(page, backend_api, surface_card, section_header, open_office)

    def office_dashboard_view():
        if (current_user_role or "").strip().lower() == "super administrator":
            if selected_monitoring_office is not None:
                return office_monitoring_view(selected_monitoring_office)
            return office_overview_view()
        return office_monitoring_view()

    def return_to_office_overview():
        nonlocal selected_monitoring_office
        selected_monitoring_office = None
        render_shell(page, current_user, logout_user, nav_items, office_overview_view(), initial_selected_index=office_dashboard_index())

    def office_monitoring_view(selected_office=None):
        nonlocal office_dashboard_refresh
        if not has_permission("view_office_documents"):
            return ft.Column([ft.Text("You do not have access to the office dashboard.")])
        if not current_user or not getattr(current_user, "strip", lambda: "")():
            return ft.Column([ft.Text("Please log in to view your office dashboard.")])

        view, refresh = build_office_queue_view(
            page,
            backend_api,
            surface_card,
            section_header,
            office_id=selected_office.get("id") if selected_office else None,
            can_receive=(
                is_employee()
                and has_permission("scan_qr")
                and has_permission("confirm_document_receipt")
                and has_permission("view_office_document_details")
            ),
            can_pass=can_pass_office_document(),
            can_view_details=has_permission("view_office_document_details"),
            can_search=has_permission("search_office_documents"),
            open_details=show_document_details,
            open_pass=open_pass_document_dialog,
            on_back=return_to_office_overview if selected_office else None,
        )
        office_dashboard_refresh = refresh
        return view

    def build_nav_items():
        # Each item is (icon, label, view, section). Items are kept in section
        # order; the shell draws a header whenever the section changes and pins
        # the "Account" section to the bottom of the sidebar.
        items = []
        is_super_admin = current_user_role == "Super Administrator"

        # Overview
        if is_employee() and has_permission("view_office_documents"):
            items.append((ft.Icons.LOCATION_CITY_OUTLINED, "Office Dashboard", lambda: office_dashboard_view(), None))
        if has_permission("view_dashboard"):
            items.append((ft.Icons.DASHBOARD_OUTLINED, "Dashboard", lambda: dashboard_view(), None))
        if has_permission("view_office_documents") and not is_employee():
            items.append((ft.Icons.LOCATION_CITY_OUTLINED, "Office Dashboard", lambda: office_dashboard_view(), None))
        if has_permission("view_analytics"):
            items.append((ft.Icons.ANALYTICS_OUTLINED, "Analytics", lambda: analytics_view(), None))

        # Documents
        if has_permission("view_documents"):
            items.append((ft.Icons.DESCRIPTION_OUTLINED, "Documents", lambda: documents_view(), "Documents"))
        if has_permission("set_documents_for_sb_members"):
            items.append((ft.Icons.EVENT_NOTE_OUTLINED, "Documents for SB Members", todays_documents_page, "Documents"))
        if has_permission("view_qr_tracking"):
            items.append((ft.Icons.QR_CODE_2, "QR Tracking", qr_tracking_view, "Documents"))
        if has_permission("view_documents"):
            items.append((ft.Icons.ARCHIVE_OUTLINED, "Archived Documents", lambda: archived_documents_view(), "Documents"))

        # Legislative
        if not is_employee() or has_permission("view_documents"):
            items.append((ft.Icons.GROUP_OUTLINED, "Committees", lambda: committees_view(), "Legislative"))

        # Administration
        if is_super_admin:
            items.append((ft.Icons.PEOPLE_ALT_OUTLINED, "Users & Roles", lambda: users_page_view(), "Administration"))
            items.append((ft.Icons.LIST_ALT_OUTLINED, "Document Definitions", lambda: reference_data_view(), "Administration"))
            items.append((ft.Icons.SECURITY_OUTLINED, "Active Sessions", sessions_view, "Administration"))
        if is_super_admin or has_permission("view_audit_logs"):
            items.append((ft.Icons.HISTORY_OUTLINED, "Audit Logs", lambda: audit_logs_view(), "Administration"))

        # Account (pinned to the bottom of the sidebar)
        items.append((ft.Icons.PERSON_OUTLINE, "My Account", lambda: account_view(), "Account"))
        items.append((ft.Icons.SETTINGS_OUTLINED, "Settings", lambda: settings_view(), "Account"))
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
            if get_pending_qr_token():
                refresh_runtime_token_if_needed(force=True)
                if runtime_token:
                    show_qr_authenticated_state()
                return True
            if current_user_role.strip().lower() == "sb member":
                from frontend.sb_member.app import main as sb_member_main
                sb_member_main(page, session={
                    "access_token": runtime_token,
                    "refresh_token": refresh_token,
                    "username": current_user,
                    "role": current_user_role,
                    "permissions": current_user_permissions,
                })
                return True
            refresh_runtime_token_if_needed(force=True)
            nav_items[:] = build_nav_items()
            initial_view = nav_items[0][2]() if nav_items else ft.Column([ft.Text("No available modules for this account.")])
            render_shell(page, current_user, logout_user, nav_items, initial_view, initial_selected_index=0)
            return True
        except Exception:
            return False

    if session:
        runtime_token = session.get("access_token")
        refresh_token = session.get("refresh_token")
        current_user = session.get("username")
        current_user_role = session.get("role") or "Employee"
        current_user_permissions = session.get("permissions") or []
        refresh_runtime_token_if_needed(force=True)
        if get_pending_qr_token():
            if runtime_token:
                show_qr_authenticated_state()
            return
        nav_items[:] = build_nav_items()
        initial_view = nav_items[0][2]() if nav_items else ft.Column([ft.Text("No available modules for this account.")])
        render_shell(page, current_user, logout_user, nav_items, initial_view, initial_selected_index=0)
    elif not restore_saved_session():
        show_login()


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
