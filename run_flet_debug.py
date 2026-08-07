import flet as ft
import traceback
import sys

from frontend.frontend_admin import app as admin_app

try:
    # Use run to start the app; exceptions during startup will be printed
    ft.run(admin_app.main, view=ft.AppView.WEB_BROWSER)
except Exception:
    traceback.print_exc()
    sys.exit(1)
