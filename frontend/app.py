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


def main(page: ft.Page):
    page.title = "Sangguniang Bayan of Tolosa"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.WHITE
    page.padding = 0
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.add(build_homepage_view(page))


if __name__ == "__main__":
    frontend_port = int(os.getenv("FRONTEND_PORT", "8550"))
    assets_dir = PROJECT_ROOT / "frontend" / "frontend_public" / "assets"
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=frontend_port, assets_dir=str(assets_dir))
