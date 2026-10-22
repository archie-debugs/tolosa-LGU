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


def serve_compressed(host, port, assets_dir):
    """Serve the web app with gzip, so the first visit over Tailscale downloads about 2 MB instead of 8 MB.

    Returns False when this Flet can't export its web app, so the caller falls back to ft.app.
    """
    try:
        import uvicorn
        from starlette.middleware.gzip import GZipMiddleware

        web_app = ft.app(target=main, assets_dir=assets_dir, export_asgi_app=True)
    except (ImportError, TypeError):
        return False
    web_app.add_middleware(GZipMiddleware, minimum_size=1024)  # web sockets pass through untouched
    url = f"http://{host or '127.0.0.1'}:{port}"

    def started():
        # Flet's web app runs its own lifespan, so Starlette never calls "startup" handlers;
        # wait for the port to answer instead.
        import socket
        import time

        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                time.sleep(0.25)
        print(f"Frontend running at {url}")
        if os.getenv("FRONTEND_OPEN_BROWSER", "1") != "0":  # ft.app's web view opened a tab too
            import webbrowser
            webbrowser.open(url)

    import threading

    threading.Thread(target=started, daemon=True).start()
    uvicorn.run(web_app, host=host, port=port, log_level="warning")
    return True


if __name__ == "__main__":
    frontend_port = int(os.getenv("FRONTEND_PORT", "8550"))
    frontend_host = os.getenv("FRONTEND_HOST", "")
    assets_dir = PROJECT_ROOT / "frontend" / "frontend_public" / "assets"
    if not serve_compressed(frontend_host, frontend_port, str(assets_dir)):
        ft.app(target=main, view=ft.AppView.WEB_BROWSER, host=frontend_host, port=frontend_port, assets_dir=str(assets_dir))
