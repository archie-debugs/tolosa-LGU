import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.audit_logs import build_audit_logs_view


class DummyPage:
    theme_mode = ft.ThemeMode.LIGHT
    overlay = []
    client_storage = type('CS', (), {'get': lambda *a, **k: None, 'set': lambda *a, **k: None, 'remove': lambda *a, **k: None})()

    def update(self):
        pass


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

    fields = [ft.TextField(label="Search"), ft.Dropdown(label="Date Range"), ft.Dropdown(label="Status")]
    pagination = ft.Row([ft.Text("Showing 0–0 of 0 audit logs")])

    view = build_audit_logs_view(
        page, table, lambda: None,
        summary_cards=ft.ResponsiveRow([]),
        filter_fields=fields,
        apply_filters=lambda: None,
        clear_filters=lambda: None,
        export=lambda _: None,
        pagination_bar=pagination,
    )

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
    assert table_host.padding == 20
    assert table_host.expand is False


def test_audit_logs_view_places_the_live_pagination_bar_and_keeps_filter_names():
    page = DummyPage()
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text("Date & Time"))], rows=[])
    fields = [ft.TextField(label="Search"), ft.Dropdown(label="User")]
    pagination = ft.Row([])

    view = build_audit_logs_view(
        page, table, lambda: None,
        summary_cards=ft.ResponsiveRow([]),
        filter_fields=fields,
        apply_filters=lambda: None,
        clear_filters=lambda: None,
        export=lambda _: None,
        pagination_bar=pagination,
    )

    def walk(control):
        yield control
        for child in getattr(control, "controls", None) or []:
            yield from walk(child)
        content = getattr(control, "content", None)
        if isinstance(content, ft.Control):
            yield from walk(content)

    controls = list(walk(view))
    # The app refills this row on every page change, so the view must hold the row itself, not a copy.
    assert any(control is pagination for control in controls)
    assert "User" in [c.value for c in controls if isinstance(c, ft.Text)]
