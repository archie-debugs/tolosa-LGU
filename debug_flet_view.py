import os
import sys
import traceback

sys.path.insert(0, os.getcwd())

import flet as ft
from frontend.frontend_admin.registration_requests import build_registration_requests_view
from frontend.frontend_admin.users_roles import build_users_roles_view

class DummyPage:
    def __init__(self):
        self.dialog = None
        self.overlay = []
        self.on_resize = None
        self.window_width = 1024
        self._dirty = False

    def update(self):
        pass


def surface_card(content, width=None, padding=24, expand=False):
    return ft.Container(content=content, width=width, padding=padding, expand=expand, bgcolor=ft.colors.WHITE, border_radius=24)


def section_header(title, subtitle, icon, accent_color):
    return ft.Row(
        [
            ft.Container(content=ft.Icon(icon, color=accent_color, size=24), padding=10, bgcolor=ft.colors.BLUE_GREY_50, border_radius=14),
            ft.Column([ft.Text(title, size=18, weight=ft.FontWeight.BOLD), ft.Text(subtitle, size=13, color=ft.colors.BLUE_GREY_600)], spacing=2, expand=True),
        ],
        spacing=14,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def traverse(ctrl, path="root"):
    problems = []
    # Detect tuple assignments to content/controls
    if hasattr(ctrl, "content"):
        val = getattr(ctrl, "content")
        if isinstance(val, tuple):
            problems.append((path + ".content", val))
        elif hasattr(val, "__dict__"):
            problems.extend(traverse(val, path + ".content"))
    if hasattr(ctrl, "controls"):
        val = getattr(ctrl, "controls")
        if isinstance(val, tuple):
            problems.append((path + ".controls", val))
        elif isinstance(val, list):
            for i, c in enumerate(val):
                if hasattr(c, "__dict__"):
                    problems.extend(traverse(c, f"{path}.controls[{i}]"))
    return problems


def print_tree(ctrl, path='root', indent=0, max_depth=6):
    pad = '  ' * indent
    try:
        tname = type(ctrl).__name__
    except Exception:
        tname = str(type(ctrl))
    # Print basic type and for certain controls also print summary values
    summary = ""
    try:
        if tname == 'Text' and hasattr(ctrl, 'value'):
            summary = f" -> '{getattr(ctrl, 'value')}'"
        if tname == 'DataTable' and hasattr(ctrl, 'rows'):
            summary = f" -> rows={len(getattr(ctrl, 'rows') or [])}"
    except Exception:
        summary = ''
    print(f"{pad}{path}: {tname}{summary}")
    if indent >= max_depth:
        return
    if hasattr(ctrl, 'content'):
        val = getattr(ctrl, 'content')
        if isinstance(val, tuple):
            print(f"{pad}  content: TUPLE(len={len(val)}) -> {val}")
        else:
            print_tree(val, path + '.content', indent + 1, max_depth)
    if hasattr(ctrl, 'controls'):
        val = getattr(ctrl, 'controls')
        if isinstance(val, tuple):
            print(f"{pad}  controls: TUPLE(len={len(val)}) -> {val}")
        elif isinstance(val, list):
            for i, c in enumerate(val):
                if hasattr(c, '__dict__'):
                    print_tree(c, f"{path}.controls[{i}]", indent + 1, max_depth)


p = DummyPage()
users_table = ft.DataTable(columns=[ft.DataColumn(ft.Text("ID"))], rows=[])
user_username_input = ft.TextField(label="Username")
user_password_input = ft.TextField(label="Password")
user_role_input = ft.Dropdown(options=[ft.dropdown.Option("Admin")], value="Admin")
users_notice = ft.Text("")

try:
    reg = build_registration_requests_view(p, surface_card, section_header)
    print("reg type", type(reg))
    problems = traverse(reg)
    print("reg problems", problems)
    ur = build_users_roles_view(
        user_username_input,
        user_password_input,
        user_role_input,
        users_notice,
        users_table,
        lambda e: None,
        surface_card,
        section_header,
        reg,
    )
    print("ur type", type(ur))
    problems = traverse(ur)
    print("ur problems", problems)
except Exception:
    traceback.print_exc()
