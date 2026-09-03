import flet as ft
import traceback
import sys

from frontend.employee import app as employee_app

try:
    ft.app(target=employee_app.main, view=ft.AppView.WEB_BROWSER, port=int(__import__("os").getenv("EMPLOYEE_FRONTEND_PORT", "8552")))
except Exception:
    traceback.print_exc()
    sys.exit(1)
