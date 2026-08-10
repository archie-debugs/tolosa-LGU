import os
import sys
from pathlib import Path
import flet as ft

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.frontend_admin.app import main as admin_main


def main(page: ft.Page):
    admin_main(page)


if __name__ == "__main__":
    frontend_port = int(os.getenv("FRONTEND_PORT", "8550"))
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=frontend_port)
