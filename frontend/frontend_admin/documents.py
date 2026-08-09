import flet as ft


def build_documents_view(
    documents_table,
    documents_notice,
    open_document_dialog,
    surface_card,
    section_header,
    documents_controls=None,
):
    """
    Compact Documents workspace.

    This UI intentionally does NOT create a large empty/gray
    dashboard area above the document table.

    Existing controls are preserved so the current frontend
    integration can continue to use them.
    """

    documents_controls = documents_controls or {}

    # =========================================================
    # CONTROLS
    # =========================================================

    search_field = documents_controls.get("search_field")

    status_filter = documents_controls.get("status_filter")
    category_filter = documents_controls.get("category_filter")
    type_filter = documents_controls.get("type_filter")
    priority_filter = documents_controls.get("priority_filter")
    assigned_filter = documents_controls.get("assigned_filter")

    register_button = documents_controls.get("register_button")
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

    # =========================================================
    # DOCUMENTS HEADER
    # =========================================================

    header = section_header(
        "Documents",
        "Manage legislative documents, routing progress, and record history.",
        ft.Icons.DESCRIPTION_OUTLINED,
        ft.Colors.BLUE_700,
    )

    # =========================================================
    # ACTION BUTTONS
    # =========================================================

    action_controls = [
        register_button,
        refresh_button,
        qr_monitor_button,
        qr_labels_button,
        export_button,
        print_button,
        import_button,
        filter_button,
    ]

    action_controls = [
        control
        for control in action_controls
        if control is not None
    ]

    action_row = ft.Row(
        controls=action_controls,
        spacing=8,
        run_spacing=8,
        wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # =========================================================
    # SEARCH
    # =========================================================

    search_row = None

    if search_field is not None:
        search_row = ft.Row(
            controls=[
                ft.Container(
                    content=search_field,
                    expand=True,
                ),
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    else:
        search_row = None

    scan_row = None

    # =========================================================
    # FILTERS
    # =========================================================

    filter_controls = [
        status_filter,
        category_filter,
        type_filter,
        priority_filter,
        assigned_filter,
        sort_filter,
        start_date_filter,
        end_date_filter,
    ]

    filter_controls = [
        control
        for control in filter_controls
        if control is not None
    ]

    filters_row = None

    if filter_controls:
        filters_row = ft.Row(
            controls=filter_controls,
            spacing=8,
            run_spacing=8,
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # =========================================================
    # TOP DOCUMENT AREA
    # =========================================================

    top_controls = [
        header,
        ft.Divider(
            height=1,
            color=ft.Colors.BLUE_GREY_100,
        ),
        action_row,
    ]

    if search_row is not None:
        top_controls.append(search_row)

    if scan_row is not None:
        top_controls.append(scan_row)

    if filters_row is not None:
        top_controls.append(filters_row)

    documents_header_card = surface_card(
        ft.Column(
            controls=top_controls,
            spacing=12,
        ),
        padding=18,
        expand=False,
    )

    # =========================================================
    # TABLE TITLE
    # =========================================================

    table_title = ft.Row(
        controls=[
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.TABLE_ROWS_OUTLINED,
                        size=20,
                        color=ft.Colors.BLUE_700,
                    ),
                    ft.Text(
                        "Document Records",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_900,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # =========================================================
    # TABLE CONTENT
    # =========================================================

    fixed_table_width = 1600
    has_rows = bool(getattr(documents_table, "rows", None) and len(documents_table.rows) > 0)

    table_scroll = ft.Row(
        controls=[
            ft.Container(
                content=documents_table,
                width=fixed_table_width,
                alignment=ft.Alignment(-1, 0),
            )
        ],
        width=fixed_table_width,
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
        alignment=ft.MainAxisAlignment.START,
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

    side = ft.BorderSide(1, ft.Colors.BLUE_GREY_100)

    table_container = ft.Container(
        content=ft.Column(
            controls=[
                table_scroll,
                empty_state,
            ],
            spacing=0,
            width=fixed_table_width,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        width=fixed_table_width,
        height=500,
        bgcolor=ft.Colors.WHITE,
        border=ft.Border(top=side, right=side, bottom=side, left=side),
        border_radius=10,
        padding=6,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        expand=False,
        alignment=ft.Alignment(-1, 0),
    )

    # =========================================================
    # DOCUMENT TABLE CARD
    # =========================================================

    table_card = surface_card(
        ft.Column(
            controls=[
                table_title,
                table_container,
            ],
            spacing=10,
            width=fixed_table_width,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=14,
        expand=False,
    )

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
        documents_header_card,
    ]

    if notice_container is not None:
        final_controls.append(
            notice_container
        )

    final_controls.append(table_card)

    return ft.Column(
        controls=final_controls,
        spacing=10,
        expand=False,
        tight=True,
    )