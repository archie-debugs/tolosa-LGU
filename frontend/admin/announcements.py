"""Announcements: edit what the public homepage shows under Announcements.

Super Administrators only; the backend stores the list as the homepage_announcements system setting.
"""

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets

MAX_ANNOUNCEMENTS = 10  # the backend enforces the same limit


def build_announcements_view(page, surface_card, section_header, api):
    """`api(method, path, **kwargs)` returns parsed JSON or raises with the backend's detail."""
    ui = TrackingWidgets(page)
    message = ft.Text("", size=12, visible=False)
    entries = []  # one dict of TextFields per announcement
    rows = ft.Column(spacing=16)
    add_button = ft.OutlinedButton("Add announcement", icon=ft.Icons.ADD, on_click=lambda _: add())
    save_button = ft.ElevatedButton("Save announcements", icon=ft.Icons.SAVE_OUTLINED, on_click=lambda _: save())

    def fields_for(item):
        return {
            "category": ft.TextField(label="Category", hint_text="e.g. Public notice", value=item.get("category") or "", width=200, max_length=40),
            "title": ft.TextField(label="Title", value=item.get("title") or "", width=360, max_length=120),
            "date": ft.TextField(label="Date", hint_text="e.g. Oct 27, 2026", value=item.get("date") or "", width=180, max_length=40),
            "details": ft.TextField(label="Details (optional)", value=item.get("details") or "", width=560,
                                    multiline=True, min_lines=1, max_lines=3, max_length=300),
        }

    try:
        stored = (api("GET", "/system-settings").get("settings") or {}).get("homepage_announcements") or []
        entries.extend(fields_for(item) for item in stored if isinstance(item, dict))
    except Exception as exc:
        # Saving now would replace the real announcements with an empty list.
        message.value, message.color, message.visible = f"Unable to load announcements: {exc}", ft.Colors.RED_700, True
        add_button.disabled = save_button.disabled = True

    def render():
        rows.controls = []
        for index, fields in enumerate(entries):
            rows.controls.append(ft.Column([
                ft.Row([
                    ft.Text(f"Announcement {index + 1}", size=13, weight=ft.FontWeight.W_600, color=ui.heading_color()),
                    ft.IconButton(icon=ft.Icons.ARROW_UPWARD, tooltip="Move up", disabled=index == 0,
                                  on_click=lambda _, i=index: move(i, -1)),
                    ft.IconButton(icon=ft.Icons.ARROW_DOWNWARD, tooltip="Move down", disabled=index == len(entries) - 1,
                                  on_click=lambda _, i=index: move(i, 1)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="Remove", icon_color=ft.Colors.RED_700,
                                  on_click=lambda _, i=index: remove(i)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([fields["category"], fields["title"], fields["date"]], wrap=True, spacing=12),
                fields["details"],
            ], spacing=8))
        if not entries:
            rows.controls.append(ui.hint("No announcements. The homepage will say there are none right now."))
        if not save_button.disabled:
            add_button.disabled = len(entries) >= MAX_ANNOUNCEMENTS

    def refresh():
        message.visible = False
        render()
        page.update()

    def add():
        entries.append(fields_for({}))
        refresh()

    def remove(index):
        entries.pop(index)
        refresh()

    def move(index, step):
        entries[index], entries[index + step] = entries[index + step], entries[index]
        refresh()

    def save():
        announcements = [{key: (field.value or "").strip() for key, field in fields.items()} for fields in entries]
        missing = [str(number) for number, item in enumerate(announcements, start=1) if not item["title"]]
        if missing:
            message.value, message.color = f"Add a title to announcement {', '.join(missing)}.", ft.Colors.RED_700
        else:
            try:
                api("PUT", "/system-settings", json={"settings": {"homepage_announcements": announcements}})
                message.value, message.color = "Announcements saved. The homepage shows them the next time it opens.", ft.Colors.GREEN_700
            except Exception as exc:
                message.value, message.color = f"Unable to save announcements: {str(exc)[:180]}", ft.Colors.RED_700
        message.visible = True
        page.update()

    render()
    return ft.Column([
        surface_card(section_header("Announcements", f"What the public homepage shows under Announcements, in this order (up to {MAX_ANNOUNCEMENTS}).",
                                    ft.Icons.CAMPAIGN_OUTLINED, ft.Colors.BLUE_700), padding=18),
        surface_card(ft.Column([
            rows,
            message,
            ft.Row([add_button, save_button], alignment=ft.MainAxisAlignment.END, spacing=12),
        ], spacing=12), padding=18),
    ], spacing=16)
