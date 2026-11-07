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
from frontend.admin.council_sessions import build_sessions_view
from frontend.admin.screen import is_phone
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

    def api(method, path, base_url=API_URL, **kwargs):
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = requests.request(method, f"{base_url}{path}", headers=headers, timeout=15, **kwargs)
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
        if is_phone(page):
            # A phone keeps the title and `trailing` only, like the admin screens' phone banners.
            row = [ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900, expand=True)]
            if trailing is not None:
                row.append(trailing)
            return card(ft.Row(row, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=ft.padding.symmetric(horizontal=14, vertical=10))
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

    def can(permission):
        return permission in permissions

    def download_document(document, attachment):
        # The app runs in the member's browser: hand that browser a download link, since a
        # file saved here would land on the machine running the app, not the member's.
        try:
            # A MOA set for today has no document; its link comes from the temporary document.
            path = (f"/temporary-documents/{document['temporary_id']}/download-token" if document.get("kind") == "MOA"
                    else f"/documents/{document['id']}/attachments/{attachment['id']}/download-token")
            payload = api("POST", path)
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

    def todays_documents_view():
        if not can("view_documents"):
            return card(ft.Column([ft.Icon(ft.Icons.LOCK_OUTLINE, size=32, color=ft.Colors.BLUE_GREY_600), ft.Text("Documents are unavailable for this account.", size=14)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10))

        date_line = ft.Text(size=13, weight=ft.FontWeight.W_600, color=PRIMARY)
        list_holder = ft.Column(spacing=10)
        updated_line = ft.Text(size=11, color="#94a3b8")
        last_ids = None

        def document_row(index, document):
            moa = document.get("kind") == "MOA"
            actions = [] if moa else [ft.OutlinedButton("Open", icon=ft.Icons.VISIBILITY_OUTLINED, on_click=lambda _, d=document: document_dialog(d))]
            if can("download_documents") and document.get("attachments"):
                download = lambda _, d=document: download_document(d, d["attachments"][0])
                actions.append(
                    ft.OutlinedButton("Download", icon=ft.Icons.DOWNLOAD_OUTLINED, on_click=download) if moa else
                    ft.IconButton(ft.Icons.DOWNLOAD_OUTLINED, tooltip="Download document", icon_color=ft.Colors.BLUE_GREY_600, on_click=download)
                )
            reference = (
                f"MOA · {document['attachments'][0]['filename']}" if moa else
                f"{document.get('document_type') or 'Document'} · No. {document.get('document_number') or '-'} / {document.get('series_year') or '-'} · {document.get('tracking_number') or '-'}"
            )
            details = [
                ft.Text(document.get("title") or "Untitled", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                ft.Text(reference, size=11, color=ft.Colors.BLUE_GREY_600),
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
            snapshot = [(item["id"], item.get("temporary_id"), item.get("note")) for item in items]
            if snapshot != last_ids:
                last_ids = snapshot
                if items:
                    list_holder.controls = [document_row(index, item) for index, item in enumerate(items, start=1)]
                else:
                    list_holder.controls = [card(ft.Column([
                        ft.Icon(ft.Icons.EVENT_AVAILABLE_OUTLINED, size=30, color="#94a3b8"),
                        ft.Text("No documents have been set for today yet.", weight=ft.FontWeight.BOLD),
                        ft.Text("They appear here as soon as they are set.", size=12, color=ft.Colors.BLUE_GREY_600),
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
                "Documents set for you for today.",
                ft.Icons.EVENT_NOTE_OUTLINED,
                trailing=ft.Row([date_line, ft.IconButton(ft.Icons.REFRESH, tooltip="Refresh now", icon_color=PRIMARY, on_click=lambda _: (load(), page.update()))], spacing=4, tight=True),
            ),
            list_holder,
            updated_line,
        ], spacing=10, tight=True)

    def sessions_view():
        # Read only: SB Members see the sessions and attendance the Secretariat records.
        # Council sessions are served by the main backend only, not the SB Member backend.
        return build_sessions_view(page, card, lambda method, path, **kwargs: api(method, path, base_url=MAIN_BACKEND_URL, **kwargs), can_manage=False)

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
                (ft.Icons.EVENT_AVAILABLE_OUTLINED, "Sessions", screen("Sessions", sessions_view), "Workspace"),
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
