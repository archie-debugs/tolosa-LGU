import json
import os
import sys
import threading
import time
from pathlib import Path
from datetime import datetime, timezone

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

from frontend.admin.admin_shell import MENU_SECTION, render_shell
from frontend.theme import CANVAS, PRIMARY

API_URL = os.getenv("SBMEM_BACKEND_URL", "http://127.0.0.1:8002").rstrip("/")
# How often Today's Documents re-checks for documents employees set while it is open.
TODAYS_DOCUMENTS_REFRESH_SECONDS = int(os.getenv("TODAYS_DOCUMENTS_REFRESH_SECONDS", "30"))
MAIN_BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")


def main(page: ft.Page, session=None):
    page.title = "SB Tolosa | Member Workspace"
    page.padding = 0
    page.bgcolor = CANVAS
    token = None
    user = None
    permissions = set()
    current_page = "Today's Documents"
    # Bumped on every render, so a refresh loop stops once its view is no longer shown.
    render_generation = 0

    def color(name, light, night):
        # The shell's Night mode sets the page theme before it rebuilds the screen.
        return night if page.theme_mode == ft.ThemeMode.DARK else light

    def api(method, path, **kwargs):
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = requests.request(method, f"{API_URL}{path}", headers=headers, timeout=15, **kwargs)
        if response.status_code == 401 and token and render_generation:
            # The session was revoked or signed out elsewhere: back to the homepage to sign in again.
            logout()
            raise RuntimeError("Your session has ended. Please sign in again.")
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
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            # Naive API times are UTC; show the date where the reader is.
            return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone().strftime("%b %d, %Y")
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
        # The admin workspace's surface_card.
        return ft.Container(
            content=control,
            bgcolor=color("surface", ft.Colors.WHITE, ft.Colors.GREY_900),
            border=ft.border.all(1, color("border", ft.Colors.BLUE_GREY_100, ft.Colors.BLUE_GREY_700)),
            border_radius=18,
            padding=padding,
            shadow=ft.BoxShadow(blur_radius=10, offset=ft.Offset(0, 2), color=ft.Colors.with_opacity(color("shadow", 0.08, 0.24), ft.Colors.BLACK)),
        )

    def page_header(title, subtitle, icon, trailing=None):
        # The admin workspace's section_header: an icon badge beside the title.
        row = [
            ft.Container(content=ft.Icon(icon, color=PRIMARY, size=24), padding=10, bgcolor=ft.Colors.with_opacity(0.12, PRIMARY), border_radius=14),
            ft.Column([
                ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                ft.Text(subtitle, size=13, color=ft.Colors.BLUE_GREY_600),
            ], spacing=2, expand=True),
        ]
        if trailing is not None:
            row.append(trailing)
        return card(ft.Row(row, spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=ft.padding.symmetric(horizontal=20, vertical=16))

    def stat_card(label, value, icon, accent):
        return card(ft.Row([
            ft.Container(content=ft.Icon(icon, color=accent, size=22), bgcolor=ft.Colors.with_opacity(0.12, accent), border_radius=14, padding=10),
            ft.Column([ft.Text(label, size=11, color=ft.Colors.BLUE_GREY_600), ft.Text(str(value), size=23, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900)], spacing=2),
        ], spacing=12), padding=14)

    def can(permission):
        return permission in permissions

    def download_document(document, attachment):
        # The app runs in the member's browser: hand that browser a download link, since a
        # file saved here would land on the machine running the app, not the member's.
        try:
            payload = api("POST", f"/documents/{document['id']}/attachments/{attachment['id']}/download-token")
            page.launch_url(payload["download_url"])
            notify(f"Downloading {attachment['filename']} in your browser")
        except Exception as exc:
            notify(str(exc))

    def document_dialog(document):
        attachment_controls = []
        for attachment in document.get("attachments", []):
            actions = []
            if can("download_documents"):
                actions.append(ft.OutlinedButton("Download", icon=ft.Icons.DOWNLOAD_OUTLINED, on_click=lambda _, d=document, a=attachment: download_document(d, a)))
            attachment_controls.append(ft.Row([ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED, size=18, color=PRIMARY), ft.Text(attachment["filename"], expand=True), *actions], spacing=8))
        if not attachment_controls:
            attachment_controls = [ft.Text("No attached file", size=12, color=ft.Colors.BLUE_GREY_600)]
        info = [
            ("System ID", document.get("tracking_number")),
            ("Document Number", document.get("document_number")),
            ("Series Year", document.get("series_year")),
            ("Document Type", document.get("document_type")),
            ("Date", format_date(document.get("date"))),
            ("Originating Office", document.get("originating_office")),
            ("Status", document.get("status")),
        ]
        rows = [ft.Row([ft.Text(label, width=145, size=12, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_600), ft.Text(value or "Not available", size=12, expand=True)], spacing=8) for label, value in info]
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
            return card(ft.Column([ft.Icon(ft.Icons.LOCK_OUTLINE, size=32, color=ft.Colors.BLUE_GREY_600), ft.Text("Documents are unavailable for this account.", size=14)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10))

        page_size = 10
        current_page_number = 1
        all_items = []
        total_items = 0
        total_page_count = 1
        field_style = dict(height=44, content_padding=ft.padding.symmetric(horizontal=12, vertical=4), border_color=ft.Colors.BLUE_GREY_100, focused_border_color=PRIMARY, border_radius=12, bgcolor=ft.Colors.WHITE)
        search = ft.TextField(hint_text="Search documents by title or number...", prefix_icon=ft.Icons.SEARCH, width=330, disabled=not can("search_documents"), **field_style)
        type_filter = ft.Dropdown(label="Document Type", width=195, options=[ft.dropdown.Option("All Types"), ft.dropdown.Option("Ordinance"), ft.dropdown.Option("Resolution")], value="All Types", **field_style)
        year_filter = ft.Dropdown(label="Year", width=195, options=[ft.dropdown.Option("All Years")], value="All Years", **field_style)
        count_text = ft.Text(size=14, color=PRIMARY, weight=ft.FontWeight.BOLD)
        range_text = ft.Text(size=12, color=ft.Colors.BLUE_GREY_600)
        table_holder = ft.Column(controls=[ft.Container(ft.Row([ft.ProgressRing(width=20, height=20), ft.Text("Loading documents...", size=12, color=ft.Colors.BLUE_GREY_600)], alignment=ft.MainAxisAlignment.CENTER), padding=28)], spacing=0, height=430, scroll=ft.ScrollMode.AUTO)
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
            current_page_number = min(current_page_number, total_page_count)
            visible_items = all_items
            start = (current_page_number - 1) * page_size
            count_text.value = f"{total_items} document{'s' if total_items != 1 else ''}"
            range_text.value = f"Showing {start + 1 if total_items else 0}-{min(start + len(visible_items), total_items)} of {total_items} documents"

            if not visible_items:
                table_holder.controls = [ft.Container(ft.Column([
                    ft.Icon(ft.Icons.SEARCH_OFF, size=28, color="#94a3b8"),
                    ft.Text("No documents found", weight=ft.FontWeight.BOLD),
                    ft.Text("Try adjusting your search or filters.", size=12, color=ft.Colors.BLUE_GREY_600),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6), padding=30, alignment=ft.alignment.center)]
            else:
                rows = []
                for document in visible_items:
                    actions = [ft.IconButton(ft.Icons.VISIBILITY_OUTLINED, tooltip="View document", icon_color=PRIMARY, on_click=lambda _, d=document: document_dialog(d))]
                    if can("download_documents") and document.get("attachments"):
                        actions.append(ft.IconButton(ft.Icons.DOWNLOAD_OUTLINED, tooltip="Download document", icon_color=ft.Colors.BLUE_GREY_600, on_click=lambda _, d=document: download_document(d, d["attachments"][0])))
                    rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Column([
                            ft.Text(document.get("document_number") or "-", size=12, weight=ft.FontWeight.W_600),
                            ft.Text(
                                f"{document.get('tracking_number') or '-'} / Series {document.get('series_year') or '-'}",
                                size=10,
                                color=ft.Colors.BLUE_GREY_600,
                            ),
                        ], spacing=2)),
                        ft.DataCell(ft.Text(document.get("title") or "-", size=12, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)),
                        ft.DataCell(ft.Text(document.get("document_type") or "-", size=12)),
                        ft.DataCell(ft.Text(format_date(document.get("date")), size=12)),
                        ft.DataCell(badge(document.get("status"))),
                        ft.DataCell(ft.Row(actions, spacing=0, tight=True)),
                    ]))
                table_holder.controls = [ft.DataTable(
                    columns=[ft.DataColumn(ft.Text(label, size=11, weight=ft.FontWeight.BOLD)) for label in ["Document No. / ID", "Title", "Type", "Date", "Status", "Actions"]],
                    rows=rows,
                    column_spacing=32,
                        heading_row_height=46,
                        data_row_min_height=52,
                    heading_row_color=color("table_heading", "#eef4fc", "#1b2a36"),
                        horizontal_lines=ft.BorderSide(1, "#e5edf6"),
                        divider_thickness=0,
                )]

            pagination_nav.controls = []
            if total_page_count > 1:
                pagination_nav.controls.append(ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Previous", disabled=current_page_number == 1, icon_color="#94a3b8", on_click=lambda _: change_page(-1)))
                start_page = max(1, current_page_number - 2)
                end_page = min(total_page_count, current_page_number + 2)
                for number in range(start_page, end_page + 1):
                    selected = number == current_page_number
                    pagination_nav.controls.append(ft.Container(
                        content=ft.TextButton(str(number), on_click=lambda _, n=number: go_to_page(n), style=ft.ButtonStyle(color="#ffffff" if selected else ft.Colors.BLUE_GREY_600, padding=ft.padding.all(0))),
                        width=38,
                        height=38,
                        bgcolor=PRIMARY if selected else None,
                        border_radius=6,
                        alignment=ft.alignment.center,
                    ))
                pagination_nav.controls.append(ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Next", disabled=current_page_number == total_page_count, icon_color="#0875c9", on_click=lambda _: change_page(1)))

        def go_to_page(number):
            nonlocal current_page_number
            current_page_number = number
            load()

        def change_page(delta):
            go_to_page(current_page_number + delta)

        def clear_filters(_):
            search.value = ""
            type_filter.value = "All Types"
            year_filter.value = "All Years"
            load(reset_page=True)

        clear_filters_button = ft.TextButton(
            "Clear Filters",
            icon=ft.Icons.REFRESH,
            on_click=clear_filters,
            style=ft.ButtonStyle(color=PRIMARY, padding=ft.padding.symmetric(horizontal=4, vertical=1)),
        )

        def load(_=None, update_page=True, reset_page=False):
            nonlocal all_items, current_page_number, total_items, total_page_count
            if reset_page:
                current_page_number = 1
            table_holder.controls = [ft.Container(ft.Row([ft.ProgressRing(width=22, height=22), ft.Text("Loading documents...", size=12, color=ft.Colors.BLUE_GREY_600)], alignment=ft.MainAxisAlignment.CENTER), padding=30)]
            try:
                query = {}
                if search.value and can("search_documents"):
                    query["search"] = search.value.strip()
                if type_filter.value and type_filter.value != "All Types":
                    query["document_type"] = type_filter.value
                if year_filter.value and year_filter.value != "All Years":
                    query["year"] = year_filter.value
                query["page"] = current_page_number
                query["page_size"] = page_size
                payload = api("GET", "/documents", params=query)
                all_items = payload.get("items", [])
                total_items = payload.get("total", len(all_items))
                total_page_count = max(1, payload.get("total_pages", 1))
                current_page_number = min(current_page_number, total_page_count)
                years = sorted({str(item.get("date", ""))[:4] for item in all_items if str(item.get("date", ""))[:4].isdigit()}, reverse=True)
                year_filter.options = [ft.dropdown.Option("All Years")] + [ft.dropdown.Option(year) for year in years]
                render_page()
            except Exception as exc:
                print(f"SB Member documents load error: {exc!r}")
                table_holder.controls = [card(ft.Column([ft.Text("Unable to load documents.", weight=ft.FontWeight.BOLD), ft.Text("Please try again.", size=12, color=ft.Colors.BLUE_GREY_600), ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=load)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=24)]
            if update_page:
                page.update()

        search.on_submit = lambda event: load(event, reset_page=True)
        filter_row = ft.Row([
            ft.Container(search, width=330),
            type_filter,
            year_filter,
            ft.FilledButton("Search", icon=ft.Icons.SEARCH, on_click=lambda event: load(event, reset_page=True), width=120, height=44, style=ft.ButtonStyle(bgcolor=PRIMARY, color=ft.Colors.WHITE, padding=ft.padding.symmetric(horizontal=12), shape=ft.RoundedRectangleBorder(radius=12))),
            clear_filters_button,
        ], spacing=12, run_spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        filters = card(filter_row, padding=ft.padding.symmetric(horizontal=18, vertical=14))
        header = page_header("Documents", "Browse legislative documents available to you.", ft.Icons.FOLDER_OPEN_OUTLINED, trailing=count_text)
        view = ft.Column([header, filters, card(table_holder, padding=0), pagination_holder], spacing=12, tight=True)
        load(update_page=False)
        return view

    def todays_documents_view():
        if not can("view_documents"):
            return card(ft.Column([ft.Icon(ft.Icons.LOCK_OUTLINE, size=32, color=ft.Colors.BLUE_GREY_600), ft.Text("Documents are unavailable for this account.", size=14)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10))

        date_line = ft.Text(size=13, weight=ft.FontWeight.W_600, color=PRIMARY)
        list_holder = ft.Column(spacing=10)
        updated_line = ft.Text(size=11, color="#94a3b8")
        last_ids = None

        def document_row(index, document):
            actions = [ft.OutlinedButton("Open", icon=ft.Icons.VISIBILITY_OUTLINED, on_click=lambda _, d=document: document_dialog(d))]
            if can("download_documents") and document.get("attachments"):
                actions.append(ft.IconButton(ft.Icons.DOWNLOAD_OUTLINED, tooltip="Download document", icon_color=ft.Colors.BLUE_GREY_600, on_click=lambda _, d=document: download_document(d, d["attachments"][0])))
            details = [
                ft.Text(document.get("title") or "Untitled", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                ft.Text(f"{document.get('document_type') or 'Document'} · No. {document.get('document_number') or '-'} / {document.get('series_year') or '-'} · {document.get('tracking_number') or '-'}", size=11, color=ft.Colors.BLUE_GREY_600),
            ]
            if document.get("note"):
                details.append(ft.Text(document["note"], size=12, italic=True, color="#1d4ed8"))
            return card(ft.Row([
                ft.Container(ft.Text(str(index), size=14, weight=ft.FontWeight.BOLD, color="#ffffff"), bgcolor=PRIMARY, border_radius=16, width=32, height=32, alignment=ft.alignment.center),
                ft.Column(details, spacing=3, expand=True),
                ft.Row(actions, spacing=4, tight=True),
            ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=14)

        def load():
            nonlocal last_ids
            try:
                payload = api("GET", "/todays-documents")
            except Exception as exc:
                list_holder.controls = [card(ft.Text(f"Unable to load today's documents: {exc}", size=12))]
                return
            items = payload.get("items", [])
            date_line.value = format_date(payload.get("date"))
            snapshot = [(item["id"], item.get("note")) for item in items]
            if snapshot != last_ids:
                last_ids = snapshot
                if items:
                    list_holder.controls = [document_row(index, item) for index, item in enumerate(items, start=1)]
                else:
                    list_holder.controls = [card(ft.Column([
                        ft.Icon(ft.Icons.EVENT_AVAILABLE_OUTLINED, size=30, color="#94a3b8"),
                        ft.Text("No documents have been set for today yet.", weight=ft.FontWeight.BOLD),
                        ft.Text("They appear here as soon as they are set. You can still search all documents.", size=12, color=ft.Colors.BLUE_GREY_600),
                        ft.TextButton("Search documents", icon=ft.Icons.SEARCH, on_click=lambda _: navigate("Documents")),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6), padding=24)]
            updated_line.value = f"Updated {datetime.now().strftime('%I:%M %p').lstrip('0')} · refreshes automatically"

        def refresh_loop(generation):
            while True:
                time.sleep(TODAYS_DOCUMENTS_REFRESH_SECONDS)
                if generation != render_generation or current_page != "Today's Documents" or token is None:
                    return
                load()
                try:
                    page.update()
                except Exception:
                    return

        load()
        threading.Thread(target=refresh_loop, args=(render_generation,), daemon=True).start()
        return ft.Column([
            page_header(
                "Today's Documents",
                "Documents set for you for today. Past documents remain searchable under Documents.",
                ft.Icons.EVENT_NOTE_OUTLINED,
                trailing=ft.Row([date_line, ft.IconButton(ft.Icons.REFRESH, tooltip="Refresh now", icon_color=PRIMARY, on_click=lambda _: (load(), page.update()))], spacing=4, tight=True),
            ),
            list_holder,
            updated_line,
        ], spacing=10, tight=True)

    def dashboard_view():
        try:
            data = api("GET", "/dashboard")
        except Exception as exc:
            return card(ft.Text(str(exc)))
        recent = data.get("recent_documents", [])
        recent_rows = [ft.ListTile(leading=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color=PRIMARY), title=ft.Text(item.get("title") or "Untitled", size=12), subtitle=ft.Text(f"{item.get('tracking_number', '-') } · No. {item.get('document_number') or '-'} / {item.get('series_year') or '-'} · {format_date(item.get('date'))}", size=11, color=ft.Colors.BLUE_GREY_600), on_click=lambda _, d=item: document_dialog(d)) for item in recent]
        return ft.Column([
            page_header("Good day, " + (user.get("full_name") or user.get("username", "Member")), "Your legislative document workspace", ft.Icons.DASHBOARD_OUTLINED),
            ft.Row([stat_card("Available Documents", data.get("total_documents", 0), ft.Icons.FOLDER_COPY_OUTLINED, PRIMARY)], spacing=12, wrap=True),
            card(ft.Column([ft.Row([ft.Text("Recently Added", size=15, weight=ft.FontWeight.BOLD), ft.TextButton("View all", on_click=lambda _: navigate("Documents"))], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), ft.Divider(height=1), *(recent_rows or [ft.Text("No recent documents.", size=12, color=ft.Colors.BLUE_GREY_600)])], spacing=3)),
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
                ft.Text(label, width=140, size=12, color=ft.Colors.BLUE_GREY_600),
                ft.Text(value or "Not available", size=12, weight=ft.FontWeight.W_500),
            ]))
        profile_card = card(ft.Column([
            ft.Row([
                ft.CircleAvatar(content=ft.Text((user.get("full_name") or "M")[0].upper(), size=24, color="white"), bgcolor=PRIMARY, radius=30),
                ft.Column([
                    ft.Text(user.get("full_name") or user.get("username"), size=18, weight=ft.FontWeight.BOLD),
                    ft.Text("SB Member", size=12, color=PRIMARY),
                ], spacing=3),
            ], spacing=14),
            ft.Divider(),
            *profile_rows,
        ], spacing=13))
        return ft.Column([
            page_header("My Account", "Your account information", ft.Icons.ACCOUNT_CIRCLE_OUTLINED),
            profile_card,
        ], spacing=12, tight=True)

    def navigate(label):
        nonlocal current_page
        current_page = label
        render()

    def logout(_=None):
        nonlocal token, user, permissions
        token, user, permissions = None, None, set()
        # The shell redraws itself when the window is resized; the homepage must not be replaced by it.
        if hasattr(type(page), "on_resized"):
            page.on_resized = None
        else:
            page.on_resize = None
        try:
            for key in ("sb_access_token", "sb_refresh_token", "sb_current_user", "sb_current_user_role", "sb_current_user_permissions"):
                page.client_storage.remove(key)
        except Exception:
            pass
        from frontend.Frontend_Homepage.page import build_homepage_view
        page.clean()
        page.add(build_homepage_view(page))
        page.update()

    def screen(label, build):
        # The shell builds a screen each time its sidebar entry is opened.
        def show():
            nonlocal current_page, render_generation
            current_page = label
            render_generation += 1
            return build()
        return show

    def render():
        # The admin workspace's shell: same sidebar, profile menu (My account, Night mode, Log out) and drawer.
        nav_items = []
        if can("view_documents"):
            nav_items = [
                (ft.Icons.EVENT_NOTE_OUTLINED, "Today's Documents", screen("Today's Documents", todays_documents_view), "Workspace"),
                (ft.Icons.DASHBOARD_OUTLINED, "Dashboard", screen("Dashboard", dashboard_view), "Workspace"),
                (ft.Icons.FOLDER_OPEN_OUTLINED, "Documents", screen("Documents", documents_view), "Workspace"),
            ]
        nav_items.append((ft.Icons.ACCOUNT_CIRCLE_OUTLINED, "My Account", screen("My Account", account_view), MENU_SECTION))
        selected = next((index for index, item in enumerate(nav_items) if item[1] == current_page), 0)
        render_shell(
            page,
            user.get("username"),
            logout,
            nav_items,
            None,
            initial_selected_index=selected,
            account={"name": user.get("full_name") or user.get("username"), "role": "SB Member"},
            panel_title="Member Workspace",
        )

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
        page.bgcolor = CANVAS
        page.add(ft.Container(content=ft.Text("Please use Login for All on the main homepage.", color=ft.Colors.BLUE_GREY_600), alignment=ft.alignment.center, expand=True))
        page.update()


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.getenv("SBMEM_FRONTEND_PORT", "8551")))
