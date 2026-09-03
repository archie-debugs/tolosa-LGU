import json
import os
import sys
from pathlib import Path
from datetime import datetime

import flet as ft
import requests
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors
if not hasattr(ft, "Icons") and hasattr(ft, "icons"):
    ft.Icons = ft.icons

API_URL = os.getenv("SBMEM_BACKEND_URL", "http://127.0.0.1:8002").rstrip("/")
MAIN_BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")


def main(page: ft.Page, session=None):
    page.title = "SB Tolosa | Member Workspace"
    page.padding = 0
    page.bgcolor = ft.Colors.GREY_50
    page.theme_mode = ft.ThemeMode.LIGHT
    token = None
    user = None
    permissions = set()
    dark = False
    current_page = "Dashboard"
    content = ft.Container(expand=True)

    def color(name, light, night):
        return night if dark else light

    def api(method, path, **kwargs):
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = requests.request(method, f"{API_URL}{path}", headers=headers, timeout=15, **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "Request failed")
            except ValueError:
                detail = "Request failed"
            raise RuntimeError(detail)
        return response.json() if response.content else {}

    def notify(message):
        page.snack_bar = ft.SnackBar(ft.Text(message), open=True)
        page.update()

    def format_date(value):
        if not value:
            return "Not available"
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%b %d, %Y")
        except ValueError:
            return str(value)[:10]

    def badge(value):
        return ft.Container(
            content=ft.Text(value or "Unspecified", size=11, color="#15803d", weight=ft.FontWeight.W_600),
            bgcolor="#dcfce7",
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
        )

    def card(control, padding=18):
        return ft.Container(
            content=control,
            bgcolor=color("surface", ft.Colors.WHITE, "#17232b"),
            border=ft.border.all(1, color("border", "#e2e8f0", "#2d414d")),
            border_radius=10,
            padding=padding,
        )

    def stat_card(label, value, icon, accent):
        return card(ft.Row([
            ft.Container(content=ft.Icon(icon, color=accent, size=22), bgcolor=f"{accent}18", border_radius=8, padding=10),
            ft.Column([ft.Text(label, size=11, color=color("muted", "#64748b", "#9fb1bd")), ft.Text(str(value), size=23, weight=ft.FontWeight.BOLD, color=color("heading", "#0f2742", "#f1f5f9"))], spacing=2),
        ], spacing=12), padding=14)

    def can(permission):
        return permission in permissions

    def download_document(document, attachment):
        try:
            response = requests.get(f"{API_URL}/documents/{document['id']}/attachments/{attachment['id']}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
            response.raise_for_status()
            downloads = Path.home() / "Downloads"
            downloads.mkdir(exist_ok=True)
            target = downloads / attachment["filename"]
            target.write_bytes(response.content)
            notify(f"Downloaded {attachment['filename']}")
        except Exception as exc:
            notify(str(exc))

    def document_dialog(document):
        attachment_controls = []
        for attachment in document.get("attachments", []):
            actions = []
            if can("download_documents"):
                actions.append(ft.OutlinedButton("Download", icon=ft.Icons.DOWNLOAD_OUTLINED, on_click=lambda _, d=document, a=attachment: download_document(d, a)))
            attachment_controls.append(ft.Row([ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED, size=18, color="#2563eb"), ft.Text(attachment["filename"], expand=True), *actions], spacing=8))
        if not attachment_controls:
            attachment_controls = [ft.Text("No attached file", size=12, color="#64748b")]
        info = [
            ("Document Number", document.get("document_number")),
            ("Document Type", document.get("document_type")),
            ("Date", format_date(document.get("date"))),
            ("Originating Office", document.get("originating_office")),
            ("Status", document.get("status")),
        ]
        rows = [ft.Row([ft.Text(label, width=145, size=12, weight=ft.FontWeight.W_600, color="#64748b"), ft.Text(value or "Not available", size=12, expand=True)], spacing=8) for label, value in info]
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(document.get("title", "Document"), weight=ft.FontWeight.BOLD),
            content=ft.Container(ft.Column(rows + [ft.Divider(), ft.Text("Description", weight=ft.FontWeight.BOLD, size=13), ft.Text(document.get("description") or "No description provided.", size=12), ft.Divider(), ft.Text("Attached File", weight=ft.FontWeight.BOLD, size=13), *attachment_controls], tight=True, spacing=10), width=620),
            actions=[ft.TextButton("Close", on_click=lambda _: close_dialog(dialog))],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.dialog = dialog
        dialog.open = True
        page.update()

    def close_dialog(dialog):
        dialog.open = False
        page.update()

    def documents_view():
        if not can("view_documents"):
            return card(ft.Column([ft.Icon(ft.Icons.LOCK_OUTLINE, size=32, color="#64748b"), ft.Text("Documents are unavailable for this account.", size=14)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10))

        page_size = 10
        current_page_number = 1
        all_items = []
        search = ft.TextField(hint_text="Search documents by title or number...", prefix_icon=ft.Icons.SEARCH, width=330, height=44, content_padding=ft.padding.symmetric(horizontal=12, vertical=4), disabled=not can("search_documents"), border_color="#dbe4ef", focused_border_color="#2563eb", bgcolor="#ffffff")
        type_filter = ft.Dropdown(label="Document Type", width=195, height=44, options=[ft.dropdown.Option("All Types"), ft.dropdown.Option("Ordinance"), ft.dropdown.Option("Resolution")], value="All Types", content_padding=ft.padding.symmetric(horizontal=12, vertical=4), border_color="#dbe4ef", focused_border_color="#2563eb", bgcolor="#ffffff")
        year_filter = ft.Dropdown(label="Year", width=195, height=44, options=[ft.dropdown.Option("All Years")], value="All Years", content_padding=ft.padding.symmetric(horizontal=12, vertical=4), border_color="#dbe4ef", focused_border_color="#2563eb", bgcolor="#ffffff")
        status_value = ft.Text("Current / Active", size=12, color="#0f766e", weight=ft.FontWeight.W_600)
        count_text = ft.Text(size=16, color="#0f2742", weight=ft.FontWeight.BOLD)
        range_text = ft.Text(size=12, color="#64748b")
        table_holder = ft.Column(controls=[ft.Container(ft.Row([ft.ProgressRing(width=20, height=20), ft.Text("Loading documents...", size=12, color="#64748b")], alignment=ft.MainAxisAlignment.CENTER), padding=28)], spacing=0, height=430, scroll=ft.ScrollMode.AUTO)
        pagination_nav = ft.Row(spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        pagination_holder = ft.Container(
            content=ft.Row(
                [range_text, ft.Container(expand=True), pagination_nav],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width="100%",
            height=42,
            padding=ft.padding.symmetric(horizontal=2, vertical=2),
        )

        def render_page():
            nonlocal current_page_number
            total = len(all_items)
            page_count = max(1, (total + page_size - 1) // page_size)
            current_page_number = min(current_page_number, page_count)
            start = (current_page_number - 1) * page_size
            visible_items = all_items[start:start + page_size]
            count_text.value = f"{total} document{'s' if total != 1 else ''}"
            range_text.value = f"Showing {start + 1 if total else 0}-{min(start + page_size, total)} of {total} documents"

            if not visible_items:
                table_holder.controls = [ft.Container(ft.Column([
                    ft.Icon(ft.Icons.SEARCH_OFF, size=28, color="#94a3b8"),
                    ft.Text("No documents found", weight=ft.FontWeight.BOLD),
                    ft.Text("Try adjusting your search or filters.", size=12, color="#64748b"),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6), padding=30, alignment=ft.alignment.center)]
            else:
                rows = []
                for document in visible_items:
                    actions = [ft.IconButton(ft.Icons.VISIBILITY_OUTLINED, tooltip="View document", icon_color="#2563eb", on_click=lambda _, d=document: document_dialog(d))]
                    if can("download_documents") and document.get("attachments"):
                        actions.append(ft.IconButton(ft.Icons.DOWNLOAD_OUTLINED, tooltip="Download document", icon_color="#64748b", on_click=lambda _, d=document: download_document(d, d["attachments"][0])))
                    rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(document.get("document_number") or "-", size=12, weight=ft.FontWeight.W_600)),
                        ft.DataCell(ft.Text(document.get("title") or "-", size=12, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)),
                        ft.DataCell(ft.Text(document.get("document_type") or "-", size=12)),
                        ft.DataCell(ft.Text(format_date(document.get("date")), size=12)),
                        ft.DataCell(badge(document.get("status"))),
                        ft.DataCell(ft.Row(actions, spacing=0, tight=True)),
                    ]))
                table_holder.controls = [ft.DataTable(
                    columns=[ft.DataColumn(ft.Text(label, size=11, weight=ft.FontWeight.BOLD)) for label in ["Document No.", "Title", "Type", "Date", "Status", "Actions"]],
                    rows=rows,
                    column_spacing=32,
                        heading_row_height=46,
                        data_row_min_height=52,
                    heading_row_color="#f4f7fb",
                        horizontal_lines=ft.BorderSide(1, "#e5edf6"),
                        divider_thickness=0,
                )]

            pagination_nav.controls = []
            if page_count > 1:
                pagination_nav.controls.append(ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Previous", disabled=current_page_number == 1, icon_color="#94a3b8", on_click=lambda _: change_page(-1)))
                for number in range(1, page_count + 1):
                    selected = number == current_page_number
                    pagination_nav.controls.append(ft.Container(
                        content=ft.TextButton(str(number), on_click=lambda _, n=number: go_to_page(n), style=ft.ButtonStyle(color="#ffffff" if selected else "#64748b", padding=ft.padding.all(0))),
                        width=38,
                        height=38,
                        bgcolor="#155eef" if selected else None,
                        border_radius=6,
                        alignment=ft.alignment.center,
                    ))
                pagination_nav.controls.append(ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Next", disabled=current_page_number == page_count, icon_color="#0875c9", on_click=lambda _: change_page(1)))

        def go_to_page(number):
            nonlocal current_page_number
            current_page_number = number
            render_page()
            page.update()

        def change_page(delta):
            go_to_page(current_page_number + delta)

        def clear_filters(_):
            search.value = ""
            type_filter.value = "All Types"
            year_filter.value = "All Years"
            load()

        clear_filters_button = ft.TextButton(
            "Clear Filters",
            icon=ft.Icons.REFRESH,
            on_click=clear_filters,
            style=ft.ButtonStyle(color="#2563eb", padding=ft.padding.symmetric(horizontal=4, vertical=1)),
        )

        def load(_=None, update_page=True):
            nonlocal all_items, current_page_number
            table_holder.controls = [ft.Container(ft.Row([ft.ProgressRing(width=22, height=22), ft.Text("Loading documents...", size=12, color="#64748b")], alignment=ft.MainAxisAlignment.CENTER), padding=30)]
            try:
                query = {}
                if search.value and can("search_documents"):
                    query["search"] = search.value.strip()
                if type_filter.value and type_filter.value != "All Types":
                    query["document_type"] = type_filter.value
                if year_filter.value and year_filter.value != "All Years":
                    query["year"] = year_filter.value
                payload = api("GET", "/documents", params=query)
                all_items = payload.get("items", [])
                current_page_number = 1
                years = sorted({str(item.get("date", ""))[:4] for item in all_items if str(item.get("date", ""))[:4].isdigit()}, reverse=True)
                year_filter.options = [ft.dropdown.Option("All Years")] + [ft.dropdown.Option(year) for year in years]
                render_page()
            except Exception as exc:
                print(f"SB Member documents load error: {exc!r}")
                table_holder.controls = [card(ft.Column([ft.Text("Unable to load documents.", weight=ft.FontWeight.BOLD), ft.Text("Please try again.", size=12, color="#64748b"), ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=load)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=24)]
            if update_page:
                page.update()

        search.on_submit = load
        filter_row = ft.Row([
            ft.Container(search, width=330),
            type_filter,
            year_filter,
            ft.FilledButton("Search", icon=ft.Icons.SEARCH, on_click=load, width=120, height=40, style=ft.ButtonStyle(bgcolor="#155eef", color=ft.Colors.WHITE, padding=ft.padding.symmetric(horizontal=12), shape=ft.RoundedRectangleBorder(radius=7))),
            clear_filters_button,
        ], spacing=12, run_spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        filters = ft.Container(content=ft.Column([
            filter_row,
        ], spacing=8), bgcolor="#ffffff", border=ft.border.all(1, "#e2e8f0"), border_radius=10, padding=ft.padding.symmetric(horizontal=18, vertical=14))
        count_card = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color="#2563eb", size=19),
                ft.Column([count_text], spacing=0),
            ], spacing=10),
            bgcolor="#ffffff",
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=13, vertical=7),
        )
        header = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Documents", size=25, weight=ft.FontWeight.BOLD, color="#0f2742"),
                    ft.Text("Browse legislative documents available to you.", size=12, color="#64748b"),
                ], spacing=3),
                count_card,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#ffffff",
            border=ft.border.all(1, "#e2e8f0"),
            border_radius=10,
            padding=ft.padding.symmetric(horizontal=16, vertical=11),
        )
        view = ft.Column([header, filters, card(table_holder, padding=0), pagination_holder], spacing=12, tight=True)
        load(update_page=False)
        return view

    def dashboard_view():
        try:
            data = api("GET", "/dashboard")
        except Exception as exc:
            return card(ft.Text(str(exc)))
        recent = data.get("recent_documents", [])
        recent_rows = [ft.ListTile(leading=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color="#2563eb"), title=ft.Text(item.get("title") or "Untitled", size=12), subtitle=ft.Text(f"{item.get('document_number', '-') } · {format_date(item.get('date'))}", size=11, color="#64748b"), on_click=lambda _, d=item: document_dialog(d)) for item in recent]
        return ft.Column([
            ft.Row([ft.Column([ft.Text("Good day, " + (user.get("full_name") or user.get("username", "Member")), size=25, weight=ft.FontWeight.BOLD, color=color("heading", "#0f2742", "#f1f5f9")), ft.Text("Your legislative document workspace", size=12, color="#64748b")], spacing=3)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([stat_card("Available Documents", data.get("total_documents", 0), ft.Icons.FOLDER_COPY_OUTLINED, "#2563eb")], spacing=12, wrap=True),
            card(ft.Column([ft.Row([ft.Text("Recently Added", size=15, weight=ft.FontWeight.BOLD), ft.TextButton("View all", on_click=lambda _: navigate("Documents"))], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), ft.Divider(height=1), *(recent_rows or [ft.Text("No recent documents.", size=12, color="#64748b")])], spacing=3)),
            ft.Row([ft.FilledButton("View Documents", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=lambda _: navigate("Documents")), ft.OutlinedButton("Search Documents", icon=ft.Icons.SEARCH, on_click=lambda _: navigate("Documents"))], spacing=10),
        ], spacing=16, tight=True)

    def account_view():
        profile_rows = []
        for label, value in [
            ("Full Name", user.get("full_name")),
            ("Username", user.get("username")),
            ("Email", user.get("email")),
            ("Role", "SB Member"),
            ("Account Status", user.get("status")),
            ("Account Created", format_date(user.get("created_at"))),
        ]:
            profile_rows.append(ft.Row([
                ft.Text(label, width=140, size=12, color="#64748b"),
                ft.Text(value or "Not available", size=12, weight=ft.FontWeight.W_500),
            ]))
        profile_card = card(ft.Column([
            ft.Row([
                ft.CircleAvatar(content=ft.Text((user.get("full_name") or "M")[0].upper(), size=24, color="white"), bgcolor="#2563eb", radius=30),
                ft.Column([
                    ft.Text(user.get("full_name") or user.get("username"), size=18, weight=ft.FontWeight.BOLD),
                    ft.Text("SB Member", size=12, color="#2563eb"),
                ], spacing=3),
            ], spacing=14),
            ft.Divider(),
            *profile_rows,
        ], spacing=13))
        return ft.Column([
            ft.Text("My Account", size=25, weight=ft.FontWeight.BOLD, color=color("heading", "#0f2742", "#f1f5f9")),
            ft.Text("Your account information", size=12, color="#64748b"),
            profile_card,
        ], spacing=12, tight=True)

    def settings_view():
        night = ft.Switch(label="Night mode", value=dark, on_change=toggle_theme)
        return ft.Column([ft.Text("Settings", size=25, weight=ft.FontWeight.BOLD, color=color("heading", "#0f2742", "#f1f5f9")), ft.Text("Personalize your workspace.", size=12, color="#64748b"), card(ft.Column([ft.Text("Appearance", size=16, weight=ft.FontWeight.BOLD), ft.Text("Choose how the workspace looks on this device.", size=12, color="#64748b"), night], spacing=12))], spacing=12, tight=True)

    def toggle_theme(event):
        nonlocal dark
        dark = bool(event.control.value)
        page.theme_mode = ft.ThemeMode.DARK if dark else ft.ThemeMode.LIGHT
        render()

    def navigate(label):
        nonlocal current_page
        current_page = label
        render()

    def logout(_=None):
        nonlocal token, user, permissions
        token, user, permissions = None, None, set()
        try:
            for key in ("sb_access_token", "sb_refresh_token", "sb_current_user", "sb_current_user_role", "sb_current_user_permissions"):
                page.client_storage.remove(key)
        except Exception:
            pass
        from frontend.Frontend_Homepage.page import build_homepage_view
        page.clean()
        page.add(build_homepage_view(page))
        page.update()

    def render():
        page.bgcolor = color("bg", "#f8fafc", "#0d171d")
        workspace_items = []
        if can("view_documents"):
            workspace_items = [
                (ft.Icons.DASHBOARD_OUTLINED, "Dashboard"),
                (ft.Icons.FOLDER_OPEN_OUTLINED, "Documents"),
            ]
        sections = [("Workspace", workspace_items), ("Personal", [(ft.Icons.ACCOUNT_CIRCLE_OUTLINED, "My Account"), (ft.Icons.SETTINGS_OUTLINED, "Settings")])]
        nav = []
        for group, items in sections:
            nav.append(ft.Text(group.upper(), size=10, weight=ft.FontWeight.BOLD, color="#93c5fd"))
            for icon, label in items:
                is_selected = current_page == label
                nav.append(ft.Container(content=ft.Row([ft.Icon(icon, size=18, color="#ffffff" if is_selected else "#93c5fd"), ft.Text(label, size=12, color="#ffffff" if is_selected else "#dbeafe")], spacing=12), bgcolor="#0754c7" if is_selected and not dark else ("#193d55" if is_selected else None), border_radius=7, padding=ft.padding.symmetric(horizontal=12, vertical=10), on_click=lambda _, item=label: navigate(item)))
        nav.append(ft.Container(expand=True))
        nav.append(ft.Container(content=ft.Row([ft.Icon(ft.Icons.LOGOUT, size=18, color="#dc2626"), ft.Text("Log Out", size=12, color="#dc2626")], spacing=12), padding=ft.padding.symmetric(horizontal=12, vertical=10), on_click=logout))
        if current_page == "Dashboard": body = dashboard_view()
        elif current_page == "Documents": body = documents_view()
        elif current_page == "My Account": body = account_view()
        else: body = settings_view()
        shell = ft.Row([ft.Container(width=225, bgcolor="#06264b" if not dark else "#071827", padding=16, content=ft.Column([ft.Row([ft.Icon(ft.Icons.ACCOUNT_BALANCE, color="#60a5fa"), ft.Column([ft.Text("SB TOLOSA", size=14, weight=ft.FontWeight.BOLD, color="#ffffff"), ft.Text("Member Workspace", size=10, color="#bfdbfe")], spacing=0)], spacing=9), ft.Divider(height=20, color="#315279"), *nav], spacing=7)), ft.Container(expand=True, padding=ft.padding.symmetric(horizontal=28, vertical=8), content=ft.Column([ft.Row([ft.Row([ft.CircleAvatar(content=ft.Text((user.get("full_name") or "M")[0].upper(), size=12, color="white"), bgcolor="#2563eb", radius=16), ft.Text(user.get("full_name") or "SB Member", size=12, color=color("nav", "#334155", "#d6e2e8"))], spacing=8)], alignment=ft.MainAxisAlignment.END), body], spacing=8, scroll=ft.ScrollMode.AUTO, expand=True))], expand=True, spacing=0)
        page.controls.clear()
        page.add(shell)
        page.update()

    if session and session.get("access_token"):
        token = session["access_token"]
        user = {
            "username": session.get("username"),
            "full_name": session.get("full_name") or session.get("username"),
            "email": session.get("email"),
            "role": "SB Member",
            "status": "Active",
        }
        permissions = set(session.get("permissions") or [])
        try:
            profile = api("GET", "/me")
        except RuntimeError as exc:
            if "token" not in str(exc).lower() or not session.get("refresh_token"):
                raise
            refresh_response = requests.post(
                f"{MAIN_BACKEND_URL}/auth/refresh",
                data={"refresh_token": session["refresh_token"]},
                timeout=10,
            )
            refresh_response.raise_for_status()
            refreshed = refresh_response.json()
            token = refreshed["access_token"]
            session["refresh_token"] = refreshed.get("refresh_token", session["refresh_token"])
            permissions = set(refreshed.get("permissions") or permissions)
            profile = api("GET", "/me")
        user.update(profile)
        permissions = set(profile.get("permissions") or permissions)
        render()
    else:
        page.bgcolor = "#f8fafc"
        page.add(ft.Container(content=ft.Text("Please use Login for All on the main homepage.", color="#64748b"), alignment=ft.alignment.center, expand=True))
        page.update()


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.getenv("SBMEM_FRONTEND_PORT", "8551")))
