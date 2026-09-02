import flet as ft

from frontend.frontend_admin.audit_logs import build_audit_logs_view


class DummyPage:
    theme_mode = ft.ThemeMode.LIGHT
    overlay = []
    client_storage = type('CS', (), {'get': lambda *a, **k: None, 'set': lambda *a, **k: None, 'remove': lambda *a, **k: None})()

    def update(self):
        pass


def surface_card(content, width=None, padding=24, expand=False):
    return ft.Container(content=content, width=width, expand=expand, padding=padding, bgcolor=ft.Colors.WHITE, border_radius=24)


def section_header(title, subtitle, icon, accent_color):
    return ft.Row(
        [
            ft.Container(content=ft.Icon(icon, color=accent_color, size=24), padding=10, bgcolor=ft.Colors.BLUE_GREY_50, border_radius=14),
            ft.Column([ft.Text(title, size=18, weight=ft.FontWeight.BOLD), ft.Text(subtitle, size=13, color=ft.Colors.BLUE_GREY_600)], spacing=2, expand=True),
        ],
        spacing=14,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def test_audit_logs_scroll_area_does_not_expand_into_blank_gray_region():
    page = DummyPage()
    view = build_audit_logs_view(page, 'http://127.0.0.1:8001', lambda: {'Authorization': 'x'}, surface_card, section_header)

    outer_column = view.content
    scroll_container = next(
        control for control in outer_column.controls if isinstance(control, ft.Container)
        and isinstance(getattr(control, 'content', None), ft.ListView)
    )
    list_view = scroll_container.content

    assert list_view.auto_scroll is False
    assert list_view.expand is None
    assert list_view.height == 420
    assert all(getattr(control, 'expand', None) is None for control in list_view.controls)
