"""Documents for SB Members: the documents employees set for SB Members to have at hand on a day."""

from datetime import date, datetime, timedelta

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets, document_reference

# Served from the shared assets folder; the banner shows plain colour when it is missing.
BANNER_IMAGE = "sb_tolosa_homepage.jpg"


def document_label(document):
    reference = document_reference(document)
    return f"{document.get('tracking_number') or '-'} · {reference}" if reference else (document.get("tracking_number") or "-")


def has_file(document):
    if "has_attachment" in document:
        return bool(document["has_attachment"])
    return bool(document.get("attachments"))


def picked_date(value):
    """The day a DatePicker returned; newer Flet releases send it as a zoned time."""
    if isinstance(value, datetime):
        return (value.astimezone() if value.tzinfo else value).date()
    return value if isinstance(value, date) else None


def build_todays_documents_view(page, api, surface_card, today=None, open_details=None):
    """`api(method, path, **kwargs)` calls the main backend and returns parsed JSON or raises.
    `open_details(document)` opens a document's details, when the user may see them."""
    widgets = TrackingWidgets(page)
    today = today or date.today()
    state = {
        "date": today, "today": today, "items": [], "upcoming": [],
        "results": [], "results_page": 1, "results_pages": 1, "results_total": 0,
        "editing": None, "removed": None, "notice": ("", False),
    }

    date_text = ft.Text(size=16, weight=ft.FontWeight.BOLD, color=widgets.heading_color())
    date_hint = widgets.hint("")
    counts_text = ft.Text("", size=13, color=widgets.body_color())
    notice_row = ft.Row([], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    upcoming_row = ft.Row([], spacing=8, wrap=True, run_spacing=8)
    list_column = ft.Column(spacing=0)
    results_column = ft.Column(spacing=0)
    results_summary = widgets.hint("")
    previous_results = ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Previous page", on_click=lambda _: load_documents(state["results_page"] - 1))
    next_results = ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Next page", on_click=lambda _: load_documents(state["results_page"] + 1))
    search_field = ft.TextField(
        hint_text="Search by title, tracking or document number",
        prefix_icon=ft.Icons.SEARCH,
        expand=True,
        height=46,
        border_radius=10,
        border_color=widgets.line_color(),
        focused_border_color=ft.Colors.BLUE_700,
        content_padding=ft.Padding(12, 4, 12, 4),
    )
    search_section = ft.Column(spacing=12)
    date_picker = ft.DatePicker(first_date=datetime(2020, 1, 1), last_date=datetime(2100, 12, 31))

    def accent():
        return widgets.tone(ft.Colors.BLUE_700, ft.Colors.BLUE_300)

    def tint():
        return widgets.tone("#F4F8FE", "#1B2430")

    def card_title(icon, title, *extra, subtitle=None):
        """A card's title with its round icon badge."""
        heading = ft.Row(
            [ft.Text(title, size=17, weight=ft.FontWeight.BOLD, color=widgets.link_color()), *extra],
            spacing=20, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        badge = ft.Container(
            content=ft.Icon(icon, size=24, color=accent()),
            width=44, height=44, border_radius=22,
            alignment=ft.Alignment(0, 0),
            bgcolor=ft.Colors.with_opacity(0.10, accent()),
        )
        lines = [heading, widgets.hint(subtitle)] if subtitle else [heading]
        return ft.Row([badge, ft.Column(lines, spacing=4, expand=True)], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def empty_state(message):
        return ft.Container(
            content=ft.Row(
                [ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=20, color=widgets.muted_color()), ft.Text(message, size=13, color=widgets.muted_color(), expand=True)],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=18,
            bgcolor=tint(),
            border=ft.border.all(1, widgets.line_color()),
            border_radius=10,
        )

    def boxed(control):
        """A date-bar button in its own framed tile."""
        return ft.Container(
            content=control,
            padding=ft.Padding(4, 2, 4, 2),
            bgcolor=tint(),
            border=ft.border.all(1, widgets.line_color()),
            border_radius=12,
        )

    def banner():
        background = widgets.tone("#EEF4FD", "#16202C")
        icon_tile = ft.Container(
            content=ft.Container(
                content=ft.Icon(ft.Icons.DESCRIPTION, size=30, color=ft.Colors.WHITE),
                width=62, height=62, border_radius=14,
                alignment=ft.Alignment(0, 0),
                bgcolor=ft.Colors.BLUE_700,
            ),
            padding=6,
            border_radius=18,
            bgcolor=ft.Colors.with_opacity(0.14, ft.Colors.BLUE_700),
        )
        heading = ft.Column(
            [
                ft.Text("Documents for SB Members", size=24, weight=ft.FontWeight.BOLD, color=widgets.link_color()),
                ft.Text("Set the documents SB Members need for the day. They appear right away in the SB Member app.", size=14, color=widgets.muted_color()),
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )
        return ft.Container(
            content=ft.Stack(
                [
                    ft.Container(
                        content=ft.Image(src=BANNER_IMAGE, fit=ft.ImageFit.COVER, opacity=0.45, error_content=ft.Container()),
                        right=0, top=0, bottom=0, width=560,
                    ),
                    # Fades the photo in from the left, so it has no visible edge.
                    ft.Container(
                        gradient=ft.LinearGradient(
                            begin=ft.Alignment(-1, 0),
                            end=ft.Alignment(1, 0),
                            colors=[background, ft.Colors.with_opacity(0.7, background), ft.Colors.with_opacity(0.2, background), ft.Colors.with_opacity(0.1, background)],
                            stops=[0.0, 0.3, 0.7, 1.0],
                        ),
                        right=0, top=0, bottom=0, width=560,
                    ),
                    ft.Container(
                        content=ft.Row([icon_tile, heading], spacing=22, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.Padding(20, 0, 20, 0),
                        alignment=ft.Alignment(-1, 0),
                        left=0, right=0, top=0, bottom=0,
                    ),
                ],
                height=124,
            ),
            bgcolor=background,
            border=ft.border.all(1, widgets.line_color()),
            border_radius=18,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    def editable():
        return state["date"] >= state["today"]

    def notify(message, error=False, undo=None):
        state["notice"] = (message, error)
        state["removed"] = undo

    def render_notice():
        message, error = state["notice"]
        notice_row.controls = [ft.Text(message, size=12, color=ft.Colors.RED_700 if error else ft.Colors.GREEN_700)] if message else []
        if message and state["removed"]:
            notice_row.controls.append(ft.TextButton("Undo", icon=ft.Icons.UNDO, on_click=undo_remove))

    def render_header():
        day = state["date"]
        date_text.value = day.strftime("%A, %B %d, %Y")
        if day == state["today"]:
            date_hint.value = "Today: SB Members see this list now."
        elif day > state["today"]:
            date_hint.value = "SB Members will see this list on that day."
        else:
            date_hint.value = "A past day, shown for reference. It can no longer be changed."
        items = state["items"]
        hidden = sum(1 for entry in items if entry["document"].get("archived"))
        no_file = sum(1 for entry in items if not has_file(entry["document"]))
        parts = [f"{len(items)} document{'s' if len(items) != 1 else ''}"]
        if hidden:
            parts.append(f"{hidden} hidden from members")
        if no_file:
            parts.append(f"{no_file} without a file")
        counts_text.value = " · ".join(parts)

    def render_upcoming():
        chips = []
        for item in state["upcoming"]:
            day = date.fromisoformat(item["date"])
            selected = day == state["date"]
            label = ("Today" if day == state["today"] else day.strftime("%a, %b %d")) + f" · {item['count']}"
            color = ft.Colors.RED_700 if item.get("hidden") else widgets.link_color()
            chips.append(ft.Container(
                content=ft.Text(label, size=12, weight=ft.FontWeight.BOLD if selected else ft.FontWeight.W_500, color=color),
                padding=ft.Padding(10, 5, 10, 5),
                bgcolor=ft.Colors.with_opacity(0.16 if selected else 0.06, color),
                border_radius=12,
                tooltip=f"{item['count']} document(s)" + (f", {item['hidden']} hidden from members" if item.get("hidden") else ""),
                on_click=lambda _, d=day: go_to(d),
                ink=True,
            ))
        upcoming_row.controls = [widgets.hint("Upcoming lists:"), *chips] if chips else [widgets.hint("No upcoming lists yet.")]

    def entry_row(index, entry):
        document = entry["document"]
        items = state["items"]
        tags = []
        if document.get("archived"):
            tags.append(widgets.chip("Archived · hidden from members", ft.Colors.RED_700))
        if not has_file(document):
            tags.append(widgets.chip("No file", ft.Colors.AMBER_800))
        details = [
            ft.Text(document_label(document), size=12, weight=ft.FontWeight.BOLD, color=widgets.link_color()),
            ft.Text(document.get("title") or "Untitled", size=13, weight=ft.FontWeight.W_600, color=widgets.heading_color()),
        ]
        if tags:
            details.append(ft.Row(tags, spacing=6, wrap=True))
        if state["editing"] == entry["id"]:
            note_field = ft.TextField(value=entry.get("note") or "", hint_text="Note for SB Members, e.g. 'For second reading'", max_length=500)
            details += [
                note_field,
                ft.Row([
                    ft.FilledButton("Save note", icon=ft.Icons.CHECK, on_click=lambda _, e=entry, f=note_field: save_note(e, f)),
                    ft.TextButton("Cancel", on_click=lambda _: set_editing(None)),
                ], spacing=8),
            ]
        elif entry.get("note"):
            details.append(ft.Text(entry["note"], size=12, italic=True, color=widgets.body_color()))
        if entry.get("added_by"):
            details.append(widgets.hint(f"Added by {entry['added_by']}"))

        actions = []
        if open_details:
            actions.append(ft.IconButton(ft.Icons.VISIBILITY_OUTLINED, tooltip="View details", on_click=lambda _, d=document: open_details(d)))
        if editable():
            actions += [
                ft.IconButton(ft.Icons.EDIT_NOTE, tooltip="Edit note" if entry.get("note") else "Add note", on_click=lambda _, e=entry: set_editing(e["id"])),
                ft.IconButton(ft.Icons.ARROW_UPWARD, tooltip="Move up", disabled=index == 0, on_click=lambda _, i=index: move(i, -1)),
                ft.IconButton(ft.Icons.ARROW_DOWNWARD, tooltip="Move down", disabled=index == len(items) - 1, on_click=lambda _, i=index: move(i, 1)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remove from this day", icon_color=ft.Colors.RED_600, on_click=lambda _, e=entry, i=index: remove(e, i)),
            ]
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(f"{index + 1}.", width=28, size=14, weight=ft.FontWeight.BOLD, color=widgets.muted_color()),
                    ft.Column(details, spacing=4, expand=True),
                    *actions,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding(4, 10, 4, 10),
            border=ft.Border(bottom=ft.BorderSide(1, widgets.line_color())),
        )

    def render_list():
        items = state["items"]
        list_column.controls = [entry_row(index, entry) for index, entry in enumerate(items)] or [
            empty_state("No documents set for this day yet." + (" Search below to add some." if editable() else ""))
        ]

    def render_results():
        results = state["results"]
        searching = bool((search_field.value or "").strip())
        total, page_number, pages = state["results_total"], state["results_page"], state["results_pages"]
        results_summary.value = (
            f"{total} document{'s' if total != 1 else ''}" + (" match" if searching else "") + f" · page {page_number} of {pages}"
        )
        previous_results.disabled = page_number <= 1
        next_results.disabled = page_number >= pages
        on_list = {entry["document"]["id"] for entry in state["items"]}
        rows = []
        for document in results:
            tags = [widgets.chip("No file", ft.Colors.AMBER_800)] if not has_file(document) else []
            action = (
                widgets.chip("On this list", ft.Colors.GREEN_700)
                if document["id"] in on_list
                else ft.OutlinedButton("Add", icon=ft.Icons.ADD, on_click=lambda _, d=document: add(d))
            )
            rows.append(widgets.list_row([
                ft.Column(
                    [
                        ft.Text(document_label(document), size=12, weight=ft.FontWeight.BOLD, color=widgets.link_color()),
                        ft.Text(document.get("title") or "Untitled", size=12, color=widgets.body_color()),
                        *([ft.Row(tags, spacing=6)] if tags else []),
                    ],
                    spacing=2,
                    expand=True,
                ),
                action,
            ]))
        results_column.controls = rows or [empty_state("No documents match your search." if searching else "There are no active documents yet.")]

    def render(update=True):
        render_header()
        render_upcoming()
        render_notice()
        render_list()
        render_results()
        search_section.visible = editable()
        if update:
            page.update()

    def load_upcoming():
        try:
            state["upcoming"] = api("GET", "/todays-documents/upcoming").get("items", [])
        except Exception:
            state["upcoming"] = []

    def load(update=True, keep_notice=False):
        if not keep_notice:
            notify("")
        try:
            payload = api("GET", "/todays-documents", params={"date": state["date"].isoformat()})
            state["items"] = payload.get("items", [])
            state["today"] = date.fromisoformat(payload.get("today") or state["today"].isoformat())
        except Exception as exc:
            state["items"] = []
            notify(f"Unable to load the list: {exc}", error=True)
        load_upcoming()
        render(update)

    def go_to(day):
        state.update(date=day, editing=None)
        load()

    def pick_date(_=None):
        date_picker.value = datetime.combine(state["date"], datetime.min.time())
        (getattr(page, "open", None) or page.show_dialog)(date_picker)

    def on_date_picked(e):
        day = picked_date(e.control.value)
        if day and day != state["date"]:
            go_to(day)

    date_picker.on_change = on_date_picked

    def set_editing(entry_id):
        state["editing"] = entry_id
        notify("")
        render()

    def save_note(entry, field):
        try:
            api("PATCH", f"/todays-documents/{entry['id']}", json={"note": field.value or None})
            state["editing"] = None
            notify("Note saved. SB Members see it with the document.")
        except Exception as exc:
            notify(f"Unable to save the note: {exc}", error=True)
        load(keep_notice=True)

    def add(document):
        try:
            api("POST", "/todays-documents", json={"scheduled_for": state["date"].isoformat(), "document_id": document["id"]})
            notify(f"Added {document.get('tracking_number') or 'the document'}. Use the note button to add a note for SB Members.")
        except Exception as exc:
            notify(f"Unable to add: {exc}", error=True)
        load(keep_notice=True)

    def remove(entry, index):
        document = entry["document"]
        try:
            api("DELETE", f"/todays-documents/{entry['id']}")
            undo = {"document_id": document["id"], "note": entry.get("note"), "position": index, "date": state["date"]}
            notify(f"Removed {document.get('tracking_number') or 'the document'} from this day.", undo=undo)
        except Exception as exc:
            notify(f"Unable to remove: {exc}", error=True)
        load(keep_notice=True)

    def undo_remove(_=None):
        removed = state["removed"]
        if not removed:
            return
        try:
            api("POST", "/todays-documents", json={
                "scheduled_for": removed["date"].isoformat(),
                "document_id": removed["document_id"],
                "note": removed["note"],
                "position": removed["position"],
            })
            notify("Put back.")
        except Exception as exc:
            notify(f"Unable to put it back: {exc}", error=True)
        load(keep_notice=True)

    def move(index, delta):
        ids = [entry["id"] for entry in state["items"]]
        ids[index], ids[index + delta] = ids[index + delta], ids[index]
        try:
            payload = api("PUT", "/todays-documents/order", json={"scheduled_for": state["date"].isoformat(), "entry_ids": ids})
            state["items"] = payload.get("items", [])
            notify("")
        except Exception as exc:
            notify(f"Unable to reorder: {exc}", error=True)
        render()

    def fetch_documents(page_number):
        """Every document except archived ones, newest first, narrowed by the search box."""
        params = {"archived": "false", "page": max(1, page_number), "page_size": 10, "sort_by": "created_at", "sort_order": "desc"}
        query = (search_field.value or "").strip()
        if query:
            params["search"] = query
        try:
            payload = api("GET", "/documents", params=params)
            state.update(
                results=payload.get("items", []),
                results_page=payload.get("page", params["page"]),
                results_pages=max(payload.get("total_pages") or 1, 1),
                results_total=payload.get("total", len(payload.get("items", []))),
            )
        except Exception as exc:
            state.update(results=[], results_page=1, results_pages=1, results_total=0)
            notify(f"Unable to load documents: {exc}", error=True)

    def load_documents(page_number=1):
        fetch_documents(page_number)
        render()

    def search(_=None):
        notify("")
        load_documents(1)

    def clear_search(_=None):
        search_field.value = ""
        search(None)

    search_field.on_submit = search
    search_section.controls = [
        card_title(
            ft.Icons.ADD_CIRCLE, "Add a document",
            subtitle="All documents except archived ones, newest first. Archived documents are left out because SB Members cannot see them.",
        ),
        ft.Row(
            [
                search_field,
                ft.FilledButton(
                    "Search", icon=ft.Icons.SEARCH, on_click=search, height=46,
                    style=ft.ButtonStyle(shape=ft.StadiumBorder(), padding=ft.Padding(28, 0, 28, 0), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
                ),
                ft.TextButton("Clear", on_click=clear_search, style=ft.ButtonStyle(color=accent())),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        results_column,
        ft.Row([results_summary, previous_results, next_results], alignment=ft.MainAxisAlignment.END, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ]

    date_text.size = 19
    date_text.color = widgets.link_color()
    date_hint.size = 13
    date_bar = ft.Row(
        [
            ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_color=accent(), tooltip="Previous day", on_click=lambda _: go_to(state["date"] - timedelta(days=1))),
            ft.Column([date_text, date_hint, upcoming_row], spacing=6, expand=True),
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_color=accent(), tooltip="Next day", on_click=lambda _: go_to(state["date"] + timedelta(days=1))),
            boxed(ft.IconButton(ft.Icons.CALENDAR_MONTH, icon_color=accent(), tooltip="Pick a date", on_click=pick_date)),
            boxed(ft.TextButton("Today", icon=ft.Icons.TODAY, on_click=lambda _: go_to(state["today"]), style=ft.ButtonStyle(color=accent()))),
        ],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    fetch_documents(1)
    load(update=False, keep_notice=True)
    return ft.Column(
        [
            banner(),
            surface_card(date_bar, padding=ft.Padding(14, 18, 18, 18)),
            surface_card(ft.Column([card_title(ft.Icons.DESCRIPTION_OUTLINED, "On this day's list", counts_text), notice_row, list_column], spacing=12), padding=20),
            surface_card(search_section, padding=20),
        ],
        spacing=16,
    )
