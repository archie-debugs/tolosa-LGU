"""Document Definitions screen: the categories and document types registration offers."""

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets


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
):
    widgets = TrackingWidgets(page)
    query = (search_field.value or "").strip().lower()
    selected_kind = kind_filter.value or "All"
    definitions = []
    if selected_kind in ("All", "Categories"):
        definitions.extend(("Category", item) for item in categories)
    if selected_kind in ("All", "Document Types"):
        definitions.extend(("Document Type", item) for item in document_types)
    definitions = [(kind, item) for kind, item in definitions if not query or query in str(item.get("name", "")).lower()]

    def definition_row(kind, item):
        active = bool(item.get("is_active", True))
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.LOCAL_OFFER_OUTLINED if kind == "Category" else ft.Icons.DESCRIPTION_OUTLINED, color=widgets.accent(), size=22),
                        width=44, height=44, border_radius=12,
                        alignment=ft.Alignment(0, 0),
                        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.BLUE_700),
                    ),
                    ft.Column(
                        [
                            ft.Text(str(item.get("name") or "-"), size=15, weight=ft.FontWeight.W_600, color=widgets.link_color()),
                            ft.Text(kind, size=12, color=widgets.muted_color()),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    widgets.chip("Active" if active else "Inactive", ft.Colors.GREEN_700 if active else ft.Colors.RED_700),
                    ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_color=widgets.accent(), tooltip="Edit", on_click=lambda _, k=kind, i=item: open_edit_dialog(k, i)),
                    ft.IconButton(
                        ft.Icons.PAUSE_CIRCLE_OUTLINE if active else ft.Icons.PLAY_CIRCLE_OUTLINE,
                        icon_color=ft.Colors.AMBER_800 if active else ft.Colors.GREEN_700,
                        tooltip="Deactivate" if active else "Activate",
                        on_click=lambda _, k=kind, i=item: toggle_definition(k, i),
                    ),
                ],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(10, 6, 8, 6),
            bgcolor=widgets.tone("#F7FAFE", "#1B2430"),
            border=ft.border.all(1, widgets.line_color()),
            border_radius=12,
        )

    widgets.style_field(search_field, hint="Search definitions")
    widgets.style_field(kind_filter)
    search_field.prefix_icon = ft.Icons.SEARCH
    search_field.expand = True
    search_field.width = None
    kind_filter.width = 220
    count = len(definitions)
    rows = [definition_row(kind, item) for kind, item in definitions] or [
        widgets.empty_box("No definitions match your search." if query else "No definitions yet. Add a category or document type to use it when registering.")
    ]
    add_button = ft.FilledButton(
        "Add Definition", icon=ft.Icons.ADD, on_click=lambda _: open_create_dialog(kind_filter.value or "Categories"), height=44,
        style=ft.ButtonStyle(shape=ft.StadiumBorder(), bgcolor=ft.Colors.WHITE, color=ft.Colors.BLUE_800, padding=ft.Padding(18, 0, 18, 0)),
    )
    return ft.Column(
        [
            widgets.banner(
                "Document Definitions", "Manage active categories and document types used by the system.", ft.Icons.LIST_ALT,
                actions=[add_button],
                corner=ft.IconButton(ft.Icons.REFRESH, icon_color=ft.Colors.WHITE, tooltip="Refresh", on_click=lambda _: refresh()),
            ),
            ft.Container(
                content=ft.Column(
                    [
                        widgets.card_title(
                            "Definitions", ft.Icons.LIST_ALT_OUTLINED,
                            subtitle="Categories and document types offered when registering a document.",
                            trailing=ft.Text(f"{count} definition{'s' if count != 1 else ''}", size=13, color=widgets.body_color()),
                        ),
                        ft.Row(
                            [widgets.labelled(search_field), widgets.labelled(kind_filter)],
                            spacing=16,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                        ft.Column(rows, spacing=12),
                    ],
                    spacing=18,
                ),
                padding=20,
                bgcolor=widgets.card_color(),
                border=ft.border.all(1, widgets.line_color()),
                border_radius=18,
            ),
        ],
        spacing=16,
        tight=True,
    )

