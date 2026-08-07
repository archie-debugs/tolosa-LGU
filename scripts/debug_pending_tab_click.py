import sys
from pathlib import Path
proj = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proj))
import flet as ft
from frontend.frontend_admin.app import build_users_roles_view
from frontend.frontend_admin.registration_requests import build_registration_requests_view

class DummyPage:
    def __init__(self):
        self.overlay = []
        self.dialog = None
        self.window_width = 1024
        self.snack_bar = None
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
pending_registration_count_text = ft.Text('Pending Registrations (0)', size=12, weight=ft.FontWeight.BOLD)

reg_content = build_registration_requests_view(page, surface_card, section_header, refresh_callback=lambda: None, headers_provider=get_admin_headers)
view = build_users_roles_view(
    user_username_input,
    user_password_input,
    user_role_input,
    users_notice,
    users_table,
    create_user_record,
    surface_card,
    section_header,
    reg_content,
    pending_registration_count_text=pending_registration_count_text,
)
print('view built', type(view), 'controls', len(view.controls))
print('button row controls', [type(c) for c in view.controls[0].controls])

pending_button = view.controls[0].controls[1]
print('pending button on_click', pending_button.on_click)

event = type('E', (), {'page': page})()
try:
    pending_button.on_click(event)
    print('click succeeded')
    print('active visible', view.controls[1].visible)
    print('pending visible', view.controls[2].visible)
except Exception:
    import traceback
    traceback.print_exc()
