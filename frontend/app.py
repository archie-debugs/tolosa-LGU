import os
import sys
from pathlib import Path
import flet as ft

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors

from frontend.Frontend_Homepage.page import build_homepage_view
from frontend.frontend_public.public_portal import build_public_portal
from frontend.theme import CANVAS


def main(page: ft.Page):
    page.title = "Sangguniang Bayan of Tolosa"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = CANVAS
    page.padding = 0
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START

    def render_route(_=None):
        page.overlay.clear()
        route_path = (page.route or "/").split("?", 1)[0]
        route_parts = route_path.split("/")
        if len(route_parts) == 3 and route_parts[1] == "qr" and route_parts[2]:
            page_state = page.data if isinstance(page.data, dict) else {}
            page_state.pop("qr_authorization", None)
            page.data = page_state
            try:
                page.client_storage.set("sb_pending_qr_token", route_parts[2])
            except Exception:
                pass
            from frontend.admin.app import main as shared_workspace_main
            shared_workspace_main(page)
            return
        else:
            try:
                page.client_storage.remove("sb_pending_qr_token")
            except Exception:
                pass
            page_state = page.data if isinstance(page.data, dict) else {}
            page_state.pop("qr_authorization", None)
            page.data = page_state
            content = build_homepage_view(page)
        page.clean()
        page.add(content)
        page.update()

    page.on_route_change = render_route
    page.go(page.route or "/")


if __name__ == "__main__":
    frontend_port = int(os.getenv("FRONTEND_PORT", "8550"))
    frontend_host = os.getenv("FRONTEND_HOST", "")
    assets_dir = PROJECT_ROOT / "frontend" / "frontend_public" / "assets"
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, host=frontend_host, port=frontend_port, assets_dir=str(assets_dir))
