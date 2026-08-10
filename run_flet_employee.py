import flet as ft
import traceback
import sys

from frontend.frontend_employee import app as employee_app

try:
    ft.app(target=employee_app.main, view=ft.AppView.WEB_BROWSER)
except Exception:
    traceback.print_exc()
    sys.exit(1)
