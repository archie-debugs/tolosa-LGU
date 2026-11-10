"""Edit document: change a document's details. Offices change only by passing the document.

The document number, category, priority and due date are not edited here (the client's request);
the form leaves them out of what it saves, so the backend keeps their current values.

The same form attaches the file to a document registered without one: as in registration, the
title comes from the file's name, and the other fields keep what the document already has.
"""

import flet as ft

from frontend.admin.definition_fields import DocumentTypeField
from frontend.admin.registration import (
    ACTIONS_REQUIRED, SHORTENED_NAME_NOTE, STATUSES, _Notice, _dialog_width, _field_style, _labelled, _primary_button,
    _section, _style_dialog, error_detail, is_shortened_name, set_label, title_from_filename, upload_finished,
)
from frontend.admin.tracking_ui import TrackingWidgets, remark_list

def _text(value):
    return "" if value in (None, "-") else str(value).strip()


def _choices(options, current):
    """`options`, plus the document's current value when it is not one of them, so saving keeps it."""
    current = _text(current)
    return [*options, current] if current and current not in options else list(options)


def _remark_history(api, document):
    """The document's remarks, newest first; a table row or details record may not carry them."""
    history = document.get("remark_history")
    if history is None and document.get("id"):
        try:
            history = (api("GET", f"/documents/{document['id']}") or {}).get("remark_history")
        except Exception:
            history = None
    if history is None and _text(document.get("remarks")):
        history = [{"text": _text(document.get("remarks"))}]
    return list(history or [])


