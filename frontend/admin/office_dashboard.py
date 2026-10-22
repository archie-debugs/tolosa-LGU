"""Office Dashboard: an office's work queue, and the Super Administrator's overview of every office."""

from datetime import datetime
from urllib.parse import quote

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets, document_reference, format_elapsed, format_time

# Served from the shared assets folder; the banner shows plain colour when it is missing.
BANNER_IMAGE = "sb_tolosa_homepage.jpg"


def page_banner(title, subtitle, icon, corner=None):
    """The blue page heading with the town hall faded in on the right; `corner` sits in its top-right corner."""
    blue = "#0D4FB0"
    layers = [
        ft.Container(
            content=ft.Image(src=BANNER_IMAGE, fit=ft.ImageFit.COVER, error_content=ft.Container()),
            right=0, top=0, bottom=0, width=700,
        ),
        # Blends the photo into the blue, so the heading sits on solid colour.
        ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, 0),
                end=ft.Alignment(1, 0),
                colors=[blue, ft.Colors.with_opacity(0.75, blue), ft.Colors.with_opacity(0.15, blue), ft.Colors.with_opacity(0.0, blue)],
                stops=[0.0, 0.25, 0.6, 1.0],
            ),
            right=0, top=0, bottom=0, width=700,
        ),
        ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(icon, size=32, color=ft.Colors.BLUE_700),
                        width=72, height=72, border_radius=16,
                        alignment=ft.Alignment(0, 0),
                        bgcolor=ft.Colors.with_opacity(0.92, ft.Colors.WHITE),
                    ),
                    ft.Column(
                        [
                            ft.Text(title, size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Text(subtitle, size=15, color=ft.Colors.with_opacity(0.92, ft.Colors.WHITE)),
                        ],
                        spacing=4,
                        alignment=ft.MainAxisAlignment.CENTER,
                        expand=True,
                    ),
                ],
                spacing=24,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(26, 0, 26, 0),
            alignment=ft.Alignment(-1, 0),
            left=0, right=0, top=0, bottom=0,
        ),
    ]
    if corner is not None:
        layers.append(ft.Container(
            content=corner,
            bgcolor=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
            border_radius=20,
            top=10, right=10,
        ))
    return ft.Container(
        content=ft.Stack(layers, height=132),
        gradient=ft.LinearGradient(begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0), colors=["#0B47A3", "#1565C0"]),
        border_radius=16,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )


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
    # "confirming" is the open inline step: ("receive", handoff_id), ("return", ...) or ("cancel", ...).
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

    return_reason = ft.TextField(
        label="Why are you returning it?",
        hint_text="e.g. Sent to the wrong office",
        expand=True,
        max_length=500,
        content_padding=ft.Padding(12, 4, 12, 4),
        on_submit=lambda _: return_confirmed(),
    )

    def receive_controls(item):
        if not (can_receive and state["own_office"]):
            return []
        handoff_id = item.get("handoff_id")
        if state["confirming"] == ("receive", handoff_id):
            return [
                ft.FilledButton("Confirm receipt", icon=ft.Icons.CHECK, on_click=lambda _, i=item: receive(i)),
                ft.TextButton("Cancel", on_click=lambda _: set_confirming(None)),
            ]
        if state["confirming"] == ("return", handoff_id):
            return []
        return [
            ft.OutlinedButton("Receive", icon=ft.Icons.MOVE_TO_INBOX_OUTLINED, on_click=lambda _, h=handoff_id: set_confirming(("receive", h))),
            ft.TextButton("Return", icon=ft.Icons.UNDO, tooltip="Send it back without receiving it", on_click=lambda _, h=handoff_id: set_confirming(("return", h))),
        ]

    def return_step():
        """The reason field shown under an incoming row while it is being returned."""
        return ft.Container(
            ft.Row(
                [
                    return_reason,
                    ft.FilledButton("Return to sender", icon=ft.Icons.UNDO, on_click=lambda _: return_confirmed()),
                    ft.TextButton("Back", on_click=lambda _: set_confirming(None)),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding(4, 0, 4, 10),
        )

    def cancel_controls(item):
        if not (can_pass and state["own_office"]):
            return []
        handoff_id = item.get("handoff_id")
        if state["confirming"] == ("cancel", handoff_id):
            return [
                ft.FilledButton("Cancel handoff", icon=ft.Icons.CANCEL_OUTLINED, on_click=lambda _, i=item: cancel(i)),
                ft.TextButton("Keep", on_click=lambda _: set_confirming(None)),
            ]
        return [ft.TextButton("Cancel", icon=ft.Icons.CANCEL_OUTLINED, tooltip="Call it back before it is received", on_click=lambda _, h=handoff_id: set_confirming(("cancel", h)))]

    def set_confirming(step):
        state["confirming"] = step
        return_reason.value = ""
        return_reason.error_text = None
        render_incoming(state.get("incoming") or [])
        render_outgoing(state.get("outgoing") or [])
        page.update()

    def return_confirmed():
        step = state["confirming"] or (None, None)
        item = next((i for i in state.get("incoming") or [] if step[0] == "return" and i.get("handoff_id") == step[1]), None)
        if item is None:
            return
        reason = (return_reason.value or "").strip()
        if not reason:
            return_reason.error_text = "Say why, so the sending office knows what to fix."
            page.update()
            return
        tracking_number = item.get("tracking_number") or ""
        state["confirming"] = None
        try:
            api("POST", f"/documents/handoffs/{item['handoff_id']}/return", json={"reason": reason})
            show_notice(f"Returned {tracking_number} to {item.get('from_office') or 'the sending office'}.")
        except Exception as exc:
            show_notice(f"Unable to return {tracking_number}: {exc}", error=True)
        load(keep_notice=True)

    def cancel(item):
        tracking_number = item.get("tracking_number") or ""
        state["confirming"] = None
        try:
            api("POST", f"/documents/handoffs/{item['handoff_id']}/cancel", json={})
            show_notice(f"Cancelled the handoff of {tracking_number}. Your office still holds it.")
        except Exception as exc:
            show_notice(f"Unable to cancel the handoff of {tracking_number}: {exc}", error=True)
        load(keep_notice=True)

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
            if state["confirming"] == ("return", item.get("handoff_id")):
                rows.append(return_step())
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
                *cancel_controls(item),
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
        state["outgoing"] = payload.get("outgoing") or []
        render_outgoing(state["outgoing"])
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
            surface_card(ft.Column([incoming_title, widgets.hint("Oldest first. Receive a document once it is physically in your office, or return it if it was not meant for you."), incoming_list], spacing=6), padding=18),
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
                    ft.Container(surface_card(ft.Column([outgoing_title, widgets.hint("Oldest first, so the longest waits are on top. Cancel a handoff that went to the wrong office."), outgoing_list], spacing=6), padding=18), col={"xs": 12, "lg": 6}),
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


def build_office_overview_view(page, api, surface_card, open_office):
    """Every active office's workload, for the Super Administrator. `open_office(office)` opens one."""
    widgets = TrackingWidgets(page)
    notice_text = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)
    rows_column = ft.Column(spacing=12)
    tint = widgets.tone("#F7FAFE", "#1B2430")
    count_tint = widgets.tone("#EDF3FC", "#22303D")

    def count_cell(value, label, color, width=140):
        return ft.Column(
            [
                ft.Text(str(value), size=18, weight=ft.FontWeight.BOLD, color=color if value else widgets.link_color()),
                ft.Text(label, size=12, color=color if value else widgets.muted_color()),
            ],
            spacing=2,
            width=width,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def count_divider():
        return ft.Container(width=1, height=38, bgcolor=widgets.line_color())

    def office_row(office):
        name = office.get("name") or "Unnamed office"
        if office.get("office_code"):
            name = f"{name} ({office['office_code']})"
        overdue = office.get("incoming_overdue") or 0
        counts = ft.Container(
            content=ft.Row(
                [
                    count_cell(office.get("incoming", 0), "To receive", ft.Colors.AMBER_800),
                    count_divider(),
                    count_cell(office.get("holding", 0), "Holding", ft.Colors.GREEN_700),
                    count_divider(),
                    count_cell(office.get("outgoing", 0), "Sent, not received", ft.Colors.BLUE_700),
                ],
                spacing=0,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(4, 10, 4, 10),
            bgcolor=count_tint,
            border_radius=10,
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=widgets.tone(ft.Colors.BLUE_700, ft.Colors.BLUE_300), size=26),
                        width=54, height=54, border_radius=14,
                        alignment=ft.Alignment(0, 0),
                        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.BLUE_700),
                    ),
                    ft.Column(
                        [
                            ft.Text(name, size=16, weight=ft.FontWeight.BOLD, color=widgets.link_color()),
                            *([widgets.chip(f"{overdue} overdue to receive", ft.Colors.RED_700)] if overdue else []),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    counts,
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=widgets.tone(ft.Colors.BLUE_700, ft.Colors.BLUE_300)),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(10, 6, 12, 6),
            bgcolor=tint,
            border=ft.border.all(1, widgets.line_color()),
            border_radius=12,
            on_click=lambda _, selected=office: open_office(selected),
            ink=True,
        )

    def banner():
        return page_banner(
            "Office Dashboard",
            "Every active office's workload. Select an office to see its queue.",
            ft.Icons.ACCOUNT_BALANCE,
            corner=ft.IconButton(ft.Icons.REFRESH, icon_color=ft.Colors.WHITE, tooltip="Refresh", on_click=lambda _: load()),
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
        rows_column.controls = [office_row(office) for office in payload.get("items") or []] or [widgets.empty("No active offices found.")]
        if update:
            page.update()

    load(update=False)
    return ft.Column(
        [
            banner(),
            notice_text,
            surface_card(rows_column, padding=18),
        ],
        spacing=16,
    )
