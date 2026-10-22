"""Announcements: edit what the public homepage shows under Announcements.

Super Administrators only; the backend stores the list as the homepage_announcements system setting.
"""

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets

MAX_ANNOUNCEMENTS = 10  # the backend enforces the same limit


def build_announcements_view(page, surface_card, api):
    """`api(method, path, **kwargs)` returns parsed JSON or raises with the backend's detail."""
    ui = TrackingWidgets(page)
    message = ft.Text("", size=12, visible=False)
    entries = []  # one dict of TextFields per announcement
    rows = ft.Column(spacing=16)
    add_button = ft.OutlinedButton(
        "Add announcement", icon=ft.Icons.ADD, on_click=lambda _: add(), height=44,
        style=ft.ButtonStyle(shape=ft.StadiumBorder(), color=ui.accent(), side=ft.BorderSide(1, ui.accent()), padding=ft.Padding(18, 0, 18, 0)),
    )
    save_button = ft.ElevatedButton(
        "Save announcements", icon=ft.Icons.SAVE, on_click=lambda _: save(), height=44,
        style=ft.ButtonStyle(shape=ft.StadiumBorder(), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, padding=ft.Padding(18, 0, 18, 0)),
    )
    style = {
        "text_size": 14, "border_radius": 10, "border_color": ui.line_color(), "focused_border_color": ui.accent(),
        "filled": True, "bgcolor": ui.card_color(),
    }

    def fields_for(item):
        third = {"xs": 12, "md": 4}
        return {
            "category": ft.TextField(label="Category", hint_text="e.g. Public notice", value=item.get("category") or "", max_length=40, col=third, **style),
            "title": ft.TextField(label="Title", value=item.get("title") or "", max_length=120, col=third, **style),
            "date": ft.TextField(label="Date", hint_text="e.g. Oct 27, 2026", value=item.get("date") or "", max_length=40, col=third, **style),
            "details": ft.TextField(label="Details (optional)", value=item.get("details") or "",
                                    multiline=True, min_lines=2, max_lines=4, max_length=300, **style),
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
            header = ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Text(str(index + 1), size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        width=28, height=28, border_radius=14, alignment=ft.Alignment(0, 0), bgcolor=ft.Colors.BLUE_700,
                    ),
                    ft.Text(f"Announcement {index + 1}", size=14, weight=ft.FontWeight.BOLD, color=ui.link_color(), expand=True),
                    ft.IconButton(icon=ft.Icons.ARROW_UPWARD, tooltip="Move up", icon_color=ui.accent(), disabled=index == 0,
                                  on_click=lambda _, i=index: move(i, -1)),
                    ft.IconButton(icon=ft.Icons.ARROW_DOWNWARD, tooltip="Move down", icon_color=ui.accent(), disabled=index == len(entries) - 1,
                                  on_click=lambda _, i=index: move(i, 1)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="Remove", icon_color=ft.Colors.RED_600,
                                  on_click=lambda _, i=index: remove(i)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(14, 4, 8, 4),
                bgcolor=ui.tone("#E8F1FD", "#1E2B38"),
            )
            body = ft.Container(
                content=ft.Column([
                    ft.ResponsiveRow([fields["category"], fields["title"], fields["date"]], spacing=14, run_spacing=4),
                    fields["details"],
                ], spacing=4),
                padding=ft.Padding(14, 16, 14, 6),
            )
            rows.controls.append(ft.Container(
                content=ft.Column([header, body], spacing=0),
                bgcolor=ui.tone("#F7FAFE", "#1B2430"),
                border=ft.border.all(1, ui.line_color()),
                border_radius=12,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            ))
        if not entries:
            rows.controls.append(ui.empty_box("No announcements. The homepage will say there are none right now."))
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
        ui.banner("Announcements", f"What the public homepage shows under Announcements, in this order (up to {MAX_ANNOUNCEMENTS}).", ft.Icons.CAMPAIGN),
        surface_card(ft.Column([
            ui.card_title("Homepage announcements", ft.Icons.CAMPAIGN_OUTLINED, subtitle="Shown on the public homepage from top to bottom. Save to publish your changes."),
            rows,
            message,
            ft.Row([add_button, save_button], alignment=ft.MainAxisAlignment.END, spacing=12),
        ], spacing=18), padding=20),
    ], spacing=16)