def open_edit_document_dialog(page, dialog, api, document, *, on_saved=None, files=None):
    """Fill `dialog` with the edit form for `document` and open it.

    `api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail.
    With `files` (a registration.PickerFiles) the form attaches a file to the document too.
    """
    attaching = files is not None
    ui = TrackingWidgets(page)
    style = _field_style(ui)
    # `data` names each field, since its name is drawn above it rather than as its label.
    title = ft.TextField(data="Title", hint_text="Title of the document", value=_text(document.get("title")), **style)
    year = ft.TextField(data="Series Year", hint_text="e.g. 2026", value=_text(document.get("series_year")), **style)
    description = ft.TextField(data="Description", hint_text="What the document is about (optional)", value=_text(document.get("description")),
                               multiline=True, min_lines=2, max_lines=3, **style)
    assigned_to = ft.TextField(data="Referred To", hint_text="e.g. SB Secretary, Vice Mayor…", value=_text(document.get("assigned_to")), **style)
    status = ft.Dropdown(data="Status", options=[ft.dropdown.Option(s) for s in _choices(STATUSES, document.get("status"))],
                         value=_text(document.get("status")) or "Approved", **style)
    action_required = ft.Dropdown(data="Action Required", options=[ft.dropdown.Option(a) for a in _choices(ACTIONS_REQUIRED, document.get("action_required"))],
                                  value=_text(document.get("action_required")) or None, **style)
    author = ft.TextField(data="Author", hint_text="Enter author name...", value=_text(document.get("author")), **style)
    # Earlier remarks are kept and shown; whatever is typed here is added as a new one.
    new_remark = ft.TextField(data="New remark", hint_text="Leave empty to keep the remarks as they are",
                              multiline=True, min_lines=2, max_lines=3, **style)
    message = _Notice()
    # "tmp_name": the chosen file once uploaded, reused if saving fails: a browser sends a picked file only once.
    state = {"file": None, "busy": False, "tmp_name": None}
    file_name = ft.Text("No file chosen", size=13, weight=ft.FontWeight.W_600, color=ui.heading_color())
    file_hint = ft.Text("", size=11, color=ui.muted_color())
    progress = ft.ProgressBar(value=0, visible=False)

    remarks = _remark_history(api, document)
    # Document details passes its display record, where a missing value is "-".
    document_type = DocumentTypeField(style, value=_text(document.get("document_type")))

    def close():
        dialog.open = False
        page.update()

    def show_error(text):
        message.value = text
        page.update()
        if text:
            try:
                content.scroll_to(offset=-1, duration=300)  # the message is at the bottom of a long form
            except Exception:
                pass  # not drawn on a page (tests)

    def picked(chosen):
        state["file"] = chosen[0] if chosen else None
        state["tmp_name"] = None
        name = state["file"]["name"] if state["file"] else ""
        file_name.value = name or "No file chosen"
        file_hint.value = SHORTENED_NAME_NOTE if is_shortened_name(name) else ""
        if title_from_filename(name):
            title.value = title_from_filename(name)
        show_error("")

    def set_busy(busy, label=None):
        state["busy"] = busy
        progress.visible = busy
        save_button.disabled = busy
        set_label(save_button, label or action)
        page.update()

    def fail(text):
        set_busy(False)
        show_error(text)

    def save():
        if state["busy"]:
            return
        if not (title.value or "").strip():
            show_error("Title is required.")
            return
        if attaching and not state["file"]:
            show_error("Choose the file to attach.")
            return
        if attaching:
            upload()
        else:
            store()

    def upload():
        """Send the file to a temporary upload first; the web app never holds its bytes."""
        chosen = state["file"]
        if state["tmp_name"]:
            set_busy(True, "Saving…")
            store(state["tmp_name"])
            return
        set_busy(True, "Uploading…")
        try:
            created = api("POST", "/documents/uploads/create_tmp_uploads", json={"files": [{"filename": chosen["name"], "size": chosen["size"]}]})
        except Exception as exc:
            fail(f"The file could not be prepared for upload: {error_detail(exc)[0]}")
            return
        item = next(iter(created.get("files") or []), {})
        if not item.get("ok"):
            fail("Only PDF, DOC and DOCX files can be attached.")
            return

        def on_progress(name, value, error):
            if name != chosen["name"] or not state["busy"]:
                return
            if error:
                fail(f"The upload failed: {error}")
            elif upload_finished(value):
                state["tmp_name"] = item["tmp_name"]
                store(item["tmp_name"])
            else:
                progress.value = value
                page.update()

        progress.value = 0
        page.update()
        files.upload([(chosen["name"], item["upload_url"])], on_progress)

    def store(tmp_name=None):
        payload = {
            "title": title.value.strip(),
            "series_year": (year.value or "").strip() or None,
            "description": (description.value or "").strip() or None,
            "document_type": document_type.value,
            "assigned_to": (assigned_to.value or "").strip() or None,
            "status": status.value or "Approved",
            "action_required": action_required.value or None,
            "author": (author.value or "").strip() or None,
            "new_remark": (new_remark.value or "").strip() or None,
        }
        try:
            # The details first: if attaching then fails (say the file is a copy), saving again is safe.
            api("PUT", f"/documents/{document['id']}", json=payload)
            if tmp_name:
                api("POST", f"/documents/{document['id']}/attachments", data={"tmp_name": tmp_name})
        except Exception as exc:
            fail(error_detail(exc)[0])
            return
        state["busy"] = False
        close()
        if on_saved:
            on_saved()

    office = document.get("current_office") or "no office"
    half = {"xs": 12, "sm": 6}
    narrow = (page.width or 1024) <= 600
    action = "Attach File" if attaching else "Save changes"
    save_button = _primary_button(action, ft.Icons.UPLOAD_FILE if attaching else ft.Icons.SAVE_OUTLINED, lambda _: save())
    file_section = [_section(ui, ft.Icons.UPLOAD_FILE, "The file", [
        ft.Row([
            ft.Column([file_name, file_hint], spacing=2, expand=True),
            ft.OutlinedButton("Choose file", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=lambda _: files.pick(False, picked)),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Text("PDF, DOC or DOCX. Choosing it fills the title from its name; check the details below.", size=11, color=ui.muted_color()),
        progress,
    ])] if attaching else []
    content = ft.Column(
        [
            *file_section,
            _section(ui, ft.Icons.DESCRIPTION, "The document", [
                _labelled(ui, title, "Title", ft.Icons.TITLE, required=True),
                ft.ResponsiveRow([
                    _labelled(ui, year, "Series year", ft.Icons.CALENDAR_TODAY_OUTLINED, col=half),
                    _labelled(ui, document_type.control(), "Document type", ft.Icons.DESCRIPTION_OUTLINED, col=half),
                ], spacing=14, run_spacing=12),
                _labelled(ui, description, "Description", ft.Icons.NOTES),
            ]),
            _section(ui, ft.Icons.TASK_ALT, "Status", [
                ft.ResponsiveRow([
                    _labelled(ui, status, "Status", ft.Icons.FLAG_OUTLINED, col=half),
                    _labelled(ui, action_required, "Action required", ft.Icons.TASK_ALT, col=half),
                    _labelled(ui, assigned_to, "Referred to", ft.Icons.PERSON, col=half),
                    _labelled(ui, author, "Author", ft.Icons.PERSON_OUTLINE, col=half),
                ], spacing=14, run_spacing=12),
                ft.Row(
                    [ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ui.muted_color()),
                     ft.Text(f"Currently in {office}. To move it to another office, use Pass.", size=11, color=ui.muted_color(), expand=True)],
                    spacing=8,
                ),
            ]),
            _section(ui, ft.Icons.COMMENT_OUTLINED, "Remarks", [
                *([remark_list(ui, remarks)] if remarks else [ui.hint("No remarks yet.")]),
                _labelled(ui, new_remark, "New remark", ft.Icons.ADD_COMMENT_OUTLINED),
            ]),
            message.box,
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        height=min(560, (page.height or 760) - 200) if narrow else 560,
    )
    _style_dialog(
        dialog, ui, "Attach File" if attaching else "Edit Document", content,
        [ft.TextButton("Cancel", on_click=lambda _: close()), save_button],
        _dialog_width(page, False),
        subtitle=f"{document.get('tracking_number') or 'Document'} · " + ("add its file and check its details." if attaching else "update its details."),
        icon=ft.Icons.UPLOAD_FILE if attaching else ft.Icons.EDIT_DOCUMENT, on_close=close,
    )
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()
