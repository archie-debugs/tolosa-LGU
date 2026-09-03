import sys
from pathlib import Path
proj = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proj))
import flet as ft
from frontend.admin.registration_requests import build_registration_requests_view

class DummyPage:
    def __init__(self):
        self.overlay = []
        self.dialog = None
        self.window_width = 1024
    def update(self):
        print('page.update called')

page = DummyPage()

def surface_card(content, width=None, padding=24, expand=False):
    return ft.Container(content=content, width=width, padding=padding, expand=expand)

def section_header(title, subtitle, icon, accent_color):
    return ft.Text(title)

def get_admin_headers():
    return {'X-Admin-Username': 'admin', 'X-Admin-Role': 'Admin'}

users_table = ft.DataTable(columns=[ft.DataColumn(ft.Text('ID'))], rows=[])
user_username_input = ft.TextField(label='Username')
user_password_input = ft.TextField(label='Password')
user_role_input = ft.Dropdown(options=[ft.dropdown.Option('Admin')], value='Admin')
users_notice = ft.Text('')
create_user_record = lambda e: None

# Users & Roles frontend module removed; debug build skipped.
print('Users & Roles frontend module removed; skipping view build.')

# simulate clicking pending on view1
pending_button = view1.controls[0].controls[1]
print('pending button on_click', pending_button.on_click)
event = type('E', (), {'page': page})()
try:
    pending_button.on_click(event)
    print('click succeeded')
    print('active visible', view1.controls[1].visible)
    print('pending visible', view1.controls[2].visible)
except Exception:
    import traceback
    traceback.print_exc()

print('Test complete')
