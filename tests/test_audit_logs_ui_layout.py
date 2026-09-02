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


def test_audit_logs_view_uses_compact_non_expanding_layout():
    page = DummyPage()
    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Date & Time")),
            ft.DataColumn(ft.Text("User")),
            ft.DataColumn(ft.Text("Status")),
        ],
        rows=[],
        column_spacing=12,
    )

    view = build_audit_logs_view(table, lambda: None, surface_card, section_header)

    assert getattr(view, "expand", False) is False
    assert getattr(view, "tight", False) is True
    assert len(view.controls) >= 3
    assert not any(getattr(control, "expand", None) is True for control in view.controls)
    def find_datatable(control):
        if isinstance(control, ft.DataTable):
            return control
        if hasattr(control, "controls"):
            for child in control.controls:
                found = find_datatable(child)
                if found is not None:
                    return found
        if hasattr(control, "content") and control.content is not None:
            return find_datatable(control.content)
        return None

    table_host = next(
        control for control in view.controls
        if isinstance(control, ft.Container)
        and find_datatable(control) is not None
    )
    assert table_host.padding == 12
    assert table_host.expand is False
