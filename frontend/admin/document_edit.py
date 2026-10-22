"""Edit document: change a document's details. Offices change only by passing the document."""

import flet as ft

from frontend.admin.definition_fields import CategoryField, DocumentTypeField
from frontend.admin.registration import ACTIONS_REQUIRED, PRIORITIES, STATUSES, error_detail
from frontend.admin.tracking_ui import DUE_DATE_HINT, TrackingWidgets, parse_due_date

def _text(value):
    return "" if value in (None, "-") else str(value).strip()


def _choices(options, current):
    """`options`, plus the document's current value when it is not one of them, so saving keeps it."""
    current = _text(current)
    return [*options, current] if current and current not in options else list(options)


def open_edit_document_dialog(page, dialog, api, document, *, on_saved=None):
    """Fill `dialog` with the edit form for `document` and open it.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    """
    ui = TrackingWidgets(page)
    title = ft.TextField(label="Title", value=_text(document.get("title")))
    number = ft.TextField(label="Document Number", value=_text(document.get("document_number")), width=220)
    year = ft.TextField(label="Series Year", value=_text(document.get("series_year")), width=140)
    description = ft.TextField(label="Description", value=_text(document.get("description")), multiline=True, min_lines=2, max_lines=3)
    priority = ft.Dropdown(label="Priority", width=180, options=[ft.dropdown.Option(p) for p in PRIORITIES], value=document.get("priority") or "Medium")
    assigned_to = ft.TextField(label="Referred To", value=_text(document.get("assigned_to")), width=280)
    status = ft.Dropdown(label="Status", width=180, options=[ft.dropdown.Option(s) for s in _choices(STATUSES, document.get("status"))],
                         value=_text(document.get("status")) or "Approved")
    action_required = ft.Dropdown(label="Action Required", width=180, options=[ft.dropdown.Option(a) for a in _choices(ACTIONS_REQUIRED, document.get("action_required"))],
                                  value=_text(document.get("action_required")) or None)
    author = ft.TextField(label="Author", value=_text(document.get("author")), width=280)
    due_date = ft.TextField(label="Due date", hint_text="YYYY-MM-DD (optional)", value=_text(document.get("due_date")), width=180)
    remarks = ft.TextField(label="Remarks", value=_text(document.get("remarks")), multiline=True, min_lines=2, max_lines=3)
    message = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)

    try:
        reference = api("GET", "/documents/edit-options")
    except Exception:
        reference = {}
    # Document details passes its display record, where a missing value is "-".
    document_type = DocumentTypeField(label="Document Type", width=280, value=_text(document.get("document_type")),
                                      used_before=reference.get("other_document_types") or [])
    category = CategoryField(label="Category", width=280, value=_text(document.get("category")),
                             used_before=reference.get("categories") or [])

    def close():
        dialog.open = False
        page.update()

    def show_error(text):
        message.value = text
        message.visible = True
        page.update()

    def save():
        if not (title.value or "").strip():
            show_error("Title is required.")
            return
        if document_type.problem(required=False):
            show_error(document_type.problem(required=False))
            return
        due = (due_date.value or "").strip()
        if due and parse_due_date(due) is None:
            show_error(DUE_DATE_HINT)
            return
        payload = {
            "title": title.value.strip(),
            "document_number": (number.value or "").strip() or None,
            "series_year": (year.value or "").strip() or None,
            "description": (description.value or "").strip() or None,
            "category": category.value,
            "document_type": document_type.value,
            "priority": priority.value or "Medium",
            "due_date": due or None,
            "assigned_to": (assigned_to.value or "").strip() or None,
            "status": status.value or "Approved",
            "action_required": action_required.value or None,
            "author": (author.value or "").strip() or None,
            "remarks": (remarks.value or "").strip() or None,
        }
        try:
            api("PUT", f"/documents/{document['id']}", json=payload)
        except Exception as exc:
            show_error(error_detail(exc)[0])
            return
        close()
        if on_saved:
            on_saved()

    office = document.get("current_office") or "no office"
    dialog.modal = True
    dialog.title = ft.Text(f"Edit {document.get('tracking_number') or 'document'}")
    dialog.content = ft.Column(
        [
            ui.hint(f"Currently in {office}. To move it to another office, use Pass."),
            title,
            ft.Row([number, year, priority, due_date], spacing=12, wrap=True),
            description,
            ft.Row([document_type.control(), category.control()], spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Row([status, action_required], spacing=12, wrap=True),
            ft.Row([assigned_to, author], spacing=12, wrap=True),
            remarks,
            message,
        ],
        spacing=10,
        tight=True,
        scroll=ft.ScrollMode.AUTO,
        width=620,
    )
    dialog.actions = [
        ft.TextButton("Cancel", on_click=lambda _: close()),
        ft.Button("Save changes", icon=ft.Icons.SAVE_OUTLINED, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda _: save()),
    ]
    dialog.actions_alignment = ft.MainAxisAlignment.END
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()
