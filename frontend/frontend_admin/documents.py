import flet as ft


def build_documents_view(
    documents_table,
    documents_notice,
    open_document_dialog,
    surface_card,
    section_header,
    documents_controls=None,
):
    documents_controls = documents_controls or {}
    summary_cards = documents_controls.get("summary_cards", [])
    search_field = documents_controls.get("search_field")
    status_filter = documents_controls.get("status_filter")
    category_filter = documents_controls.get("category_filter")
    type_filter = documents_controls.get("type_filter")
    year_filter = documents_controls.get("year_filter")
    assigned_filter = documents_controls.get("assigned_filter")
    register_button = documents_controls.get("register_button")
    refresh_button = documents_controls.get("refresh_button")
    export_button = documents_controls.get("export_button")
    print_button = documents_controls.get("print_button")
    filter_button = documents_controls.get("filter_button")
    reset_filter_button = documents_controls.get("reset_filter_button")
    sort_filter = documents_controls.get("sort_filter")
    start_date_filter = documents_controls.get("start_date_filter")
    end_date_filter = documents_controls.get("end_date_filter")
    empty_state_button = documents_controls.get("empty_state_button", register_button)

    toolbar_controls = [
        register_button,
        refresh_button,
        export_button,
        print_button,
        documents_controls.get("import_button"),
        filter_button,
    ]
    toolbar_controls = [control for control in toolbar_controls if control is not None]

    # Header area: title, subtitle and toolbar/filters (kept compact)
    header_content = [
        section_header(
            "Documents",
            "Manage legislative documents, routing progress, and record history.",
            ft.Icons.DESCRIPTION_OUTLINED,
            ft.Colors.BLUE_700,
        ),
        ft.Divider(height=1),
    ]

    if summary_cards:
        header_content.append(
            ft.Row(summary_cards, wrap=True, spacing=10, run_spacing=10)
        )

    toolbar_row = []
    if toolbar_controls:
        toolbar_row.extend(toolbar_controls)
    if search_field is not None:
        toolbar_row.append(search_field)
    if toolbar_row:
        header_content.append(
            ft.Row(toolbar_row, wrap=True, spacing=8, run_spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        )

    filter_controls = [
        status_filter,
        category_filter,
        type_filter,
        year_filter,
        assigned_filter,
        sort_filter,
        start_date_filter,
        end_date_filter,
        reset_filter_button,
    ]
    filter_controls = [control for control in filter_controls if control is not None]
    if filter_controls:
        header_content.append(
            ft.Row(filter_controls, wrap=True, spacing=8, run_spacing=8)
        )

    # Table container: will be placed inside the remaining page area and made scrollable via the inner column
    table_container = ft.Container(
        content=ft.Column(
            [documents_table],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
        bgcolor=ft.Colors.WHITE,
        border_radius=12,
        padding=8,
        expand=True,
    )

    table_section = []
    if getattr(documents_table, "rows", None) and len(documents_table.rows) > 0:
        table_section.append(table_container)
    else:
        table_section.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=44, color=ft.Colors.BLUE_GREY_400),
                        ft.Text("No documents found", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_800),
                        ft.Text("Register a new document to get started and keep your tracking workspace active.", size=13, color=ft.Colors.BLUE_GREY_600),
                        empty_state_button if empty_state_button is not None else ft.Button("Register Document", icon=ft.Icons.ADD, on_click=lambda _: open_document_dialog(None)),
                    ],
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=28,
                border_radius=20,
                bgcolor=ft.Colors.BLUE_GREY_50,
            )
        )

    # Build final layout: header (compact) + table area that consumes remaining vertical space and scrolls internally
    header_only = ft.Column(header_content, spacing=12)

    # If there are no documents, show empty state inside the table area
    if getattr(documents_table, "rows", None) and len(documents_table.rows) > 0:
        table_area_content = table_container
    else:
        table_area_content = table_section[0]

    return ft.Column(
        [
            # Compact header card
            surface_card(header_only, padding=12, expand=False),
            ft.Container(
                content=ft.Column(
                    [table_area_content],
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=12,
                expand=True,
            ),
            # Notice / status line
            ft.Container(content=ft.Text(documents_notice.value, size=12, color=ft.Colors.BLUE_GREY_600), padding=ft.Padding.only(top=6, bottom=6)),
        ],
        expand=True,
    )
