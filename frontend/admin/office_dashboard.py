"""Office Dashboard: an office's work queue, and the Super Administrator's overview of every office."""

from datetime import datetime
from urllib.parse import quote

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets, document_reference, format_elapsed, format_time


def build_office_queue_view(
    page,
    api,
    surface_card,
    section_header,
    *,
    office_id=None,
    can_receive=False,
    can_pass=False,
    can_view_details=False,
    can_search=False,
    open_details=None,
    open_pass=None,
    on_back=None,
):
    """What an office has to do: receive what was sent to it, pass on what it holds, chase what it sent.

    `api(method, path, **kwargs)` calls the main backend and returns parsed JSON or raises.
    `office_id` is set when a Super Administrator monitors another office; that view is read-only.
    Returns `(view, refresh)` so dialogs that change the queue can reload it.
    """
    widgets = TrackingWidgets(page)
    state = {"page": 1, "confirming": None, "own_office": office_id is None}

    header_holder = ft.Container()
    updated_text = widgets.hint("")
    notice_text = ft.Text("", size=12, visible=False)
    kpi_row = ft.ResponsiveRow(spacing=12, run_spacing=12)
    incoming_title, holding_title, outgoing_title = widgets.title("To receive"), widgets.title("Holding"), widgets.title("Sent, awaiting receipt")
    incoming_list, holding_list, outgoing_list, activity_list = (ft.Column(spacing=0) for _ in range(4))
    page_label = widgets.hint("")
    previous_button = ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Previous page", on_click=lambda _: change_page(-1))
    next_button = ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Next page", on_click=lambda _: change_page(1))
    search_field = ft.TextField(
        hint_text="Search held documents by title or tracking number",
        prefix_icon=ft.Icons.SEARCH,
        expand=True,
        height=44,
        content_padding=ft.Padding(12, 4, 12, 4),
        on_submit=lambda _: load(page_number=1),
        visible=can_search,
    )

    def show_notice(message, error=False):
        notice_text.value = message
        notice_text.color = ft.Colors.RED_700 if error else ft.Colors.GREEN_700
        notice_text.visible = bool(message)

    def summary_of(document):
        return {"id": document.get("document_id"), "tracking_number": document.get("tracking_number"), "title": document.get("title")}

    def view_button(document):
        if not (can_view_details and open_details and document.get("document_id")):
            return None
        return ft.IconButton(ft.Icons.VISIBILITY_OUTLINED, tooltip="View details", on_click=lambda _, d=summary_of(document): open_details(d))

    def receive_controls(item):
        if not (can_receive and state["own_office"]):
            return []
        if state["confirming"] == item.get("handoff_id"):
            return [
                ft.FilledButton("Confirm receipt", icon=ft.Icons.CHECK, on_click=lambda _, i=item: receive(i)),
                ft.TextButton("Cancel", on_click=lambda _: set_confirming(None)),
            ]
        return [ft.OutlinedButton("Receive", icon=ft.Icons.MOVE_TO_INBOX_OUTLINED, on_click=lambda _, i=item: set_confirming(i.get("handoff_id")))]

    def set_confirming(handoff_id):
        state["confirming"] = handoff_id
        render_incoming(state.get("incoming") or [])
        page.update()

    def receive(item):
        tracking_number = item.get("tracking_number") or ""
        state["confirming"] = None
        try:
            api("POST", f"/documents/qr/{quote(tracking_number, safe='')}/receipt", json={})
            show_notice(f"Received {tracking_number}. It is now held by your office.")
        except Exception as exc:
            show_notice(f"Unable to receive {tracking_number}: {exc}", error=True)
        load(keep_notice=True)

    def render_incoming(items):
        incoming_title.value = f"To receive ({len(items)})"
        rows = []
        for item in items:
            controls = [
                widgets.document_cell(item),
                ft.Column(
                    [
                        ft.Text(f"From {item.get('from_office') or '-'}", size=12, color=widgets.body_color()),
                        widgets.hint(f"Sent {format_time(item.get('sent_at'))}" + (f" by {item['sent_by']}" if item.get("sent_by") else "")),
                    ],
                    spacing=1,
                    expand=True,
                ),
                widgets.waiting_chip(item),
                *receive_controls(item),
            ]
            button = view_button(item)
            rows.append(widgets.list_row(controls + ([button] if button else [])))
        incoming_list.controls = rows or [widgets.empty("Nothing waiting. Documents passed to this office appear here until you receive them.")]

    def render_holding(holding):
        items = holding.get("items") or []
        total = holding.get("total", len(items))
        total_pages = holding.get("total_pages") or 0
        holding_title.value = f"Holding ({total})"
        rows = []
        for item in items:
            reference = document_reference(item)
            since = item.get("since")
            controls = [
                widgets.document_cell(item),
                ft.Column(
                    [
                        ft.Text(reference or "-", size=12, color=widgets.body_color()),
                        widgets.hint(("Received " if item.get("received_at") else "Registered ") + format_time(since)),
                    ],
                    spacing=1,
                    expand=True,
                ),
                widgets.chip(f"Held {format_elapsed(since)}", ft.Colors.GREEN_700),
            ]
            if can_pass and state["own_office"] and open_pass:
                controls.append(ft.OutlinedButton("Pass on", icon=ft.Icons.SEND_OUTLINED, on_click=lambda _, d=summary_of(item): open_pass(d)))
            button = view_button(item)
            rows.append(widgets.list_row(controls + ([button] if button else [])))
        if not rows:
            message = "No held documents match your search." if (search_field.value or "").strip() else "This office holds no documents right now."
            rows = [widgets.empty(message)]
        holding_list.controls = rows
        page_label.value = f"Page {state['page']} of {max(total_pages, 1)}"
        previous_button.disabled = state["page"] <= 1
        next_button.disabled = state["page"] >= total_pages

    def render_outgoing(items):
        outgoing_title.value = f"Sent, awaiting receipt ({len(items)})"
        rows = []
        for item in items:
            controls = [
                widgets.document_cell(item),
                ft.Column(
                    [
                        ft.Text(f"To {item.get('to_office') or '-'}", size=12, color=widgets.body_color()),
                        widgets.hint(f"Sent {format_time(item.get('sent_at'))}"),
                    ],
                    spacing=1,
                    expand=True,
                ),
                widgets.waiting_chip(item),
            ]
            button = view_button(item)
            rows.append(widgets.list_row(controls + ([button] if button else [])))
        outgoing_list.controls = rows or [widgets.empty("Everything this office sent has been received.")]

    def render(payload):
        office = payload.get("office") or {}
        state["own_office"] = bool(payload.get("own_office"))
        subtitle = (
            "What to receive, what you hold, and what you sent that is not received yet."
            if state["own_office"]
            else f"Monitoring {office.get('name') or 'this office'}. Read-only: receiving and passing on are done by the office itself."
        )
        header_holder.content = section_header(
            f"Office Dashboard · {office.get('name') or 'Your office'}", subtitle, ft.Icons.LOCATION_CITY_OUTLINED, ft.Colors.BLUE_700,
        )
        summary = payload.get("summary") or {}
        overdue_hours = payload.get("overdue_hours") or 24
        kpi_row.controls = [
            widgets.kpi("To receive", summary.get("incoming", 0), f"{summary.get('incoming_overdue', 0)} waiting {overdue_hours}h+", ft.Icons.MOVE_TO_INBOX_OUTLINED, ft.Colors.AMBER_800),
            widgets.kpi("Holding", summary.get("holding", 0), "In this office's custody", ft.Icons.INVENTORY_2_OUTLINED, ft.Colors.GREEN_700),
            widgets.kpi("Sent, not received", summary.get("outgoing", 0), f"{summary.get('outgoing_overdue', 0)} waiting {overdue_hours}h+", ft.Icons.LOCAL_SHIPPING_OUTLINED, ft.Colors.BLUE_700),
            widgets.kpi("Received today", summary.get("received_today", 0), "Receipts confirmed", ft.Icons.TASK_ALT, ft.Colors.TEAL_700),
            widgets.kpi("Sent today", summary.get("sent_today", 0), "Handoffs started", ft.Icons.SEND_OUTLINED, ft.Colors.INDIGO_600),
        ]
        state["incoming"] = payload.get("incoming") or []
        render_incoming(state["incoming"])
        render_holding(payload.get("holding") or {})
        render_outgoing(payload.get("outgoing") or [])
        events = payload.get("recent_activity") or []
        activity_list.controls = [widgets.event_row(event, show_document=True) for event in events] or [widgets.empty("No activity for this office yet.")]

    def load(page_number=None, keep_notice=False, update=True):
        if page_number is not None:
            state["page"] = page_number
        if not keep_notice:
            show_notice("")
        params = {"page": state["page"], "page_size": 10}
        if office_id:
            params["office_id"] = office_id
        if can_search and (search_field.value or "").strip():
            params["search"] = search_field.value.strip()
        try:
            render(api("GET", "/documents/office/queue", params=params))
            updated_text.value = f"Updated {datetime.now().strftime('%I:%M %p')}"
        except Exception as exc:
            message = str(exc)
            if "Office assignment required" in message:
                message = "Your account has not been assigned to an office. Please contact the administrator."
            show_notice(f"Unable to load the office dashboard: {message}", error=True)
        if update:
            page.update()

    def change_page(delta):
        load(page_number=max(1, state["page"] + delta))

    def refresh(_=None):
        load()

    load(update=False)
    header_controls = [ft.Container(header_holder, expand=True), updated_text, ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=refresh)]
    view = ft.Column(
        [
            *([ft.TextButton("All offices", icon=ft.Icons.ARROW_BACK, on_click=lambda _: on_back())] if on_back else []),
            ft.Row(header_controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            notice_text,
            kpi_row,
            surface_card(ft.Column([incoming_title, widgets.hint("Oldest first. Receive a document once it is physically in your office."), incoming_list], spacing=6), padding=18),
            surface_card(
                ft.Column(
                    [
                        holding_title,
                        widgets.hint("Documents in this office's custody. Pass one on to send it to another office."),
                        *([ft.Row([search_field, ft.FilledButton("Search", icon=ft.Icons.SEARCH, on_click=lambda _: load(page_number=1), height=44)], spacing=8)] if can_search else []),
                        holding_list,
                        ft.Row([previous_button, page_label, next_button], alignment=ft.MainAxisAlignment.END),
                    ],
                    spacing=6,
                ),
                padding=18,
            ),
            ft.ResponsiveRow(
                [
                    ft.Container(surface_card(ft.Column([outgoing_title, widgets.hint("Oldest first, so the longest waits are on top."), outgoing_list], spacing=6), padding=18), col={"xs": 12, "lg": 6}),
                    ft.Container(surface_card(ft.Column([widgets.title("Recent activity"), activity_list], spacing=6), padding=18), col={"xs": 12, "lg": 6}),
                ],
                spacing=16,
                run_spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ],
        spacing=16,
    )
    return view, refresh


def build_office_overview_view(page, api, surface_card, section_header, open_office):
    """Every active office's workload, for the Super Administrator. `open_office(office)` opens one."""
    widgets = TrackingWidgets(page)
    notice_text = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)
    rows_column = ft.Column(spacing=0)

    def count_cell(value, label, color, width=110):
        return ft.Column(
            [
                ft.Text(str(value), size=18, weight=ft.FontWeight.BOLD, color=color if value else widgets.muted_color()),
                widgets.hint(label),
            ],
            spacing=0,
            width=width,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def load(update=True):
        notice_text.visible = False
        try:
            payload = api("GET", "/documents/office/overview")
        except Exception as exc:
            notice_text.value = f"Unable to load offices: {exc}"
            notice_text.visible = True
            rows_column.controls = []
            if update:
                page.update()
            return
        rows = []
        for office in payload.get("items") or []:
            name = office.get("name") or "Unnamed office"
            if office.get("office_code"):
                name = f"{name} ({office['office_code']})"
            overdue = office.get("incoming_overdue") or 0
            rows.append(widgets.list_row(
                [
                    ft.Icon(ft.Icons.APARTMENT, color=widgets.link_color(), size=20),
                    ft.Column(
                        [
                            ft.Text(name, size=13, weight=ft.FontWeight.BOLD, color=widgets.heading_color()),
                            *([widgets.chip(f"{overdue} overdue to receive", ft.Colors.RED_700)] if overdue else []),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    count_cell(office.get("incoming", 0), "To receive", ft.Colors.AMBER_800),
                    count_cell(office.get("holding", 0), "Holding", ft.Colors.GREEN_700),
                    count_cell(office.get("outgoing", 0), "Sent, not received", ft.Colors.BLUE_700),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=widgets.muted_color()),
                ],
                on_click=lambda _, selected=office: open_office(selected),
            ))
        rows_column.controls = rows or [widgets.empty("No active offices found.")]
        if update:
            page.update()

    load(update=False)
    return ft.Column(
        [
            ft.Row(
                [
                    ft.Container(section_header("Office Dashboard", "Every active office's workload. Select an office to see its queue.", ft.Icons.LOCATION_CITY_OUTLINED, ft.Colors.BLUE_700), expand=True),
                    ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH, on_click=lambda _: load()),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            notice_text,
            surface_card(rows_column, padding=18),
        ],
        spacing=16,
    )
