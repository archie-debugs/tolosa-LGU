"""Documents due for deletion: one dialog to delete each now or keep it longer.

It opens on its own after sign-in when an archived document's retention period has ended, from a
retention notification, and from an archived document's menu.
"""

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets

# How much longer "Extend" can keep a document, in months.
EXTEND_CHOICES = {1: "1 month", 3: "3 months", 6: "6 months", 12: "1 year", 24: "2 years", 60: "5 years", 120: "10 years"}
DEFAULT_EXTEND_MONTHS = 6
RETENTION_KINDS = {"retention_due", "retention_soon"}


def due_for_deletion(notifications):
    """The priority retention items of a GET /notifications body: documents past their retention."""
    return [item for item in (notifications or {}).get("items") or [] if item.get("kind") == "retention_due"]


ENDED = "Their retention period has ended. Delete each one now, or keep it longer."


def open_retention_dialog(page, api, items, on_changed=None, title="Documents due for deletion", intro=ENDED):
    """Ask what to do with each of `items` ({document_id, tracking_number, title, message}).

    `api(method, path, **kwargs)` returns parsed JSON or raises with the backend's detail.
    `on_changed()` runs after a document is deleted or extended.
    """
    if not items:
        return None
    ui = TrackingWidgets(page)
    remaining = list(items)
    rows = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, tight=True)
    dialog = ft.AlertDialog(modal=True)

    def close(_=None):
        dialog.open = False
        page.update()

    def done(item):
        remaining.remove(item)
        if on_changed:
            on_changed()
        if remaining:
            render()
        else:
            close()

    def act(item, status, call, success):
        try:
            call()
        except Exception as exc:
            status.value, status.color = f"{exc}", ft.Colors.RED_700
            status.visible = True
            page.update()
            return
        done(item)
        page.snack_bar = ft.SnackBar(ft.Text(success), open=True)
        page.update()

    def row(item):
        name = item.get("tracking_number") or "This document"
        status = ft.Text("", size=12, visible=False)
        extend_by = ft.Dropdown(
            value=str(DEFAULT_EXTEND_MONTHS), width=140, dense=True, text_size=13,
            options=[ft.dropdown.Option(key=str(months), text=text) for months, text in EXTEND_CHOICES.items()],
        )
        actions = ft.Row(spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        def delete(_):
            act(item, status, lambda: api("DELETE", f"/documents/{item['document_id']}/permanent"), f"Permanently deleted {name}.")

        def extend(_):
            months = int(extend_by.value or DEFAULT_EXTEND_MONTHS)
            act(item, status, lambda: api("POST", f"/documents/{item['document_id']}/retention/extend", json={"months": months}),
                f"{name} is kept {EXTEND_CHOICES.get(months, f'{months} months')} longer.")

        def choose(_=None, update=True):
            actions.controls = [
                ft.FilledButton("Delete now", icon=ft.Icons.DELETE_FOREVER_OUTLINED, style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE),
                                on_click=lambda _: confirm_delete()),
                ft.Text("or keep it", size=12, color=ui.muted_color()),
                extend_by,
                ft.OutlinedButton("Extend", icon=ft.Icons.MORE_TIME, on_click=extend),
            ]
            if update:
                page.update()

        def confirm_delete():
            actions.controls = [
                ft.Text("Its record, file and tracking history are deleted. This cannot be undone.", size=12, color=ft.Colors.RED_700),
                ft.TextButton("Cancel", on_click=choose),
                ft.FilledButton("Delete permanently", style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE), on_click=delete),
            ]
            page.update()

        choose(update=False)
        edge = ft.BorderSide(1, ft.Colors.with_opacity(0.5, ft.Colors.RED_700))
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(name, size=13, weight=ft.FontWeight.BOLD, color=ui.link_color()),
                    ft.Text(item.get("title") or "", size=13, color=ui.heading_color(), expand=True, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS, tooltip=item.get("title")),
                ], spacing=8),
                ft.Text(item.get("message") or "", size=12, color=ui.body_color()),
                actions,
                status,
            ], spacing=6, tight=True),
            padding=ft.Padding(12, 10, 12, 10),
            border=ft.Border(left=edge, top=edge, right=edge, bottom=edge),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.RED_700),
        )

    def render():
        rows.controls = [row(item) for item in remaining]
        dialog.title = ft.Row([
            ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.RED_700),
            ft.Text(f"{title} ({len(remaining)})" if len(remaining) > 1 else title, expand=True),
        ], spacing=10)
        page.update()

    dialog.content = ft.Container(
        ft.Column([
            ft.Text(intro, size=13, color=ui.body_color()),
            rows,
        ], spacing=12, tight=True),
        width=620,
    )
    dialog.actions = [ft.TextButton("Decide later", on_click=close)]
    page.overlay.append(dialog)
    render()
    dialog.open = True
    page.update()
    return dialog
