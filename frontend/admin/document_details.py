"""Document details: what a document is, where it is now, its full trail, and what your office can do with it."""

import base64
import inspect
from urllib.parse import quote

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets, document_reference, format_elapsed, format_time, parse_time

# What an office can record having done to a document it holds. Receiving is its own step.
ACTION_TYPES = ("Signed", "Reviewed", "Approved", "Noted", "Other")

# Where the document is now: (icon, colour).
LOCATION_STYLES = {
    "held": (ft.Icons.APARTMENT, ft.Colors.GREEN_700),
    "in_transit": (ft.Icons.LOCAL_SHIPPING_OUTLINED, ft.Colors.AMBER_800),
    "archived": (ft.Icons.ARCHIVE_OUTLINED, ft.Colors.BLUE_GREY_600),
    "unrouted": (ft.Icons.HOURGLASS_EMPTY, ft.Colors.BLUE_GREY_600),
}

PRIORITY_COLORS = {"high": ft.Colors.RED_700, "medium": ft.Colors.AMBER_800, "low": ft.Colors.BLUE_GREY_600}

# Flet 0.28 takes base64 text in `src_base64`; newer releases take the bytes in `src`.
IMAGE_TAKES_BASE64 = "src_base64" in inspect.signature(ft.Image.__init__).parameters


def outline(color):
    side = ft.BorderSide(1, color)
    return ft.Border(left=side, top=side, right=side, bottom=side)


def format_date(value):
    """'Oct 20, 2026 09:30 AM', or 'Oct 20, 2026' for a date without a time."""
    if not value or value == "-":
        return "-"
    text = str(value)
    parsed = parse_time(text)
    if not parsed:
        return text
    if len(text) <= 10:
        return parsed.strftime("%b %d, %Y")
    return parsed.astimezone().strftime("%b %d, %Y %I:%M %p")


def describe_location(location, events):
    """(headline, detail) for the location banner."""
    state = location.get("state")
    since, actor = location.get("since"), location.get("actor")
    if state == "in_transit":
        detail = f"Sent from {location.get('office') or '-'}" + (f" by {actor}" if actor else "")
        return f"In transit → {location.get('to_office') or '-'}", f"{detail} · {format_time(since)} · waiting {format_elapsed(since)}"
    if state == "archived":
        headline = f"Archived on {format_date(since)}" + (f" by {actor}" if actor else "")
        return headline, f"Last held by {location['office']}" if location.get("office") else ""
    if state == "held":
        last_move = next((event for event in events if event.get("type") in ("received", "registered")), {})
        how = "Received" if last_move.get("type") == "received" else "Registered"
        detail = f"{how}" + (f" by {actor}" if actor else "") + (f" · held {format_elapsed(since)}" if since else "")
        return f"Held by {location.get('office') or '-'}" + (f" since {format_time(since)}" if since else ""), detail
    return "Not routed yet", "No office has this document on record."


