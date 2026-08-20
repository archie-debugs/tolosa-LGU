import flet as ft
import os
import requests
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors
if not hasattr(ft, "Icons") and hasattr(ft, "icons"):
    ft.Icons = ft.icons

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

if not hasattr(ft, 'Button'):
    BaseButton = getattr(ft, 'FilledButton', None) or getattr(ft, 'ElevatedButton', None) or getattr(ft, 'buttons', None)

    def _compat_button(*args, **kwargs):
        bgcolor = kwargs.pop('bgcolor', None)
        color = kwargs.pop('color', None)
        try:
            btn = BaseButton(*args, **kwargs)
        except Exception:
            common = {}
            if len(args) > 0:
                common['label'] = args[0]
            if 'icon' in kwargs:
                common['icon'] = kwargs['icon']
            if 'on_click' in kwargs:
                common['on_click'] = kwargs['on_click']
            btn = BaseButton(**common)
        try:
            if color is not None and hasattr(btn, 'color'):
                btn.color = color
        except Exception:
            pass
        if bgcolor is not None:
            return ft.Container(content=btn, bgcolor=bgcolor, padding=0)
        return btn

    ft.Button = _compat_button

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(override=True)

BACKEND_URL = os.getenv("EMPLOYEE_BACKEND_URL") or os.getenv("BACKEND_URL") or "http://127.0.0.1:8002"
AUTH_TOKEN = os.getenv("BACKEND_AUTH_TOKEN")

if os.getenv("DEV_HTTP", "0").lower() in ("1", "true", "yes"):
    if BACKEND_URL.startswith("https://"):
        BACKEND_URL = BACKEND_URL.replace("https://", "http://", 1)

from frontend.frontend_admin.admin_shell import render_shell
from frontend.frontend_admin.documents import build_documents_view
from frontend.frontend_admin.analytics import build_analytics_view
from frontend.frontend_admin.audit_logs import build_audit_logs_view


