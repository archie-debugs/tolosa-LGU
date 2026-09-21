import flet as ft


def build_reference_data_view(
    categories,
    document_types,
    search_field,
    kind_filter,
    open_create_dialog,
    open_edit_dialog,
    toggle_definition,
    refresh,
    page,
    section_header,
):
    rows = []
    query = (search_field.value or "").strip().lower()
    selected_kind = kind_filter.value or "All"
    definitions = []
    if selected_kind in ("All", "Categories"):
        definitions.extend(("Category", item) for item in categories)
    if selected_kind in ("All", "Document Types"):
        definitions.extend(("Document Type", item) for item in document_types)
    for kind, item in definitions:
        if query and query not in str(item.get("name", "")).lower():
            continue
        active = bool(item.get("is_active", True))
        rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(kind, size=12)),
                    ft.DataCell(ft.Text(str(item.get("name") or "-"), size=12)),
                    ft.DataCell(ft.Text("Active" if active else "Inactive", size=12, color=ft.Colors.GREEN_700 if active else ft.Colors.RED_700)),
                    ft.DataCell(
                        ft.Row(
                            [
                                ft.IconButton(icon=ft.Icons.EDIT, tooltip="Edit", on_click=lambda _, k=kind, i=item: open_edit_dialog(k, i)),
                                ft.IconButton(icon=ft.Icons.PAUSE_CIRCLE_OUTLINE if active else ft.Icons.PLAY_CIRCLE_OUTLINE, tooltip="Deactivate" if active else "Activate", on_click=lambda _, k=kind, i=item: toggle_definition(k, i)),
                            ],
                            spacing=2,
                        )
                    ),
                ]
            )
        )

    table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("Definition")), ft.DataColumn(ft.Text("Name")), ft.DataColumn(ft.Text("Status")), ft.DataColumn(ft.Text("Actions"))],
        rows=rows,
        column_spacing=24,
    )
    return ft.Column(
        [
            ft.Container(
                content=ft.Column(
                    [
                        section_header("Document Definitions", "Manage active categories and document types used by the system.", ft.Icons.LIST_ALT_OUTLINED, ft.Colors.BLUE_700),
                        ft.Row([search_field, kind_filter, ft.Button("Add Definition", icon=ft.Icons.ADD, on_click=lambda _: open_create_dialog(kind_filter.value or "Categories")), ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=lambda _: refresh())], spacing=8, wrap=True),
                        ft.Container(content=table, padding=12, bgcolor=ft.Colors.BLUE_GREY_50, border_radius=12),
                    ],
                    spacing=12,
                ),
                padding=18,
                bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                border_radius=12,
            )
        ],
        spacing=12,
        tight=True,
    )
