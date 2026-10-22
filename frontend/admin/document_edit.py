"""Edit document: change a document's details. Offices change only by passing the document."""

import flet as ft

from frontend.admin.registration import PRIORITIES, error_detail
from frontend.admin.tracking_ui import DUE_DATE_HINT, TrackingWidgets, parse_due_date

NO_CATEGORY = "No category"
NO_TYPE = "No document type"


def _choices(dropdown, none_label, names, current):
    """Fill `dropdown` with `names`, keeping the document's `current` value even if it was retired since."""
    names = list(names)
    if current and current not in names:
        names.append(current)
    dropdown.options = [ft.dropdown.Option(none_label)] + [ft.dropdown.Option(name) for name in names]
    dropdown.value = current or none_label


def _text(value):
    return "" if value in (None, "-") else str(value).strip()


def open_edit_document_dialog(page, dialog, api, document, *, on_saved=None):
    """Fill `dialog` with the edit form for `document` and open it.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    """
    ui = TrackingWidgets(page)
    title = ft.TextField(label="Title", value=_text(document.get("title")))
    number = ft.TextField(label="Document Number", value=_text(document.get("document_number")), width=220)
    year = ft.TextField(label="Series Year", value=_text(document.get("series_year")), width=140)
    description = ft.TextField(label="Description", value=_text(document.get("description")), multiline=True, min_lines=2, max_lines=3)
    category = ft.Dropdown(label="Category", width=280)
    document_type = ft.Dropdown(label="Document Type", width=280)
    priority = ft.Dropdown(label="Priority", width=180, options=[ft.dropdown.Option(p) for p in PRIORITIES], value=document.get("priority") or "Medium")
    assigned_to = ft.TextField(label="Assigned To", value=_text(document.get("assigned_to")), width=280)
    author = ft.TextField(label="Author", value=_text(document.get("author")), width=280)
    due_date = ft.TextField(label="Due date", hint_text="YYYY-MM-DD (optional)", value=_text(document.get("due_date")), width=180)
    remarks = ft.TextField(label="Remarks", value=_text(document.get("remarks")), multiline=True, min_lines=2, max_lines=3)
    message = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)

    try:
        reference = api("GET", "/documents/edit-options")
    except Exception:
        reference = {}
    # Document details passes its display record, where a missing value is "-".
    _choices(category, NO_CATEGORY, reference.get("categories") or [], _text(document.get("category")) or None)
    _choices(document_type, NO_TYPE, reference.get("document_types") or [], _text(document.get("document_type")) or None)

    def close():
        dialog.open = False
        page.update()

    def show_error(text):
        message.value = text
        message.visible = True
        page.update()

    def chosen(dropdown, none_label):
        value = (dropdown.value or "").strip()
        return None if not value or value == none_label else value

    def save():
        if not (title.value or "").strip():
            show_error("Title is required.")
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
            "category": chosen(category, NO_CATEGORY),
            "document_type": chosen(document_type, NO_TYPE),
            "priority": priority.value or "Medium",
            "due_date": due or None,
            "assigned_to": (assigned_to.value or "").strip() or None,
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
            ft.Row([category, document_type], spacing=12, wrap=True),
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