def main(page: ft.Page):
    page.title = "LGU Tolosa - Employee System"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.WHITE
    page.scroll = ft.ScrollMode.AUTO
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.padding = 8

    current_user = None
    current_user_role = None
    current_user_permissions = []
    runtime_token = None
    refresh_token = None

    documents_data: list[dict] = []
    audit_log_rows = []

    def save_session_state():
        try:
            if hasattr(page, "client_storage"):
                page.client_storage.set("sb_employee_access_token", runtime_token or "")
                page.client_storage.set("sb_employee_refresh_token", refresh_token or "")
                page.client_storage.set("sb_employee_current_user", current_user or "")
                page.client_storage.set("sb_employee_current_user_role", current_user_role or "")
                page.client_storage.set("sb_employee_current_user_permissions", __import__('json').dumps(current_user_permissions or []))
        except Exception:
            pass

    def clear_session_state():
        try:
            if hasattr(page, "client_storage"):
                page.client_storage.remove("sb_employee_access_token")
                page.client_storage.remove("sb_employee_refresh_token")
                page.client_storage.remove("sb_employee_current_user")
                page.client_storage.remove("sb_employee_current_user_role")
                page.client_storage.remove("sb_employee_current_user_permissions")
        except Exception:
            pass

    def normalize_permissions(permissions):
        return {str(p).strip().lower().replace(" ", "_") for p in (permissions or []) if str(p).strip()}

    def refresh_runtime_token_if_needed():
        nonlocal runtime_token, refresh_token
        if not runtime_token or not refresh_token:
            return
        try:
            token_parts = runtime_token.split('.')
            if len(token_parts) == 3:
                payload_part = token_parts[1]
                payload_part += '=' * (-len(payload_part) % 4)
                payload = __import__('json').loads(__import__('base64').urlsafe_b64decode(payload_part).decode('utf-8'))
                exp = payload.get('exp')
                if exp is not None and int(exp) - int(__import__('time').time()) > 300:
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
                save_session_state()
        except Exception:
            pass

    def get_employee_headers():
        refresh_runtime_token_if_needed()
        hdrs = {}
        if runtime_token:
            hdrs["Authorization"] = f"Bearer {runtime_token}"
        elif AUTH_TOKEN:
            hdrs["Authorization"] = f"Bearer {AUTH_TOKEN}"
        return hdrs

    def format_date(value):
        if not value:
            return "—"
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%b %d, %Y")
        except Exception:
            return str(value)

    document_details_dialog = ft.AlertDialog(
        title=ft.Text("Document Details"),
        content=ft.Column([], spacing=8),
        actions=[ft.TextButton("Close", on_click=lambda _: close_document_details())],
    )
    page.overlay.append(document_details_dialog)

    documents_notice = ft.Text("", size=12, color=ft.Colors.BLUE_GREY_600)
    document_details_container = ft.Container()

    def close_document_details():
        document_details_dialog.open = False
        page.update()

    def open_document_details(doc):
        document_details_dialog.title = ft.Text(f"{doc.get('tracking_number', 'Document')}")
        lines = [
            ft.Text(f"Title: {doc.get('title', '-')}", size=13),
            ft.Text(f"Type: {doc.get('document_type', '-')}", size=13),
            ft.Text(f"Category: {doc.get('category', '-')}", size=13),
            ft.Text(f"Status: {doc.get('status', '-')}", size=13),
            ft.Text(f"Priority: {doc.get('priority', '-')}", size=13),
            ft.Text(f"Current Office: {doc.get('current_office', '-')}", size=13),
            ft.Text(f"Assigned To: {doc.get('assigned_to', '-')}", size=13),
            ft.Text(f"Date Registered: {doc.get('date_registered', '-')}", size=13),
            ft.Text(f"Created By: {doc.get('created_by', '-')}", size=13),
            ft.Text(f"Created At: {format_date(doc.get('created_at'))}", size=13),
            ft.Text("Description:", size=13, weight=ft.FontWeight.BOLD),
            ft.Text(doc.get('description', '-') or "-", size=12),
        ]
        document_details_dialog.content = ft.Column(lines, spacing=6, scroll=ft.ScrollMode.AUTO)
        document_details_dialog.open = True
        page.update()

    documents_search_field = ft.TextField(
        label="Search documents",
        hint_text="Search title, tracking number, office, or status",
        prefix_icon=ft.Icon(ft.Icons.SEARCH, size=18, color=ft.Colors.BLUE_GREY_600),
        expand=True,
        on_change=lambda _: load_documents_table(),
    )
    documents_status_filter = ft.Dropdown(
        label="Status",
        width=180,
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

    documents_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Tracking #")),
            ft.DataColumn(ft.Text("Title")),
            ft.DataColumn(ft.Text("Type")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("Current Office")),
            ft.DataColumn(ft.Text("Assigned To")),
            ft.DataColumn(ft.Text("Priority")),
            ft.DataColumn(ft.Text("Actions")),
        ],
        rows=[],
        width=1200,
        expand=False,
        column_spacing=10,
        data_row_min_height=52,
        data_text_style=ft.TextStyle(size=12),
        heading_text_style=ft.TextStyle(size=12, weight=ft.FontWeight.BOLD),
        horizontal_lines=ft.BorderSide(width=1, color=ft.Colors.BLUE_GREY_100),
        border_radius=10,
    )

    documents_empty_state = ft.Container(
        content=ft.Text(
            "No documents match your current filters.",
            size=13,
            color=ft.Colors.BLUE_GREY_600,
            text_align=ft.TextAlign.CENTER,
        ),
        width=1200,
        height=48,
        alignment=ft.Alignment.CENTER,
        visible=False,
        padding=ft.Padding(12, 12, 12, 12),
    )

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

    def load_documents_table():
        nonlocal documents_data
        params = {}
        search_value = (documents_search_field.value or "").strip()
        if search_value:
            params["search"] = search_value
        status_value = documents_status_filter.value or "All"
        if status_value != "All":
            params["status"] = status_value

        try:
            response = requests.get(
                f"{BACKEND_URL}/documents",
                params=params,
                headers=get_employee_headers(),
                verify=False,
                timeout=15,
            )
            response.raise_for_status()
            documents_data = response.json() or []
        except Exception as exc:
            documents_notice.value = f"Unable to load documents: {exc}"
            documents_data = []
            documents_table.rows = []
            documents_empty_state.visible = True
            page.update()
            return

        document_rows = []
        for doc in documents_data:
            document_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(doc.get("tracking_number", "-"))),
                        ft.DataCell(ft.Text(doc.get("title", "-"), width=280)),
                        ft.DataCell(ft.Text(doc.get("document_type", "-"))),
                        ft.DataCell(ft.Text(doc.get("status", "-"))),
                        ft.DataCell(ft.Text(doc.get("current_office", "-"))),
                        ft.DataCell(ft.Text(doc.get("assigned_to", "-"))),
                        ft.DataCell(ft.Text(doc.get("priority", "-"))),
                        ft.DataCell(
                            ft.Row(
                                [
                                    ft.IconButton(
                                        ft.Icons.INFO_OUTLINED,
                                        tooltip="View Details",
                                        on_click=lambda e, item=doc: open_document_details(item),
                                    ),
                                ],
                                spacing=0,
                            )
                        ),
                    ]
                )
            )

        documents_table.rows = document_rows
        documents_empty_state.visible = not bool(document_rows)
        documents_notice.value = ""
        page.update()

    def reset_document_filters():
        documents_search_field.value = ""
        documents_status_filter.value = "All"
        load_documents_table()

    def documents_view():
        documents_controls = {
            "search_field": documents_search_field,
            "status_filter": documents_status_filter,
            "category_filter": None,
            "type_filter": None,
            "priority_filter": None,
            "assigned_filter": None,
            "register_button": None,
            "bulk_register_button": None,
            "refresh_button": ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=lambda _: load_documents_table()),
            "qr_monitor_button": None,
            "qr_labels_button": None,
            "export_button": None,
            "print_button": None,
            "import_button": None,
            "filter_button": ft.OutlinedButton("Apply", icon=ft.Icons.FILTER_LIST, on_click=lambda _: load_documents_table()),
            "reset_filter_button": ft.TextButton("Clear", on_click=lambda _: reset_document_filters()),
            "sort_filter": None,
            "start_date_filter": None,
            "end_date_filter": None,
            "empty_state": documents_empty_state,
        }
        return build_documents_view(
            documents_table,
            documents_notice,
            open_document_details,
            surface_card,
            section_header,
            documents_controls,
        )

    def dashboard_view():
        load_documents_table()
        total_docs = len(documents_data)
        pending_docs = sum(1 for doc in documents_data if (doc.get("status") or "").strip().lower() == "pending")
        completed_docs = sum(1 for doc in documents_data if (doc.get("status") or "").strip().lower() in {"approved", "completed"})
        active_docs = total_docs - completed_docs

        normalized_permissions = normalize_permissions(current_user_permissions)
        if current_user_role == "Super Administrator" and not normalized_permissions:
            normalized_permissions = {"*"}
        if not normalized_permissions:
            normalized_permissions = {"(none)"}

        cards = [
            {"title": "Total Documents", "value": str(total_docs), "detail": "Documents accessible to your account", "icon": ft.Icons.DESCRIPTION_OUTLINED, "accent": ft.Colors.BLUE_700},
            {"title": "Active Documents", "value": str(active_docs), "detail": "Documents in active workflow", "icon": ft.Icons.LIBRARY_ADD_CHECK_OUTLINED, "accent": ft.Colors.GREEN_700},
            {"title": "Pending Documents", "value": str(pending_docs), "detail": "Awaiting action", "icon": ft.Icons.SCHEDULE_OUTLINED, "accent": ft.Colors.ORANGE_700},
            {"title": "Completed Documents", "value": str(completed_docs), "detail": "Finished workflows", "icon": ft.Icons.CHECK_CIRCLE_OUTLINED, "accent": ft.Colors.TEAL_700},
        ]
        cards_row = ft.Row(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row([ft.Icon(item["icon"], color=item["accent"], size=22), ft.Text(item["title"], size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700)], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.Text(item["value"], size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                            ft.Text(item["detail"], size=12, color=ft.Colors.BLUE_GREY_600),
                        ], spacing=6),
                    padding=16,
                    bgcolor=ft.Colors.WHITE,
                    border_radius=18,
                    width=240,
                )
                for item in cards
            ],
            spacing=12,
            wrap=True,
        )

        buttons = [
            ft.Button("Documents", icon=ft.Icons.DESCRIPTION_OUTLINED, on_click=lambda _: open_documents_module(), bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE),
        ]
        if "view_analytics" in normalized_permissions or current_user_role == "Super Administrator":
            buttons.append(ft.Button("Analytics", icon=ft.Icons.ANALYTICS_OUTLINED, on_click=lambda _: render_shell(page, current_user, logout_user, nav_items, analytics_view(), initial_selected_index=next((idx for idx, (_, label, _) in enumerate(nav_items) if label == "Analytics"), 0)), bgcolor=ft.Colors.TEAL_700, color=ft.Colors.WHITE))

        if "view_audit_logs" in normalized_permissions or current_user_role == "Super Administrator":
            buttons.append(ft.Button("Audit Logs", icon=ft.Icons.HISTORY_OUTLINED, on_click=lambda _: render_shell(page, current_user, logout_user, nav_items, audit_logs_view(), initial_selected_index=next((idx for idx, (_, label, _) in enumerate(nav_items) if label == "Audit Logs"), 0)), bgcolor=ft.Colors.ORANGE_700, color=ft.Colors.WHITE))

        return ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            section_header(
                                "Employee Dashboard",
                                "Key operational metrics and recent activity.",
                                ft.Icons.DASHBOARD,
                                ft.Colors.BLUE_700,
                            ),
                            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                            ft.Row(
                                [
                                    ft.Column([
                                        ft.Text(f"Logged in as: {current_user}", size=14, weight=ft.FontWeight.BOLD),
                                        ft.Text(f"Role: {current_user_role}", size=12, color=ft.Colors.BLUE_GREY_700),
                                    ]),
                                    ft.Container(expand=True),
                                    ft.Container(
                                        content=ft.Text(
                                            ", ".join(sorted(normalized_permissions)),
                                            size=12,
                                            color=ft.Colors.BLUE_GREY_700,
                                        ),
                                        padding=ft.Padding(12, 12, 12, 12),
                                        bgcolor=ft.Colors.BLUE_GREY_50,
                                        border_radius=14,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                wrap=True,
                            ),
                            ft.Row(buttons, spacing=12, wrap=True),
                            ft.Container(content=cards_row, padding=ft.Padding(0, 12, 0, 0)),
                        ],
                        spacing=18,
                    ),
                    width="100%",
                    padding=24,
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    border_radius=24,
                ),
            ],
            spacing=16,
            expand=True,
        )

    def analytics_view():
        return build_analytics_view(
            current_user,
            get_employee_headers(),
            backend_url=BACKEND_URL,
            open_documents_view=open_documents_module,
            open_archived_view=None,
        )

    audit_logs_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Time")),
            ft.DataColumn(ft.Text("Actor")),
            ft.DataColumn(ft.Text("Action")),
            ft.DataColumn(ft.Text("Target")),
            ft.DataColumn(ft.Text("Details")),
        ],
        rows=[],
        width=1000,
        expand=False,
    )

    def load_audit_logs_view():
        try:
            response = requests.get(
                f"{BACKEND_URL}/audit/logs",
                headers=get_employee_headers(),
                verify=False,
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            audit_logs_table.rows = [
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(item.get("created_at", "-"))),
                        ft.DataCell(ft.Text(item.get("actor", "-"))),
                        ft.DataCell(ft.Text(item.get("action", "-"))),
                        ft.DataCell(ft.Text(item.get("target", "-"))),
                        ft.DataCell(ft.Text(item.get("details", "-"), width=360)),
                    ]
                )
                for item in payload.get("items", [])
            ]
        except Exception as exc:
            audit_logs_table.rows = []
            documents_notice.value = f"Unable to load audit logs: {exc}"
        page.update()

    def audit_logs_view():
        load_audit_logs_view()
        return build_audit_logs_view(
            audit_logs_table,
            load_audit_logs_view,
            surface_card,
            section_header,
        )

    def logout_user():
        nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
        current_user = None
        current_user_role = None
        current_user_permissions = []
        runtime_token = None
        refresh_token = None
        clear_session_state()
        show_login()

    def open_documents_module():
        target_index = next((idx for idx, (_, label, _) in enumerate(nav_items) if label == "Documents"), 0)
        render_shell(page, current_user, logout_user, nav_items, documents_view(), initial_selected_index=target_index)

    def open_audit_module():
        target_index = next((idx for idx, (_, label, _) in enumerate(nav_items) if label == "Audit Logs"), 0)
        render_shell(page, current_user, logout_user, nav_items, audit_logs_view(), initial_selected_index=target_index)

    def build_nav_items():
        normalized_permissions = normalize_permissions(current_user_permissions)
        items = []
        if "view_dashboard" in normalized_permissions or "*" in normalized_permissions or current_user_role == "Super Administrator":
            items.append((ft.Icons.DASHBOARD_OUTLINED, "Dashboard", lambda: dashboard_view()))
        if "view_analytics" in normalized_permissions or "*" in normalized_permissions or current_user_role == "Super Administrator":
            items.append((ft.Icons.ANALYTICS_OUTLINED, "Analytics", lambda: analytics_view()))
        if "view_documents" in normalized_permissions or "*" in normalized_permissions or current_user_role == "Super Administrator":
            items.append((ft.Icons.DESCRIPTION_OUTLINED, "Documents", lambda: documents_view()))
        if "view_audit_logs" in normalized_permissions or "*" in normalized_permissions or current_user_role == "Super Administrator":
            items.append((ft.Icons.HISTORY_OUTLINED, "Audit Logs", lambda: audit_logs_view()))
        return items

    def show_login():
        page.clean()
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER

        username_field = ft.TextField(label="Username", width=300, icon=ft.Icons.PERSON)
        password_field = ft.TextField(label="Password", width=300, password=True, can_reveal_password=True, icon=ft.Icons.LOCK)
        login_error = ft.Text("", size=12, color=ft.Colors.RED_700)

        def attempt_login(_):
            nonlocal current_user, current_user_role, current_user_permissions, runtime_token, nav_items
            username = (username_field.value or "").strip()
            password = password_field.value or ""
            login_error.value = ""

            if not username or not password:
                login_error.value = "Please fill out both fields."
                page.update()
                return

            try:
                res = requests.post(
                    f"{BACKEND_URL}/auth/login",
                    data={"username": username, "password": password},
                    verify=False,
                    timeout=15,
                )
                res.raise_for_status()
                payload = res.json()
                runtime_token = payload.get("access_token")
                refresh_token = payload.get("refresh_token")
                current_user = payload.get("username")
                current_user_role = (payload.get("role") or "Employee").strip()
                current_user_permissions = payload.get("permissions") or []
                save_session_state()
                nav_items = build_nav_items()
                initial_view = nav_items[0][2]() if nav_items else ft.Column([ft.Text("No available modules for this account.")])
                render_shell(page, current_user, logout_user, nav_items, initial_view, initial_selected_index=0)
            except Exception as ex:
                error_message = str(ex)
                try:
                    if hasattr(ex, "response") and ex.response is not None:
                        error_message = ex.response.text
                except Exception:
                    pass
                login_error.value = f"Login failed: {error_message}"
                page.update()

        login_btn = ft.Button("Log In", width=300, on_click=attempt_login, bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE)

        page.add(
            surface_card(
                ft.Column(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=52, color=ft.Colors.BLUE_800),
                            padding=14,
                            bgcolor=ft.Colors.BLUE_GREY_50,
                            border_radius=20,
                        ),
                        ft.Text("LGU Tolosa - Employee Access", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                        ft.Text("Employee system login", size=14, color=ft.Colors.BLUE_GREY_600),
                        ft.Container(height=12),
                        username_field,
                        password_field,
                        login_error,
                        ft.Container(height=8),
                        login_btn,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
                width=420,
                padding=36,
            )
        )
        page.update()

    nav_items = []

    def restore_saved_session():
        nonlocal current_user, current_user_role, current_user_permissions, runtime_token, refresh_token
        try:
            if not hasattr(page, "client_storage"):
                return False
            saved_access = page.client_storage.get("sb_employee_access_token")
            saved_refresh = page.client_storage.get("sb_employee_refresh_token")
            saved_user = page.client_storage.get("sb_employee_current_user")
            saved_role = page.client_storage.get("sb_employee_current_user_role")
            saved_permissions = page.client_storage.get("sb_employee_current_user_permissions")
            if not saved_access or not saved_user:
                return False
            runtime_token = saved_access
            refresh_token = saved_refresh
            current_user = saved_user
            current_user_role = saved_role or "Employee"
            try:
                current_user_permissions = __import__('json').loads(saved_permissions) if saved_permissions else []
            except Exception:
                current_user_permissions = []
            nav_items[:] = build_nav_items()
            if nav_items:
                initial_view = nav_items[0][2]()
            else:
                initial_view = ft.Column([ft.Text("No available modules for this account.")])
            render_shell(page, current_user, logout_user, nav_items, initial_view, initial_selected_index=0)
            return True
        except Exception:
            return False

    if not restore_saved_session():
        show_login()


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
