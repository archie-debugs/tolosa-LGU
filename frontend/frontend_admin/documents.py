import flet as ft


def build_documents_view(
    documents_table,
    documents_notice,
    open_document_dialog,
    surface_card,
    section_header,
    documents_controls=None,
):
    """Build the document browser with the public-facing workspace layout."""

    documents_controls = documents_controls or {}
    document_count = documents_controls.get("document_count", 0)

    # =========================================================
    # CONTROLS
    # =========================================================

    search_field = documents_controls.get("search_field")

    status_filter = documents_controls.get("status_filter")
    category_filter = documents_controls.get("category_filter")
    type_filter = documents_controls.get("type_filter")
    year_filter = documents_controls.get("year_filter")
    priority_filter = documents_controls.get("priority_filter")
    assigned_filter = documents_controls.get("assigned_filter")

    register_button = documents_controls.get("register_button")
    bulk_register_button = documents_controls.get("bulk_register_button")
    refresh_button = documents_controls.get("refresh_button")
    qr_monitor_button = documents_controls.get("qr_monitor_button")
    qr_labels_button = documents_controls.get("qr_labels_button")
    export_button = documents_controls.get("export_button")
    print_button = documents_controls.get("print_button")
    import_button = documents_controls.get("import_button")

    scan_field = documents_controls.get("scan_field")

    filter_button = documents_controls.get("filter_button")
    reset_filter_button = documents_controls.get("reset_filter_button")

    sort_filter = documents_controls.get("sort_filter")

    start_date_filter = documents_controls.get("start_date_filter")
    end_date_filter = documents_controls.get("end_date_filter")

    documents_empty_state = documents_controls.get("empty_state")

    page_title = ft.Column(
        [
            ft.Text("Documents", size=30, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
            ft.Text("Browse legislative documents available to you.", size=14, color=ft.Colors.BLUE_GREY_600),
        ],
        spacing=2,
    )

    count_card = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=24, color=ft.Colors.BLUE_700),
                ft.Column([ft.Text(str(document_count), size=16, weight=ft.FontWeight.BOLD), ft.Text("documents", size=11, color=ft.Colors.BLUE_GREY_600)], spacing=0),
            ],
            spacing=10,
        ),
        padding=ft.Padding(left=16, top=10, right=22, bottom=10),
        bgcolor=ft.Colors.WHITE,
        border=ft.Border(top=ft.BorderSide(1, ft.Colors.BLUE_GREY_100), right=ft.BorderSide(1, ft.Colors.BLUE_GREY_100), bottom=ft.BorderSide(1, ft.Colors.BLUE_GREY_100), left=ft.BorderSide(1, ft.Colors.BLUE_GREY_100)),
        border_radius=10,
    )

    search_controls = [search_field, type_filter, year_filter]
    search_controls = [control for control in search_controls if control is not None]
    if search_controls:
        search_controls[0].hint_text = "Search documents by title or number..."
        search_controls[0].label = None
    if type_filter is not None:
        type_filter.label = "Document Type"
        type_filter.width = 220
    if year_filter is not None:
        year_filter.label = "Year"
        year_filter.width = 220
    if search_field is not None:
        search_field.width = 380

    filter_panel = ft.Container(
        content=ft.Column(
            [
                ft.Row(search_controls, spacing=14, wrap=True),
                ft.Row(
                    [
                        ft.Row([ft.Container(width=8, height=8, bgcolor=ft.Colors.GREEN_600, border_radius=4), ft.Text("Status: Current / Active", size=12, color=ft.Colors.GREEN_700, weight=ft.FontWeight.BOLD)], spacing=8),
                        reset_filter_button or ft.Container(),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=16,
        ),
        padding=20,
        bgcolor=ft.Colors.WHITE,
        border_radius=12,
    )

    # =========================================================
    # TABLE CONTENT
    # =========================================================

    fixed_table_width = 1120
    has_rows = bool(getattr(documents_table, "rows", None) and len(documents_table.rows) > 0)

    table_scroll = ft.Container(
        content=ft.Row(
            controls=[
                documents_table,
            ],
            width=fixed_table_width,
            scroll=ft.ScrollMode.AUTO,
            spacing=0,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        width="100%",
    )

    empty_state = documents_empty_state
    if empty_state is None:
        empty_state = ft.Container(
            content=ft.Text(
                "No documents match your search.",
                size=13,
                color=ft.Colors.BLUE_GREY_600,
                text_align=ft.TextAlign.CENTER,
            ),
            width=fixed_table_width,
            height=40,
            alignment=ft.Alignment.CENTER,
            visible=not has_rows,
            padding=ft.Padding(left=0, top=8, right=0, bottom=8),
        )

    table_card = ft.Container(content=ft.Column([table_scroll, empty_state], spacing=0), bgcolor=ft.Colors.WHITE, border_radius=12, padding=10, width="100%")

    # =========================================================
    # NOTICE
    # =========================================================

    notice_container = None

    if documents_notice is not None:
        notice_container = ft.Container(
            content=documents_notice,
            padding=ft.Padding(
                left=4,
                right=4,
                top=4,
                bottom=0,
            ),
            expand=False,
        )

    # =========================================================
    # FINAL VIEW
    # =========================================================

    final_controls = [
        ft.Row([page_title, count_card], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        filter_panel,
    ]
    if notice_container is not None:
        final_controls.append(notice_container)
    final_controls.append(table_card)

    return ft.Column(
        controls=final_controls,
        spacing=10,
        expand=False,
        tight=True,
    )