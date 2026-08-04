import os
import requests
import flet as ft
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.frontend_secretariat.app import build_secretariat_view

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_binary_file_to_workspace(filename: str, data: bytes) -> str:
    output_path = os.path.join(UPLOAD_DIR, filename)
    with open(output_path, "wb") as fh:
        fh.write(data)
    return output_path


def surface_card(content, width=None, padding=24, expand=False):
    return ft.Container(content=content, width=width, expand=expand, padding=padding, bgcolor=ft.colors.WHITE, border_radius=24)


def section_header(title, subtitle, icon, accent_color):
    return ft.Row([
        ft.Container(content=ft.Icon(icon, color=accent_color, size=24), padding=10, bgcolor=ft.colors.BLUE_GREY_50, border_radius=14),
        ft.Column([
            ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
            ft.Text(subtitle, size=13, color=ft.colors.BLUE_GREY_600),
        ], spacing=2, expand=True),
    ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def main(page: ft.Page):
    page.title = "Secretariat - SB Tolosa"
    page.padding = 12
    page.scroll = ft.ScrollMode.AUTO

    # Login dialog
    username = ft.TextField(label="Username")
    password = ft.TextField(label="Password", password=True, can_reveal_password=True)
    login_notice = ft.Text("")

    def do_login(e=None):
        login_notice.value = "Logging in..."
        page.update()
        try:
            resp = requests.post(f"{BACKEND_URL}/auth/scanner/login", params={"username": username.value, "password": password.value}, verify=False)
            if resp.status_code == 200:
                payload = resp.json()
                role = (payload.get("role") or "").strip()
                if role.lower() not in {"secretariat", "admin"}:
                    login_notice.value = "Access denied: account is not Secretariat."
                    page.update()
                    return

                # Load required data and render secretariat view
                try:
                    wf = []
                    wf_resp = requests.get(f"{BACKEND_URL}/workflow/config", verify=False)
                    if wf_resp.status_code == 200:
                        wf = wf_resp.json().get("statuses", [])
                except Exception:
                    wf = []

                try:
                    docs = []
                    d_resp = requests.get(f"{BACKEND_URL}/legislative/list", verify=False)
                    if d_resp.status_code == 200:
                        docs = d_resp.json().get("items", [])
                except Exception:
                    docs = []

                secretariat_selected_ids = set()
                view = build_secretariat_view(
                    page=page,
                    current_user_role=role,
                    workflow_steps=wf,
                    all_documents=docs,
                    secretariat_selected_ids=secretariat_selected_ids,
                    save_binary_file_to_workspace=save_binary_file_to_workspace,
                    BACKEND_URL=BACKEND_URL,
                    surface_card=surface_card,
                    section_header=section_header,
                )
                page.controls.clear()
                page.add(view)
                page.update()
                return

            login_notice.value = f"Login failed: {resp.text}"
        except Exception as exc:
            login_notice.value = f"Login error: {exc}"
        page.update()

    login_card = surface_card(
        ft.Column([
            ft.Text("Secretariat Login", size=18, weight=ft.FontWeight.BOLD),
            username,
            password,
            ft.Row([ft.ElevatedButton("Login", on_click=do_login), ft.TextButton("Cancel", on_click=lambda e: page.window_close())]),
            login_notice,
        ], spacing=12), width=420, padding=20, expand=False
    )

    page.add(ft.Column([login_card], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True))
    page.update()


if __name__ == "__main__":
    ft.app(target=main)
