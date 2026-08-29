import flet as ft
import traceback
import sys

from frontend.frontend_admin import app as universal_app

try:
    ft.app(target=universal_app.main, view=ft.AppView.WEB_BROWSER)
except Exception:
    traceback.print_exc()
    sys.exit(1)
