"""Employee screen for Today's Documents: set the documents SB Members see for a day."""

from datetime import date, timedelta

import flet as ft


def document_label(document):
    number = document.get("document_number")
    series = document.get("series_year")
    reference = f"No. {number}" + (f" s. {series}" if series else "") if number else "No number"
    return f"{document.get('tracking_number') or '-'} · {reference}"


def build_todays_documents_view(page, api, surface_card, section_header, today=None):
    """`api(method, path, **kwargs)` calls the main backend and returns parsed JSON or raises."""
    today = today or date.today()
    state = {"date": today, "today": today, "items": []}

    date_text = ft.Text(size=15, weight=ft.FontWeight.BOLD)
    date_hint = ft.Text(size=12, color=ft.Colors.BLUE_GREY_600)
    list_column = ft.Column(spacing=6)
    status_text = ft.Text("", size=12, color=ft.Colors.RED_700)
    search_field = ft.TextField(hint_text="Search by title, tracking or document number", prefix_icon=ft.Icons.SEARCH, expand=True, height=44, content_padding=ft.padding.symmetric(horizontal=12, vertical=4))
    note_field = ft.TextField(hint_text="Note for SB Members (optional), e.g. 'For second reading'", expand=True, height=44, max_length=500, counter_text="", content_padding=ft.padding.symmetric(horizontal=12, vertical=4))
    results_column = ft.Column(spacing=4)

    def editable():
        return state["date"] >= state["today"]

    def show_error(message):
        status_text.value = message
        page.update()

    def render_list():
        day = state["date"]
        date_text.value = day.strftime("%A, %B %d, %Y")
        if day == state["today"]:
            date_hint.value = "Today: SB Members see this list now."
        elif day > state["today"]:
            date_hint.value = "SB Members will see this list on that day."
        else:
            date_hint.value = "A past day, shown for reference."
        items = state["items"]
        if not items:
            list_column.controls = [ft.Text("No documents set for this day yet.", size=12, color=ft.Colors.BLUE_GREY_500)]
            return
        rows = []
        for index, entry in enumerate(items):
            document = entry["document"]
            controls = [
                ft.Text(f"{index + 1}.", width=28, weight=ft.FontWeight.BOLD),
                ft.Column([
                    ft.Text(document.get("title") or "Untitled", size=13, weight=ft.FontWeight.W_600),
                    ft.Text(document_label(document), size=11, color=ft.Colors.BLUE_GREY_600),
                    *([ft.Text(entry["note"], size=11, italic=True, color=ft.Colors.BLUE_700)] if entry.get("note") else []),
                ], spacing=2, expand=True),
            ]
            if editable():
                controls += [
                    ft.IconButton(ft.Icons.ARROW_UPWARD, tooltip="Move up", disabled=index == 0, on_click=lambda _, i=index: move(i, -1)),
                    ft.IconButton(ft.Icons.ARROW_DOWNWARD, tooltip="Move down", disabled=index == len(items) - 1, on_click=lambda _, i=index: move(i, 1)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remove from this day", icon_color=ft.Colors.RED_600, on_click=lambda _, e=entry: remove(e)),
                ]
            rows.append(ft.Container(ft.Row(controls, vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=ft.padding.symmetric(horizontal=8, vertical=6), border=ft.border.all(1, ft.Colors.BLUE_GREY_100), border_radius=8))
        list_column.controls = rows

    def load(update=True):
        status_text.value = ""
        try:
            payload = api("GET", "/todays-documents", params={"date": state["date"].isoformat()})
            state["items"] = payload.get("items", [])
            state["today"] = date.fromisoformat(payload.get("today") or state["today"].isoformat())
        except Exception as exc:
            state["items"] = []
            status_text.value = f"Unable to load the list: {exc}"
        render_list()
        search_section.visible = editable()
        if update:
            page.update()

    def change_day(days):
        state["date"] = state["date"] + timedelta(days=days)
        results_column.controls = []
        load()

    def go_today(_=None):
        state["date"] = state["today"]
        results_column.controls = []
        load()

    def add(document):
        try:
            api("POST", "/todays-documents", json={"scheduled_for": state["date"].isoformat(), "document_id": document["id"], "note": note_field.value or None})
            note_field.value = ""
            load()
        except Exception as exc:
            show_error(f"Unable to add: {exc}")

    def remove(entry):
        try:
            api("DELETE", f"/todays-documents/{entry['id']}")
            load()
        except Exception as exc:
            show_error(f"Unable to remove: {exc}")

    def move(index, delta):
        ids = [entry["id"] for entry in state["items"]]
        ids[index], ids[index + delta] = ids[index + delta], ids[index]
        try:
            payload = api("PUT", "/todays-documents/order", json={"scheduled_for": state["date"].isoformat(), "entry_ids": ids})
            state["items"] = payload.get("items", [])
            render_list()
            page.update()
        except Exception as exc:
            show_error(f"Unable to reorder: {exc}")

    def search(_=None):
        query = (search_field.value or "").strip()
        if not query:
            results_column.controls = []
            page.update()
            return
        try:
            payload = api("GET", "/documents", params={"search": query, "archived": "false", "page_size": 10})
        except Exception as exc:
            show_error(f"Search failed: {exc}")
            return
        already_set = {entry["document"]["id"] for entry in state["items"]}
        rows = []
        for document in payload.get("items", []):
            is_set = document["id"] in already_set
            rows.append(ft.Row([
                ft.Column([
                    ft.Text(document.get("title") or "Untitled", size=12, weight=ft.FontWeight.W_600),
                    ft.Text(document_label(document), size=11, color=ft.Colors.BLUE_GREY_600),
                ], spacing=1, expand=True),
                ft.Text("Already set", size=11, color=ft.Colors.GREEN_700) if is_set else ft.OutlinedButton("Add", icon=ft.Icons.ADD, on_click=lambda _, d=document: add(d)),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        results_column.controls = rows or [ft.Text("No matching documents.", size=12, color=ft.Colors.BLUE_GREY_500)]
        page.update()

    search_field.on_submit = search
    search_section = ft.Column([
        ft.Text("Add a document", size=14, weight=ft.FontWeight.BOLD),
        ft.Row([search_field, ft.FilledButton("Search", icon=ft.Icons.SEARCH, on_click=search)], spacing=8),
        note_field,
        results_column,
    ], spacing=8)

    date_bar = ft.Row([
        ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Previous day", on_click=lambda _: change_day(-1)),
        ft.Column([date_text, date_hint], spacing=1),
        ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Next day", on_click=lambda _: change_day(1)),
        ft.TextButton("Today", icon=ft.Icons.TODAY, on_click=go_today),
    ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

    load(update=False)
    return ft.Column([
        section_header("Documents for SB Members", "Set the documents SB Members need for the day. They appear right away in the SB Member app.", ft.Icons.EVENT_NOTE_OUTLINED, ft.Colors.BLUE_700),
        surface_card(ft.Column([date_bar, status_text, list_column], spacing=10)),
        surface_card(search_section),
    ], spacing=16)