def open_document_details(
    page,
    dialog,
    api,
    document_id,
    *,
    normalize,
    load_qr_image=None,
    can_edit=False,
    can_download=False,
    can_print=False,
    open_pass=None,
    open_edit=None,
    preview=None,
    download=None,
    on_change=None,
):
    """Load a document into `dialog` and open it; raises when it cannot be loaded.

    `api(method, path, **kwargs)` calls the main backend and returns parsed JSON or raises.
    The backend decides what the user's office can do now (receive, pass on, record an
    action); the `can_*` flags only cover what the user's permissions allow.
    `load_qr_image(document_id)` returns the QR code as base64 PNG, or None when the
    user may not see it. `on_change()` runs after a receipt or action is recorded.
    """
    widgets = TrackingWidgets(page)
    state = {"payload": None, "confirming": False, "action": None, "notice": ("", False)}
    qr_base64 = load_qr_image(document_id) if load_qr_image else None

    def fetch():
        state["payload"] = api("GET", f"/documents/{document_id}/overview")

    def notify(message, error=False):
        state["notice"] = (message, error)

    def changed():
        if on_change:
            try:
                on_change()
            except Exception:
                pass

    def summary():
        return normalize(state["payload"].get("document") or {})

    def close_then(callback):
        dialog.open = False
        page.update()
        callback(summary())

    def reload(update=True):
        try:
            fetch()
        except Exception as exc:
            notify(f"Unable to refresh the document: {exc}", error=True)
        render()
        if update:
            page.update()

    def receive(_):
        tracking_number = (state["payload"].get("document") or {}).get("tracking_number") or ""
        state["confirming"] = False
        try:
            api("POST", f"/documents/qr/{quote(tracking_number, safe='')}/receipt", json={})
            notify(f"Received {tracking_number}. Your office holds it now.")
            changed()
        except Exception as exc:
            notify(f"Unable to receive {tracking_number}: {exc}", error=True)
        reload()

    def save_action(notes_field):
        tracking_number = (state["payload"].get("document") or {}).get("tracking_number") or ""
        action_type = state["action"]
        try:
            api(
                "POST",
                f"/documents/qr/{quote(tracking_number, safe='')}/actions",
                json={"action_type": action_type, "notes": (notes_field.value or "").strip() or None},
            )
            state["action"] = None
            notify(f"Recorded: {action_type}.")
            changed()
        except Exception as exc:
            notify(f"Unable to record {action_type}: {exc}", error=True)
        reload()

    def set_state(update=True, **changes):
        state.update(changes)
        notify("")
        render()
        if update:
            page.update()

    def tags(document):
        chips = []
        if "is_public" in document:
            chips.append(widgets.chip("Public", ft.Colors.TEAL_700) if document.get("is_public") else widgets.chip("Private", ft.Colors.BLUE_GREY_600))
        if document.get("priority"):
            chips.append(widgets.chip(f"{document['priority']} priority", PRIORITY_COLORS.get(str(document["priority"]).lower(), ft.Colors.BLUE_GREY_600)))
        if document.get("status"):
            chips.append(widgets.chip(document["status"], ft.Colors.INDIGO_600))
        if document.get("archived"):
            chips.append(widgets.chip("Archived", ft.Colors.BLUE_GREY_600))
        return chips

    def header(document):
        reference = document_reference(document)
        return ft.Column(
            [
                ft.Text(
                    (document.get("tracking_number") or "-") + (f" · {reference}" if reference else ""),
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    color=widgets.link_color(),
                ),
                ft.Text(document.get("title") or "Untitled", size=18, weight=ft.FontWeight.BOLD, color=widgets.heading_color()),
                ft.Row(tags(document), spacing=6, wrap=True),
            ],
            spacing=4,
        )

    def location_banner(location, events):
        icon, color = LOCATION_STYLES.get(location.get("state"), LOCATION_STYLES["unrouted"])
        headline, detail = describe_location(location, events)
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, color=color, size=26),
                    ft.Column(
                        [
                            ft.Text(headline, size=14, weight=ft.FontWeight.BOLD, color=widgets.heading_color()),
                            *([ft.Text(detail, size=12, color=widgets.muted_color())] if detail else []),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=12,
            ),
            padding=12,
            bgcolor=ft.Colors.with_opacity(0.08, color),
            border=ft.Border(left=ft.BorderSide(4, color)),
            border_radius=10,
        )

    def action_buttons(document, can):
        attachments = [item for item in document.get("attachments") or [] if isinstance(item, dict) and item.get("id")]
        has_pdf = any(
            (item.get("mime_type") or "").lower() == "application/pdf" or str(item.get("original_filename") or "").lower().endswith(".pdf")
            for item in attachments
        )
        buttons = []
        if can.get("receive"):
            if state["confirming"]:
                buttons += [
                    ft.FilledButton("Confirm receipt", icon=ft.Icons.CHECK, on_click=receive),
                    ft.TextButton("Cancel", on_click=lambda _: set_state(confirming=False)),
                ]
            else:
                buttons.append(ft.FilledButton("Receive", icon=ft.Icons.MOVE_TO_INBOX_OUTLINED, on_click=lambda _: set_state(confirming=True)))
        if can.get("pass") and open_pass:
            buttons.append(ft.FilledButton("Pass on", icon=ft.Icons.SEND_OUTLINED, on_click=lambda _: close_then(open_pass)))
        if can.get("record_action") and state["action"] is None:
            buttons.append(ft.OutlinedButton("Record action", icon=ft.Icons.TASK_ALT, on_click=lambda _: set_state(action="")))
        if has_pdf and (can_download or can_print) and preview:
            buttons.append(ft.OutlinedButton("Preview", icon=ft.Icons.VISIBILITY_OUTLINED, on_click=lambda _: preview(summary())))
        if attachments and can_download and download:
            buttons.append(ft.OutlinedButton("Download", icon=ft.Icons.DOWNLOAD_OUTLINED, on_click=lambda _: download(summary())))
        if can_edit and open_edit and not document.get("archived"):
            buttons.append(ft.OutlinedButton("Edit", icon=ft.Icons.EDIT_OUTLINED, on_click=lambda _: close_then(open_edit)))
        return ft.Row(buttons, spacing=8, run_spacing=8, wrap=True) if buttons else None

    def action_panel():
        """Choose what was done, add a note, save."""
        notes = ft.TextField(label="Notes (optional)", multiline=True, min_lines=2, max_lines=4)
        choices = [
            (ft.FilledButton if state["action"] == action_type else ft.OutlinedButton)(
                action_type, on_click=lambda _, value=action_type: set_state(action=value)
            )
            for action_type in ACTION_TYPES
        ]
        return ft.Container(
            content=ft.Column(
                [
                    widgets.title("What did your office do with this document?"),
                    ft.Row(choices, spacing=8, run_spacing=8, wrap=True),
                    notes,
                    ft.Row(
                        [
                            ft.FilledButton("Save action", icon=ft.Icons.SAVE_OUTLINED, disabled=not state["action"], on_click=lambda _: save_action(notes)),
                            ft.TextButton("Cancel", on_click=lambda _: set_state(action=None)),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=10,
            ),
            padding=12,
            border=outline(widgets.line_color()),
            border_radius=10,
        )

    def field(label, value):
        return ft.Column(
            [widgets.hint(label), ft.Text(str(value) if value not in (None, "") else "-", size=13, color=widgets.body_color(), selectable=True)],
            spacing=2,
            col={"xs": 12, "sm": 6},
        )

    def details_grid(document):
        """Only fields this user's view of the document carries; office staff get fewer."""
        attachments = [item for item in document.get("attachments") or [] if isinstance(item, dict)]
        file_names = ", ".join(str(item.get("original_filename")) for item in attachments if item.get("original_filename"))
        candidates = [
            ("Document type", "document_type", None),
            ("Category", "category", None),
            ("Legislative number", "document_number", None),
            ("Series year", "series_year", None),
            ("Originating office", "originating_office", None),
            ("Assigned to", "assigned_to", None),
            ("Author", "author", None),
            ("Session", "session", None),
            ("Registered", "created_at", format_date),
            ("Registered by", "created_by", None),
            ("Last updated", "updated_at", format_date),
        ]
        # date_registered is the registration day; it only stands in for older records without created_at.
        document = {**document, "created_at": document.get("created_at") or document.get("date_registered")}
        fields = [field(label, (formatter or (lambda v: v))(document.get(key))) for label, key, formatter in candidates if key in document]
        fields.append(field("File", file_names or document.get("attachment_name") or "No file attached"))
        return ft.ResponsiveRow(fields, spacing=16, run_spacing=12)

    def text_block(label, text):
        return ft.Column([widgets.hint(label), ft.Text(text, size=13, color=widgets.body_color(), selectable=True)], spacing=2)

    def qr_block(document):
        image = ft.Image(src_base64=qr_base64, width=180, height=180) if IMAGE_TAKES_BASE64 else ft.Image(src=base64.b64decode(qr_base64), width=180, height=180)
        return ft.Column(
            [
                widgets.hint("QR code"),
                ft.Container(content=image, padding=8, bgcolor=ft.Colors.WHITE, border_radius=10, width=196, height=196),
                widgets.hint("Scan to track this document."),
            ],
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def render():
        payload = state["payload"] or {}
        document = payload.get("document") or {}
        events = payload.get("events") or []
        can = payload.get("can") or {}
        message, error = state["notice"]
        buttons = action_buttons(document, can)
        grid = details_grid(document)
        body = (
            ft.ResponsiveRow(
                [
                    ft.Container(grid, col={"xs": 12, "md": 8}),
                    ft.Container(qr_block(document), col={"xs": 12, "md": 4}),
                ],
                spacing=16,
                run_spacing=16,
            )
            if qr_base64
            else grid
        )
        sections = [
            header(document),
            location_banner(payload.get("location") or {}, events),
            *([ft.Text(message, size=12, color=ft.Colors.RED_700 if error else ft.Colors.GREEN_700)] if message else []),
            *([buttons] if buttons else []),
            *([action_panel()] if can.get("record_action") and state["action"] is not None else []),
            ft.Divider(height=1, color=widgets.line_color()),
            body,
            *([text_block("Description", document["description"])] if document.get("description") else []),
            *([text_block("Remarks", document["remarks"])] if document.get("remarks") else []),
            ft.Divider(height=1, color=widgets.line_color()),
            widgets.title(f"Trail ({len(events)})"),
            ft.Column([widgets.event_row(event, show_document=False) for event in events] or [widgets.empty("No movement recorded yet.")], spacing=0),
        ]
        mobile = (page.width or 1024) <= 600
        width = max(280, (page.width or 360) - 32) if mobile else 680
        dialog.title = ft.Text("Document details", color=widgets.heading_color())
        dialog.content = ft.Container(
            content=ft.Column(sections, spacing=14, scroll=ft.ScrollMode.AUTO),
            width=width,
            padding=ft.Padding(4, 0, 4, 0),
        )

    fetch()
    render()
    dialog.open = True
    page.update()
    return True
