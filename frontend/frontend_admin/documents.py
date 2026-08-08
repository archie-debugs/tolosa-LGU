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
    year_filter = documents_controls.get("year_filter")
    assigned_filter = documents_controls.get("assigned_filter")

    register_button = documents_controls.get("register_button")
    refresh_button = documents_controls.get("refresh_button")
    export_button = documents_controls.get("export_button")
    print_button = documents_controls.get("print_button")
    import_button = documents_controls.get("import_button")

    filter_button = documents_controls.get("filter_button")
    reset_filter_button = documents_controls.get("reset_filter_button")

    sort_filter = documents_controls.get("sort_filter")

    start_date_filter = documents_controls.get("start_date_filter")
    end_date_filter = documents_controls.get("end_date_filter")

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
                    content=ft.Icon(
                        ft.Icons.SEARCH,
                        size=20,
                        color=ft.Colors.BLUE_GREY_500,
                    ),
                    padding=ft.Padding.only(
                        left=12,
                        right=4,
                    ),
                ),
                ft.Container(
                    content=search_field,
                    expand=True,
                ),
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # =========================================================
    # FILTERS
    # =========================================================

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

    table_has_rows = bool(
        getattr(
            documents_table,
            "rows",
            None,
        )
        and len(
            documents_table.rows
        ) > 0
    )

    if table_has_rows:

        # -----------------------------------------------------
        # COMPACT TABLE CONTAINER
        # -----------------------------------------------------

        table_scroll = ft.Row(
            controls=[documents_table],
            width=1600,
            scroll=ft.ScrollMode.AUTO,
            spacing=0,
        )

        table_container = ft.Container(
            content=table_scroll,
            height=500,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(
                1,
                ft.Colors.BLUE_GREY_100,
            ),
            border_radius=10,
            padding=6,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=False,
        )

    else:

        # -----------------------------------------------------
        # EMPTY STATE
        # -----------------------------------------------------

        empty_button = documents_controls.get(
            "empty_state_button",
            register_button,
        )

        if empty_button is None:
            empty_button = ft.Button(
                "Register Document",
                icon=ft.Icons.ADD,
                on_click=lambda e: open_document_dialog(None),
            )

        empty_state = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.DESCRIPTION_OUTLINED,
                        size=42,
                        color=ft.Colors.BLUE_GREY_400,
                    ),
                    ft.Text(
                        "No documents found",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_GREY_800,
                    ),
                    ft.Text(
                        "Register a document to begin tracking.",
                        size=13,
                        color=ft.Colors.BLUE_GREY_600,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    empty_button,
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            height=220,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(
                1,
                ft.Colors.BLUE_GREY_100,
            ),
            border_radius=10,
            alignment=ft.Alignment.CENTER,
        )

        table_container = empty_state

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
            padding=ft.Padding.only(
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
        table_card,
    ]

    if notice_container is not None:
        final_controls.append(
            notice_container
        )

    return ft.Column(
        controls=final_controls,
        spacing=10,
        expand=False,
        tight=True,
    )