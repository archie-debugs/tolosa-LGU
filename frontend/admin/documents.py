"""Documents and Archived Documents screens: find a document, see where it is, and act on it."""

import inspect

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets, document_reference, format_elapsed, parse_time, stage_color

PAGE_SIZES = (10, 25, 50)
SORTS = {
    "Newest number": ("tracking_number", "desc"),
    "Oldest number": ("tracking_number", "asc"),
    "Recently updated": ("updated_at", "desc"),
    "Title A–Z": ("title", "asc"),
}
ARCHIVED_SORTS = {
    "Recently archived": ("archived_at", "desc"),
    "Oldest archived": ("archived_at", "asc"),
    "Newest number": ("tracking_number", "desc"),
    "Title A–Z": ("title", "asc"),
}
PRIORITY_COLORS = {"High": ft.Colors.RED_700, "Low": ft.Colors.BLUE_GREY_600}
ALL = "All"
# Newer Flet versions renamed the dropdown's change event to on_select.
DROPDOWN_EVENT = "on_select" if "on_select" in inspect.signature(ft.Dropdown.__init__).parameters else "on_change"


def format_date(value):
    parsed = parse_time(value)
    return parsed.astimezone().strftime("%b %d, %Y") if parsed else "-"


def build_documents_view(
    page,
    api,
    surface_card,
    *,
    normalize,
    selection,
    loaded,
    can_search=False,
    can_filter=False,
    can_register=False,
    can_import=False,
    can_archive=False,
    can_print_qr=False,
    can_view_details=False,
    can_download=False,
    can_print=False,
    can_edit=False,
    open_details=None,
    open_register=None,
    open_bulk_register=None,
    open_edit=None,
    open_replace_attachment=None,
    preview=None,
    print_document=None,
    download=None,
    set_visibility=None,
    archive=None,
    archive_selected=None,
    qr_labels=None,
    archived=False,
    can_restore=False,
    can_delete=False,
    restore=None,
    restore_selected=None,
    delete_permanently=None,
    delete_selected=None,
):
    """The active document list, or with `archived=True` the archived one.

    `api(method, path, **kwargs)` calls the main backend and returns parsed JSON or raises.
    `normalize(item)` turns a list item into the document shape the app's dialogs expect.
    `selection` is the app's set of selected document IDs, and `loaded` its list of the
    documents on screen; both are kept up to date here so the QR label and bulk archive
    dialogs see the same rows.
    Returns `(view, refresh)`; `refresh()` reloads the current page.
    """
    widgets = TrackingWidgets(page)
    sorts = ARCHIVED_SORTS if archived else SORTS
    default_sort = next(iter(sorts))
    state = {"page": 1, "page_size": PAGE_SIZES[0], "total": 0, "total_pages": 1, "quick": None, "summary": {}}

    accent = widgets.accent()
    tint = widgets.tint()
    field_style = {
        "dense": True,
        "text_size": 14,
        "border_radius": 10,
        "border_color": widgets.line_color(),
        "focused_border_color": accent,
        "filled": True,
        "bgcolor": widgets.card_color(),
        "content_padding": ft.Padding(14, 12, 10, 12),
    }

    def dropdown(label, options, value=ALL):
        # The name is drawn above the dropdown (see filter_box), so `data` keeps it.
        return ft.Dropdown(
            data=label,
            value=value,
            options=[ft.dropdown.Option(key=key, text=text) for key, text in options],
            **field_style,
            **{DROPDOWN_EVENT: lambda _: load(page_number=1)},
        )

    def filter_box(control):
        return ft.Column(
            [ft.Text(control.data, size=13, weight=ft.FontWeight.W_600, color=widgets.heading_color()), control],
            spacing=6,
            width=190,
        )

    search_field = ft.TextField(
        hint_text="Search by tracking number, title, number, author, office…",
        prefix_icon=ft.Icons.SEARCH,
        expand=True,
        height=50,
        on_change=lambda _: load(page_number=1),
        on_submit=lambda _: load(page_number=1),
        visible=can_search,
        **{**field_style, "content_padding": ft.Padding(14, 14, 14, 14)},
    )
    type_filter = dropdown("Type", [(ALL, ALL)])
    category_filter = dropdown("Category", [(ALL, ALL)])
    priority_filter = dropdown("Priority", [(ALL, ALL), ("High", "High"), ("Medium", "Medium"), ("Low", "Low")])
    status_filter = dropdown("Status", [(ALL, ALL)])
    from_year = dropdown("From year", [(ALL, "Any")])
    to_year = dropdown("To year", [(ALL, "Any")])
    archived_by_filter = dropdown("Archived by", [(ALL, "Anyone")])
    sort_filter = dropdown("Sort", [(name, name) for name in sorts], value=default_sort)
    if archived:
        filters = [type_filter, category_filter, archived_by_filter, status_filter, from_year, to_year]
    else:
        filters = [type_filter, category_filter, priority_filter, status_filter, from_year, to_year]
    filter_boxes = {control: filter_box(control) for control in [*filters, sort_filter]}

    kpi_row = ft.ResponsiveRow(spacing=12, run_spacing=12)
    notice_text = ft.Text("", size=12, visible=False)
    result_text = widgets.hint("")
    selection_bar = ft.Container(visible=False)
    rows_column = ft.Column(spacing=0)
    pagination = ft.Row(spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True)

    def show_notice(message, error=False):
        notice_text.value = message
        notice_text.color = ft.Colors.RED_700 if error else ft.Colors.GREEN_700
        notice_text.visible = bool(message)

    def load_reference_options():
        for control, path in ((type_filter, "/reference-data/document-types"), (category_filter, "/reference-data/categories")):
            try:
                names = [item.get("name") for item in api("GET", path, params={"active_only": "true"}) if item.get("name")]
            except Exception:
                continue
            control.options = [ft.dropdown.Option(key=ALL, text=ALL)] + [ft.dropdown.Option(key=name, text=name) for name in names]
            if control.value not in names:
                control.value = ALL

    def set_options(control, values, any_text):
        current = control.value
        keys = [str(value) for value in values]
        control.options = [ft.dropdown.Option(key=ALL, text=any_text)] + [ft.dropdown.Option(key=key, text=key) for key in keys]
        control.value = current if current in keys else ALL

    def params():
        result = {"page": state["page"], "page_size": state["page_size"]}
        result["sort_by"], result["sort_order"] = sorts.get(sort_filter.value, sorts[default_sort])
        if archived:
            result["archived"] = "true"
        if can_search and (search_field.value or "").strip():
            result["search"] = search_field.value.strip()
        if can_filter:
            for key, control in (("document_type", type_filter), ("category", category_filter), ("priority", priority_filter), ("status", status_filter), ("start_date", from_year), ("end_date", to_year), ("archived_by", archived_by_filter)):
                if control.value and control.value != ALL:
                    result[key] = control.value
        quick = state["quick"]
        if quick == "in_transit":
            result["location"] = "in_transit"
        elif quick == "public":
            result["visibility"] = "public"
        elif quick == "without_attachment":
            result["has_attachment"] = "false"
        elif quick == "archived_last_30_days":
            result["archived_within_days"] = 30
        return result

    def load(page_number=None, keep_notice=False):
        if page_number is not None:
            state["page"] = max(1, page_number)
        if not keep_notice:
            show_notice("")
        if can_filter and from_year.value != ALL and to_year.value != ALL and int(from_year.value) > int(to_year.value):
            show_notice("“From year” cannot be later than “To year”.", error=True)
            page.update()
            return
        try:
            payload = api("GET", "/documents", params=params())
        except Exception as exc:
            loaded[:] = []
            rows_column.controls = [widgets.empty_box(f"Unable to load documents: {exc}")]
            result_text.value = ""
            pagination.controls = []
            page.update()
            return
        state["total"] = payload.get("total", 0)
        state["total_pages"] = max(1, payload.get("total_pages", 1))
        state["summary"] = payload.get("summary") or {}
        years = payload.get("available_years") or []
        set_options(from_year, years, "Any")
        set_options(to_year, list(reversed(years)), "Any")
        statuses = payload.get("available_statuses") or []
        set_options(status_filter, statuses, ALL)
        filter_boxes[status_filter].visible = len(statuses) > 1 or status_filter.value != ALL
        set_options(archived_by_filter, payload.get("available_archivers") or [], "Anyone")
        items = payload.get("items") or []
        loaded[:] = [{**normalize(item), "in_transit_to": item.get("in_transit_to"), "in_transit_since": item.get("in_transit_since")} for item in items]
        selection.intersection_update(doc.get("id") for doc in loaded)
        render()
        page.update()

    def refresh():
        load(keep_notice=True)

    def set_quick(key):
        state["quick"] = None if state["quick"] == key or key == "total" else key
        load(page_number=1)

    def clear_filters(_=None):
        search_field.value = ""
        for control in filters:
            control.value = ALL
        sort_filter.value = default_sort
        state["quick"] = None
        load(page_number=1)

    def render_kpis():
        summary = state["summary"]
        cards = [
            ("total", "Archived documents", summary.get("total", 0), "Out of circulation", ft.Icons.ARCHIVE_OUTLINED, ft.Colors.BLUE_GREY_600),
            ("archived_last_30_days", "Archived in 30 days", summary.get("archived_last_30_days", 0), "Recently archived", ft.Icons.HISTORY, ft.Colors.BLUE_700),
            ("without_attachment", "No file attached", summary.get("without_attachment", 0), "Missing the scanned copy", ft.Icons.FILE_PRESENT_OUTLINED, ft.Colors.RED_700),
        ] if archived else [
            ("total", "Active documents", summary.get("total", 0), "Registered and not archived", ft.Icons.DESCRIPTION, ft.Colors.BLUE_700),
            ("in_transit", "In transit", summary.get("in_transit", 0), "Sent, not yet received", ft.Icons.LOCAL_SHIPPING, ft.Colors.AMBER_800),
            ("public", "Public", summary.get("public", 0), "Visible to SB Members", ft.Icons.VISIBILITY, ft.Colors.GREEN_700),
            ("without_attachment", "No file attached", summary.get("without_attachment", 0), "Missing the scanned copy", ft.Icons.FILE_PRESENT, ft.Colors.RED_700),
        ]
        controls = []
        for key, title, value, detail, icon, color in cards:
            filtering_by_it = state["quick"] == key and key != "total"
            card = widgets.stat_card(
                title, value, "Showing these" if filtering_by_it else detail, icon, color,
                col={"xs": 12, "sm": 6, "md": 12 // len(cards)}, tile=True, active=filtering_by_it,
            )
            card.on_click = lambda _, k=key: set_quick(k)
            card.ink = True
            card.tooltip = "Show all" if key == "total" else f"Show only: {title.lower()}"
            controls.append(card)
        kpi_row.controls = controls

    def location_cell(doc):
        if archived:
            archived_at = doc.get("date_archived") if doc.get("date_archived") not in (None, "-") else doc.get("archived_at")
            by = doc.get("archived_by")
            return ft.Column(
                [
                    ft.Text(format_date(archived_at), size=12, color=widgets.body_color()),
                    widgets.hint(f"by {by}" if by and by != "-" else "Archiver not recorded"),
                ],
                spacing=3,
                width=190,
            )
        if doc.get("in_transit_to"):
            return ft.Column(
                [
                    ft.Text(f"→ {doc['in_transit_to']}", size=12, color=widgets.body_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    widgets.chip(f"In transit · {format_elapsed(doc.get('in_transit_since'))}", ft.Colors.AMBER_800),
                ],
                spacing=3,
                width=190,
            )
        office = doc.get("current_office")
        return ft.Column(
            [
                ft.Text(office if office and office != "-" else "No office recorded", size=12, color=widgets.body_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                widgets.hint("Held here"),
            ],
            spacing=3,
            width=190,
        )

    def badges(doc):
        # A measure's stage comes first: it says where the measure is in the Sanggunian.
        chips = [widgets.chip(doc["stage"], stage_color(doc["stage"]))] if doc.get("stage") else []
        if doc.get("is_public") and not archived:
            chips.append(widgets.chip("Public", ft.Colors.GREEN_700))
        priority = doc.get("priority")
        if priority in PRIORITY_COLORS and priority != "Low":
            chips.append(widgets.chip(f"{priority} priority", PRIORITY_COLORS[priority]))
        if not has_file(doc):
            chips.append(widgets.chip("No file", ft.Colors.RED_700))
        status = doc.get("status")
        if status and status != "Approved":
            chips.append(widgets.chip(status, ft.Colors.INDIGO_600))
        return chips

    def has_file(doc):
        return any(isinstance(item, dict) and item.get("id") for item in doc.get("attachments") or [])

    def has_pdf(doc):
        return any(
            isinstance(item, dict) and ((item.get("mime_type") or "").lower() == "application/pdf" or str(item.get("original_filename") or "").lower().endswith(".pdf"))
            for item in doc.get("attachments") or []
        )

    def menu_items(doc):
        items = []

        def add(text, icon, handler):
            if handler:
                items.append(ft.PopupMenuItem(content=ft.Row([ft.Icon(icon, size=18), ft.Text(text)], spacing=10), on_click=lambda _, d=doc: handler(d)))

        if archived:
            if can_restore:
                add("Restore to Documents", ft.Icons.UNARCHIVE_OUTLINED, restore)
            if can_delete and delete_permanently:
                if items:
                    items.append(ft.PopupMenuItem())
                add("Delete permanently", ft.Icons.DELETE_FOREVER_OUTLINED, delete_permanently)
            return items

        if can_download and has_pdf(doc):
            add("Preview PDF", ft.Icons.PICTURE_AS_PDF_OUTLINED, preview)
        if can_print and has_pdf(doc):
            add("Print", ft.Icons.PRINT_OUTLINED, print_document)
        if can_download and has_file(doc):
            add("Download file", ft.Icons.DOWNLOAD_OUTLINED, download)
        if can_edit:
            add("Edit details", ft.Icons.EDIT_OUTLINED, open_edit)
            if has_file(doc):
                add("Replace file", ft.Icons.UPLOAD_FILE, open_replace_attachment)
            if set_visibility:
                public = bool(doc.get("is_public"))
                items.append(ft.PopupMenuItem(
                    content=ft.Row([ft.Icon(ft.Icons.PUBLIC_OFF if public else ft.Icons.PUBLIC, size=18), ft.Text("Make private" if public else "Make public")], spacing=10),
                    on_click=lambda _, d=doc, value=not public: set_visibility(d, value),
                ))
        if can_archive and archive:
            if items:
                items.append(ft.PopupMenuItem())
            add("Archive", ft.Icons.ARCHIVE_OUTLINED, archive)
        return items

    def toggle(doc_id, checked):
        if checked:
            selection.add(doc_id)
        else:
            selection.discard(doc_id)
        render()
        page.update()

    def toggle_page(checked):
        ids = [doc.get("id") for doc in loaded if doc.get("id") is not None]
        if checked:
            selection.update(ids)
        else:
            selection.difference_update(ids)
        render()
        page.update()

    def clear_selection(_=None):
        selection.clear()
        render()
        page.update()

    selectable = (can_restore or can_delete) if archived else (can_archive or can_print_qr)

    def render_selection_bar():
        count = len(selection)
        selection_bar.visible = selectable and count > 0
        if not selection_bar.visible:
            return
        actions = [ft.Text(f"{count} selected", size=13, weight=ft.FontWeight.W_600, color=widgets.heading_color())]
        if archived:
            if can_restore and restore_selected:
                actions.append(ft.OutlinedButton("Restore selected", icon=ft.Icons.UNARCHIVE_OUTLINED, on_click=lambda _: restore_selected()))
            if can_delete and delete_selected:
                actions.append(ft.OutlinedButton("Delete permanently", icon=ft.Icons.DELETE_FOREVER_OUTLINED, style=ft.ButtonStyle(color=ft.Colors.RED_700), on_click=lambda _: delete_selected()))
        elif can_print_qr and qr_labels:
            actions.append(ft.OutlinedButton("Download QR labels", icon=ft.Icons.QR_CODE_2, on_click=lambda _: qr_labels()))
        if can_archive and archive_selected and not archived:
            actions.append(ft.OutlinedButton("Archive selected", icon=ft.Icons.ARCHIVE_OUTLINED, on_click=lambda _: archive_selected()))
        actions.append(ft.TextButton("Clear selection", on_click=clear_selection))
        selection_bar.content = ft.Row(actions, spacing=10, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        selection_bar.padding = ft.Padding(12, 8, 12, 8)
        selection_bar.border_radius = 10
        selection_bar.bgcolor = ft.Colors.with_opacity(0.10, ft.Colors.BLUE_700)

    def header_row():
        ids = {doc.get("id") for doc in loaded if doc.get("id") is not None}
        cells = []
        if selectable:
            cells.append(ft.Checkbox(value=bool(ids) and ids.issubset(selection), tooltip="Select this page", on_change=lambda e: toggle_page(e.control.value)))
        for text, width in (("Document", None), ("Archived" if archived else "Where it is", 190), ("Registered", 110), ("", 96)):
            label = widgets.hint(text.upper())
            cells.append(ft.Container(label, expand=True) if width is None else ft.Container(label, width=width))
        return ft.Container(ft.Row(cells, spacing=12), padding=ft.Padding(4, 4, 4, 6), border=ft.Border(bottom=ft.BorderSide(1, widgets.line_color())))

    def document_row(doc):
        doc_id = doc.get("id")
        reference = document_reference(doc)
        details = [
            ft.Row(
                [
                    ft.Text(doc.get("tracking_number") or "-", size=12, weight=ft.FontWeight.BOLD, color=widgets.link_color()),
                    *([widgets.hint(reference)] if reference else []),
                ],
                spacing=8,
                wrap=True,
            ),
            ft.Text(doc.get("title") or "Untitled", size=13, color=widgets.heading_color(), max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, tooltip=doc.get("title")),
        ]
        chips = badges(doc)
        if chips:
            details.append(ft.Row(chips, spacing=6, wrap=True))
        controls = []
        if selectable:
            controls.append(ft.Checkbox(value=doc_id in selection, on_change=lambda e, i=doc_id: toggle(i, e.control.value)))
        controls += [
            ft.Column(details, spacing=4, expand=True),
            location_cell(doc),
            ft.Column([ft.Text(format_date(doc.get("date_registered") if doc.get("date_registered") not in (None, "-") else doc.get("date_received")), size=12, color=widgets.body_color()), widgets.hint(f"Updated {format_date(doc.get('last_updated'))}")], spacing=3, width=110),
        ]
        actions = []
        if can_view_details and open_details:
            actions.append(ft.IconButton(ft.Icons.VISIBILITY_OUTLINED, tooltip="View details", on_click=lambda _, d=doc: open_details(d)))
        more = menu_items(doc)
        if more:
            actions.append(ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, tooltip="More actions", items=more))
        controls.append(ft.Row(actions, spacing=0, width=96, alignment=ft.MainAxisAlignment.END))
        return widgets.list_row(controls, on_click=(lambda _, d=doc: open_details(d)) if can_view_details and open_details else None)

    def render_pagination():
        current, total_pages = state["page"], state["total_pages"]
        controls = [
            ft.Dropdown(
                value=str(state["page_size"]),
                options=[ft.dropdown.Option(key=str(size), text=f"{size} per page") for size in PAGE_SIZES],
                width=150,
                **{**field_style, "bgcolor": tint, "border_color": ft.Colors.TRANSPARENT},
                **{DROPDOWN_EVENT: lambda e: change_page_size(e.control.value)},
            ),
            ft.Container(width=8),
            ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_color=accent, tooltip="Previous page", disabled=current <= 1, on_click=lambda _: load(page_number=current - 1)),
        ]
        for number in range(max(1, current - 2), min(total_pages, current + 2) + 1):
            if number == current:
                controls.append(ft.Container(
                    content=ft.Text(str(number), size=14, weight=ft.FontWeight.BOLD, color=widgets.link_color()),
                    width=42, height=42, border_radius=21,
                    alignment=ft.Alignment(0, 0),
                    bgcolor=tint,
                ))
            else:
                controls.append(ft.TextButton(str(number), on_click=lambda _, n=number: load(page_number=n)))
        controls += [
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_color=accent, tooltip="Next page", disabled=current >= total_pages, on_click=lambda _: load(page_number=current + 1)),
            ft.Text(f"Page {current} of {total_pages}", size=13, color=widgets.muted_color()),
        ]
        pagination.controls = controls

    def change_page_size(value):
        state["page_size"] = int(value or PAGE_SIZES[0])
        load(page_number=1)

    def filtering():
        return bool((search_field.value or "").strip()) or state["quick"] is not None or any(control.value not in (None, ALL) for control in filters)

    def render():
        render_kpis()
        render_selection_bar()
        total = state["total"]
        if loaded:
            first = (state["page"] - 1) * state["page_size"] + 1
            result_text.value = f"Showing {first}–{first + len(loaded) - 1} of {total} document{'s' if total != 1 else ''}"
            rows_column.controls = [header_row()] + [document_row(doc) for doc in loaded]
        else:
            result_text.value = ""
            if filtering():
                message = "No documents match your search or filters."
            else:
                message = "Nothing is archived. Documents you archive appear here and can be restored." if archived else "No documents yet. Registered documents appear here."
            rows_column.controls = [widgets.empty_box(message)]
        render_pagination()

    pill = ft.StadiumBorder()
    header_actions = []
    if can_register and open_register and not archived:
        header_actions.append(ft.FilledButton(
            "Register document", icon=ft.Icons.ADD, on_click=lambda _: open_register(), height=44,
            style=ft.ButtonStyle(shape=pill, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, padding=ft.Padding(18, 0, 18, 0)),
        ))
    if can_import and open_bulk_register and not archived:
        header_actions.append(ft.OutlinedButton(
            "Multiple registration", icon=ft.Icons.UPLOAD_FILE, on_click=lambda _: open_bulk_register(), height=44,
            style=ft.ButtonStyle(shape=pill, bgcolor=ft.Colors.WHITE, color=ft.Colors.BLUE_800, side=ft.BorderSide(1, ft.Colors.WHITE), padding=ft.Padding(18, 0, 18, 0)),
        ))

    filter_controls = [filter_boxes[control] for control in ([*filters, sort_filter] if can_filter else [sort_filter])]
    banner = (
        widgets.banner("Archived Documents", "Documents taken out of circulation. Restore one to put it back on Documents.", ft.Icons.ARCHIVE_OUTLINED)
        if archived else
        widgets.banner("Documents", "Every active legislative document, where it is, and what you can do with it.", ft.Icons.INVENTORY_2, actions=header_actions)
    )
    kpi_card = surface_card(kpi_row, padding=18, expand=False)
    list_card = surface_card(
        ft.Column(
            [
                ft.Row(
                    [
                        search_field,
                        ft.TextButton("Clear filters", icon=ft.Icons.FILTER_ALT_OUTLINED, on_click=clear_filters, style=ft.ButtonStyle(color=accent)),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(filter_controls, spacing=16, run_spacing=12, wrap=True),
                selection_bar,
                ft.Row([result_text, notice_text], spacing=12, wrap=True),
                rows_column,
                pagination,
            ],
            spacing=16,
        ),
        padding=22,
        expand=False,
    )

    if can_filter:
        load_reference_options()
    load(page_number=1)
    view = ft.Column([banner, kpi_card, list_card], spacing=16, expand=False, tight=True)
    return view, refresh
