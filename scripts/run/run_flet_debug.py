import flet as ft
import traceback
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from frontend.admin import app as admin_app

try:
    # Use run to start the app; exceptions during startup will be printed
    ft.run(admin_app.main, view=ft.AppView.WEB_BROWSER)
except Exception:
    traceback.print_exc()
    sys.exit(1)
