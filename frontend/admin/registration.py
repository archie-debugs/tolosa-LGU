"""Registration: add new documents into an office, one at a time or several files at once."""

import inspect
import os
from datetime import date, datetime

import flet as ft

from frontend.admin.todays_documents import picked_date
from frontend.admin.tracking_ui import DUE_DATE_HINT, TrackingWidgets, parse_due_date

ALLOWED_EXTENSIONS = ("pdf", "doc", "docx")
PRIORITIES = ("Low", "Medium", "High")
OLDEST_YEAR = 1900
NO_CATEGORY = "No category"

# Flet 0.28 labels a button with `text`; newer releases use `content`.
_BUTTON_CLASS = ft.Button if inspect.isclass(ft.Button) else (getattr(ft, "FilledButton", None) or ft.ElevatedButton)
BUTTON_TAKES_TEXT = "text" in inspect.signature(_BUTTON_CLASS.__init__).parameters


def set_label(button, text):
    if isinstance(button, ft.Container) and button.content is not None:
        button = button.content  # app.py's ft.Button stand-in wraps coloured buttons in a Container
    if BUTTON_TAKES_TEXT:
        button.text = text
    else:
        button.content = text


def on_dropdown_change(dropdown, handler):
    """Flet 0.28 calls a Dropdown's on_change; newer releases call on_select."""
    if hasattr(dropdown, "on_change"):
        dropdown.on_change = handler
    else:
        dropdown.on_select = handler


class PickerFiles:
    """Picks document files and uploads them, over a Flet FilePicker.

    `pick(multiple, on_picked)` calls `on_picked([{"name", "size"}, ...])`.
    `upload([(name, upload_url), ...], on_progress)` calls `on_progress(name, progress, error)`;
    a file is done when progress is None or reaches 1.0.
    """

    def __init__(self, page, picker):
        self.page = page
        self.picker = picker
        self.on_picked = None
        self.on_progress = None
        # Flet 0.28 reports picked files through on_result; newer releases return them from pick_files.
        if hasattr(picker, "on_result"):
            picker.on_result = lambda e: self._picked(getattr(e, "files", None))
        picker.on_upload = self._uploaded

    def _picked(self, files):
        if files and self.on_picked:
            self.on_picked([{"name": getattr(f, "name", "") or "", "size": getattr(f, "size", 0) or 0} for f in files])

    def _uploaded(self, e):
        if self.on_progress:
            self.on_progress(getattr(e, "file_name", None), getattr(e, "progress", None), getattr(e, "error", None))

    def _run(self, result, then=None):
        if inspect.isawaitable(result):
            async def wait():
                value = await result
                if then:
                    then(value)
            self.page.run_task(wait)
        elif then:
            then(result)

    def pick(self, multiple, on_picked):
        self.on_picked = on_picked
        result = self.picker.pick_files(
            allow_multiple=multiple, file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=list(ALLOWED_EXTENSIONS),
        )
        self._run(result, self._picked if result is not None else None)

    def upload(self, uploads, on_progress):
        self.on_progress = on_progress
        self._run(self.picker.upload([ft.FilePickerUploadFile(name, upload_url=url, method="PUT") for name, url in uploads]))


def upload_finished(progress):
    return progress is None or progress >= 1.0


def error_detail(exc):
    """(message, detail) from an api error; detail is the structured body when the backend sent one."""
    detail = exc.args[0] if exc.args else None
    if isinstance(detail, dict):
        return detail.get("message") or str(detail), detail
    return str(exc) or "Something went wrong.", None


def title_from_filename(name):
    stem = os.path.splitext(name or "")[0].replace("_", " ").replace("-", " ").strip()
    return " ".join(stem.split())


def number_label(document_type, number, year):
    parts = [document_type or "Document"]
    if number:
        parts.append(f"No. {number}")
    if year:
        parts.append(f"s. {year}")
    return " ".join(parts)


def _accent(widgets):
    return widgets.tone(ft.Colors.BLUE_700, ft.Colors.BLUE_300)


def _field_style(widgets):
    """Inputs show a placeholder inside and their name above (see _labelled)."""
    return {
        "dense": True,
        "text_size": 13,
        "border_radius": 8,
        "border_color": widgets.line_color(),
        "focused_border_color": _accent(widgets),
        "filled": True,
        "bgcolor": widgets.card_color(),
        "content_padding": ft.Padding(12, 12, 12, 12),
    }


def _labelled(widgets, control, text, icon, required=False, col=None):
    """`control` under its name; `col` places it in a ResponsiveRow."""
    caption = ft.Row(
        [
            ft.Icon(icon, size=15, color=_accent(widgets)),
            ft.Text(text + (" *" if required else ""), size=12, weight=ft.FontWeight.W_600, color=widgets.heading_color()),
        ],
        spacing=6,
    )
    return ft.Column([caption, control], spacing=6, col=col, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)


def _section(widgets, icon, title, controls):
    """A card with a tinted header strip, as each part of the registration form is drawn."""
    header = ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=18, color=_accent(widgets)),
                ft.Text(title.upper(), size=12, weight=ft.FontWeight.BOLD, color=_accent(widgets)),
            ],
            spacing=10,
        ),
        padding=ft.Padding(14, 10, 14, 10),
        bgcolor=widgets.tone("#E8F1FD", "#1E2B38"),
    )
    return ft.Container(
        content=ft.Column(
            [header, ft.Container(ft.Column(controls, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH), padding=ft.Padding(14, 12, 14, 14))],
            spacing=0,
        ),
        bgcolor=widgets.tone("#F7FAFE", "#1B2430"),
        border=ft.border.all(1, widgets.line_color()),
        border_radius=12,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )


def _pill_button(widgets, text, icon, on_click):
    return ft.OutlinedButton(
        text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            shape=ft.StadiumBorder(),
            bgcolor=widgets.tone("#E8F1FD", "#1E2B38"),
            color=_accent(widgets),
            side=ft.BorderSide(1, widgets.tone(ft.Colors.BLUE_200, ft.Colors.BLUE_GREY_600)),
            padding=ft.Padding(18, 12, 18, 12),
        ),
    )


def _upload_box(widgets, heading, hint, *buttons):
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED, size=40, color=_accent(widgets)),
                ft.Column([heading, hint], spacing=2, expand=True),
                *buttons,
            ],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(18, 16, 18, 16),
        bgcolor=widgets.card_color(),
        border=ft.border.all(1.5, widgets.tone(ft.Colors.BLUE_100, ft.Colors.BLUE_GREY_700)),
        border_radius=12,
    )


class _Notice:
    """A red message box, shown only while it has something to say. Set `value` like a Text's."""

    def __init__(self):
        self.text = ft.Text("", size=12, color=ft.Colors.RED_700, expand=True)
        self.box = ft.Container(
            content=ft.Row([ft.Icon(ft.Icons.ERROR, color=ft.Colors.RED_600, size=20), self.text], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(12, 10, 12, 10),
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.RED_600),
            border=ft.border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.RED_400)),
            border_radius=8,
            visible=False,
        )

    @property
    def value(self):
        return self.text.value

    @value.setter
    def value(self, text):
        self.text.value = text
        self.box.visible = bool(text)


def load_options(api):
    options = api("GET", "/documents/registration/options")
    return {
        "offices": options.get("offices") or [],
        "default_office_id": options.get("default_office_id"),
        "office_locked": bool(options.get("office_locked")),
        "categories": options.get("categories") or [],
        "document_types": options.get("document_types") or [],
    }


class _Form:
    """The fields both dialogs share: what the documents are and where they start."""

    def __init__(self, page, options, widgets):
        self.page = page
        self.options = options
        self.widgets = widgets
        style = _field_style(widgets)
        offices = options["offices"]
        default_office = options["default_office_id"] or (offices[0]["id"] if len(offices) == 1 else None)
        # `data` names each field, since its name is drawn above it rather than as its label.
        self.document_type = ft.Dropdown(
            data="Document type", hint_text="Document type", options=[ft.dropdown.Option(name) for name in options["document_types"]],
            value=options["document_types"][0] if options["document_types"] else None, **style,
        )
        self.category = ft.Dropdown(
            data="Category", options=[ft.dropdown.Option(NO_CATEGORY)] + [ft.dropdown.Option(name) for name in options["categories"]],
            value=NO_CATEGORY, **style,
        )
        self.office = ft.Dropdown(
            data="Office", hint_text="Office", options=[ft.dropdown.Option(str(office["id"]), office["name"]) for office in offices],
            value=str(default_office) if default_office is not None else None,
            disabled=options["office_locked"], **style,
        )
        self.priority = ft.Dropdown(data="Priority", options=[ft.dropdown.Option(name) for name in PRIORITIES], value="Medium", **style)
        self.due_date = ft.TextField(data="Due date", hint_text="YYYY-MM-DD", **{**style, "content_padding": ft.Padding(12, 12, 44, 12)})
        self.assigned_to = ft.TextField(data="Assigned to", hint_text="Select or enter assignee...", **style)
        self.author = ft.TextField(data="Author", hint_text="Enter author name...", **style)
        self.description = ft.TextField(data="Description", hint_text="What the document is about (optional)", multiline=True, min_lines=2, max_lines=3, **style)
        self.due_button = ft.IconButton(ft.Icons.CALENDAR_MONTH_OUTLINED, icon_size=18, icon_color=widgets.muted_color(), tooltip="Pick a date", on_click=lambda _: self.pick_due())

    def due_field(self):
        """The due date box with its calendar button inside it."""
        return ft.Stack([self.due_date, ft.Container(self.due_button, right=0, top=0, bottom=0, alignment=ft.Alignment(0, 0))])

    def pick_due(self):
        # One picker per page, kept in the overlay; it fills whichever form opened it last.
        picker = getattr(self.page, "_due_date_picker", None)
        if picker is None:
            picker = ft.DatePicker(first_date=datetime(2000, 1, 1), last_date=datetime(2100, 12, 31))
            self.page._due_date_picker = picker
            self.page.overlay.append(picker)
            self.page.update()
        picker.on_change = self._due_picked
        current = parse_due_date((self.due_date.value or "").strip())
        picker.value = datetime.combine(current, datetime.min.time()) if current else None
        if hasattr(picker, "pick_date"):
            picker.pick_date()
        else:
            self.page.open(picker)

    def _due_picked(self, e):
        day = picked_date(e.control.value)
        if day:
            self.due_date.value = day.isoformat()
            self.page.update()

    def due_problem(self):
        text = (self.due_date.value or "").strip()
        return DUE_DATE_HINT if text and parse_due_date(text) is None else None

    def office_name(self):
        return next((office["name"] for office in self.options["offices"] if str(office["id"]) == str(self.office.value)), None)

    def office_problem(self):
        if not self.options["offices"]:
            if self.options["office_locked"]:
                return "Your account is not assigned to an office. Ask the Super Admin to assign one before registering documents."
            return "There is no active office to register into. Add one in Offices first."
        if not self.office.value:
            return "Choose the office the document starts in."
        return None

    def shared_fields(self):
        return {
            "document_type": self.document_type.value or None,
            "category": self.category.value if self.category.value not in (None, "", NO_CATEGORY) else None,
            "office_id": int(self.office.value) if self.office.value else None,
            "priority": self.priority.value or "Medium",
            "due_date": (self.due_date.value or "").strip() or None,
            "assigned_to": (self.assigned_to.value or "").strip() or None,
            "author": (self.author.value or "").strip() or None,
            "description": (self.description.value or "").strip() or None,
        }

    def lock(self, locked):
        for control in (self.document_type, self.category, self.priority, self.due_date, self.due_button, self.assigned_to, self.author, self.description):
            control.disabled = locked
        self.office.disabled = locked or self.options["office_locked"]


def _dialog_width(page, wide):
    if (page.width or 1024) <= 600:
        return max(280, (page.width or 360) - 32)
    return 760 if wide else 680


def _style_dialog(dialog, widgets, title, content, actions, width, *, subtitle=None, icon=None, on_close=None):
    """`icon`, `subtitle` and `on_close` draw the form header: icon tile, title, subtitle and a close button."""
    dialog.modal = True
    dialog.bgcolor = widgets.card_color()
    dialog.shape = ft.RoundedRectangleBorder(radius=18)
    heading = ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=widgets.heading_color())
    if icon:
        heading = ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, color=ft.Colors.WHITE, size=28),
                    width=56, height=56, border_radius=14,
                    alignment=ft.Alignment(0, 0),
                    bgcolor=ft.Colors.BLUE_700,
                    border=ft.border.all(4, ft.Colors.with_opacity(0.15, ft.Colors.BLUE_700)),
                ),
                ft.Column(
                    [
                        ft.Text(title, size=22, weight=ft.FontWeight.BOLD, color=widgets.link_color()),
                        *([ft.Text(subtitle, size=13, color=widgets.muted_color())] if subtitle else []),
                    ],
                    spacing=2,
                    expand=True,
                ),
                *([ft.IconButton(ft.Icons.CLOSE, icon_color=widgets.muted_color(), tooltip="Close", on_click=lambda _: on_close())] if on_close else []),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    dialog.title = heading
    dialog.title_padding = ft.Padding(24, 20, 16, 8)
    dialog.content_padding = ft.Padding(24, 8, 24, 8)
    dialog.actions_padding = ft.Padding(24, 8, 24, 20)
    dialog.content = ft.Container(content=content, width=width)
    dialog.actions = actions
    dialog.actions_alignment = ft.MainAxisAlignment.END


def _download_labels(page, api, ids):
    url = api("POST", "/documents/qr/labels/download-token", json={"ids": ids}).get("download_url")
    if not url:
        raise Exception("The download link was not returned.")
    page.launch_url(url)


def _year_dropdown(this_year, width=130, value=None, widgets=None):
    """With `widgets`, styled for the form, where the name is drawn above it."""
    options = [ft.dropdown.Option(str(year)) for year in range(this_year, OLDEST_YEAR - 1, -1)]
    if widgets:
        return ft.Dropdown(data="Year", options=options, value=str(value or this_year), width=width, **_field_style(widgets))
    return ft.Dropdown(label="Year", options=options, value=str(value or this_year), width=width)


def open_register_dialog(page, dialog, api, files, *, on_registered=None, open_details=None, can_print_qr=False, today=None):
    """Register one document, with or without its file.

    `api(method, path, **kwargs)` calls the main backend and returns parsed JSON or raises with the
    backend's detail. `files` is a PickerFiles. `open_details(document)` opens the new document.
    """
    widgets = TrackingWidgets(page)
    this_year = (today or date.today()).year
    try:
        options = load_options(api)
    except Exception as exc:
        _show_problem(page, dialog, widgets, "Register document", f"The registration form could not be loaded: {error_detail(exc)[0]}")
        return
    form = _Form(page, options, widgets)
    state = {"file": None, "tmp_name": None, "busy": False, "allow_duplicate": False, "duplicate": None}

    style = _field_style(widgets)
    title = ft.TextField(data="Title", hint_text="Enter document title...", autofocus=True, **style)
    number = ft.TextField(data="Number", hint_text="Enter document number...", **style)
    year = _year_dropdown(this_year, width=None, widgets=widgets)
    file_name = ft.Text("", size=14, weight=ft.FontWeight.BOLD, color=widgets.heading_color(), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    file_hint = widgets.hint("")
    remove_file = ft.IconButton(ft.Icons.CLOSE, tooltip="Remove file", on_click=lambda _: set_file(None))
    choose_file = _pill_button(widgets, "Choose file", ft.Icons.ATTACH_FILE, lambda _: files.pick(False, picked))
    message = _Notice()
    progress = ft.ProgressBar(value=None, visible=False)
    duplicate_box = ft.Column(spacing=6, visible=False)
    register_button = ft.Button("Register", icon=ft.Icons.SAVE_OUTLINED, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda _: submit())
    cancel_button = ft.TextButton("Cancel", on_click=lambda _: close())

    def close():
        dialog.open = False
        files.on_progress = None
        page.update()

    def set_file(picked_file):
        state["file"] = picked_file
        state["tmp_name"] = None
        render_file()
        page.update()

    def picked(picked_files):
        set_file(picked_files[0])
        if not (title.value or "").strip():
            title.value = title_from_filename(picked_files[0]["name"])
            page.update()

    def render_file():
        chosen = state["file"]
        file_name.value = chosen["name"] if chosen else "No file chosen"
        file_hint.value = "" if chosen else "Without a file, only the record is registered."
        remove_file.visible = bool(chosen) and not state["busy"]
        choose_file.visible = not state["busy"]

    def set_busy(busy, label=None):
        state["busy"] = busy
        progress.visible = busy
        register_button.disabled = busy
        set_label(register_button, label or "Register")
        for control in (title, number, year):
            control.disabled = busy
        form.lock(busy)
        render_file()
        page.update()

    def fail(text):
        message.value = text
        set_busy(False)

    def show_duplicate(documents):
        state["duplicate"] = documents
        label = number_label(form.document_type.value, (number.value or "").strip(), year.value)
        duplicate_box.controls = [
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.AMBER_800, size=18),
                        ft.Text(f"{label} is already registered", size=13, weight=ft.FontWeight.BOLD, color=widgets.heading_color()),
                    ], spacing=6),
                    ft.Text(", ".join(documents), size=12, color=widgets.body_color()),
                    ft.Text("Check the number and year. If this really is a separate document, register it anyway.", size=12, color=widgets.body_color()),
                    ft.Row([
                        ft.TextButton("Change the number", on_click=lambda _: dismiss_duplicate()),
                        ft.OutlinedButton("Register anyway", on_click=lambda _: register_anyway()),
                    ], spacing=8, wrap=True),
                ], spacing=4),
                padding=12,
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.AMBER_700),
            )
        ]
        duplicate_box.visible = True
        message.value = ""
        set_busy(False)

    def dismiss_duplicate():
        duplicate_box.visible = False
        state["duplicate"] = None
        page.update()

    def register_anyway():
        state["allow_duplicate"] = True
        duplicate_box.visible = False
        submit()

    def fields():
        return {
            "title": (title.value or "").strip(),
            "document_number": (number.value or "").strip() or None,
            "series_year": int(year.value),
            **form.shared_fields(),
        }

    def submit():
        if state["busy"]:
            return
        message.value = ""
        if not (title.value or "").strip():
            message.value = "Enter the document's title."
            page.update()
            return
        problem = form.office_problem() or form.due_problem()
        if problem:
            message.value = problem
            page.update()
            return
        values = fields()
        if not state["allow_duplicate"] and values["document_number"]:
            try:
                found = api("GET", "/documents/registration/duplicates", params={
                    "document_type": values["document_type"] or "", "document_number": values["document_number"], "series_year": values["series_year"],
                }).get("documents") or []
            except Exception as exc:
                fail(error_detail(exc)[0])
                return
            if found:
                show_duplicate([item["tracking_number"] for item in found])
                return
        if state["file"]:
            upload_then_register(values)
        else:
            register_without_file(values)

    def register_without_file(values):
        set_busy(True, "Registering…")
        data = {key: str(value) for key, value in values.items() if value is not None}
        if state["allow_duplicate"]:
            data["allow_duplicate_number"] = "true"
        try:
            document = api("POST", "/documents/register", data=data)
        except Exception as exc:
            text, detail = error_detail(exc)
            if detail and detail.get("duplicate_number"):
                show_duplicate(detail.get("documents") or [])
            else:
                fail(text)
            return
        registered(document)

    def upload_then_register(values):
        if state["tmp_name"]:
            confirm(values)
            return
        set_busy(True, "Uploading…")
        chosen = state["file"]
        try:
            created = api("POST", "/documents/uploads/create_tmp_uploads", json={"files": [{"filename": chosen["name"], "size": chosen["size"]}]})
        except Exception as exc:
            fail(f"The file could not be prepared for upload: {error_detail(exc)[0]}")
            return
        item = next(iter(created.get("files") or []), {})
        if not item.get("ok"):
            reason = item.get("reason") or "The file was refused."
            fail("Only PDF, DOC and DOCX files can be registered." if reason == "Unsupported extension" else reason)
            return

        def on_progress(name, value, error):
            if name != chosen["name"] or not state["busy"]:
                return
            if error:
                fail(f"The upload failed: {error}")
                return
            if upload_finished(value):
                state["tmp_name"] = item["tmp_name"]
                confirm(values)
            else:
                progress.value = value
                set_label(register_button, f"Uploading {int(value * 100)}%")
                page.update()

        progress.value = 0
        files.upload([(chosen["name"], item["upload_url"])], on_progress)

    def confirm(values):
        set_busy(True, "Registering…")
        progress.value = None
        spec = {"tmp_name": state["tmp_name"], "series_year": values["series_year"], "title": values["title"], "document_number": values["document_number"]}
        shared = {key: value for key, value in values.items() if key not in spec and key != "title"}
        try:
            result = api("POST", "/documents/bulk-register/confirm_tmp", json={
                "tmp_names": [state["tmp_name"]], "documents": [spec], **shared, "allow_duplicate_number": state["allow_duplicate"],
            })
        except Exception as exc:
            fail(error_detail(exc)[0])
            return
        if result.get("documents"):
            registered(result["documents"][0])
            return
        error = next(iter(result.get("errors") or []), {})
        if error.get("duplicate_number"):
            show_duplicate(error.get("documents") or [])
        elif error.get("reason") == "Temporary file not found":
            state["tmp_name"] = None
            fail("The uploaded file expired. Press Register to upload it again.")
        else:
            fail(error.get("reason") or "The document was not registered.")

    def registered(document):
        set_busy(False)
        if on_registered:
            on_registered()
        tracking = document.get("tracking_number") or "-"
        actions = []
        if open_details and document.get("id"):
            actions.append(ft.OutlinedButton("View details", icon=ft.Icons.OPEN_IN_NEW, on_click=lambda _: (close(), open_details({"id": document["id"]}))))
        if can_print_qr and document.get("id"):
            actions.append(ft.OutlinedButton("QR label", icon=ft.Icons.QR_CODE_2, on_click=lambda _: labels([document["id"]])))
        done_message = ft.Text("", size=12, color=ft.Colors.RED_700)

        def labels(ids):
            try:
                _download_labels(page, api, ids)
            except Exception as exc:
                done_message.value = f"The QR label could not be downloaded: {error_detail(exc)[0]}"
                page.update()

        where = form.office_name()
        no_file = "" if state["file"] else " No file was attached."
        _style_dialog(dialog, widgets, "Document registered", ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_700, size=28),
                ft.Text(tracking, size=22, weight=ft.FontWeight.BOLD, color=widgets.heading_color(), selectable=True),
            ], spacing=10),
            ft.Text(document.get("title") or values_title(), size=14, color=widgets.body_color()),
            widgets.hint((f"Held by {where}." if where else "") + no_file),
            ft.Row(actions, spacing=8, wrap=True),
            done_message,
        ], spacing=10, tight=True), [
            ft.TextButton("Register another", on_click=lambda _: open_register_dialog(
                page, dialog, api, files, on_registered=on_registered, open_details=open_details, can_print_qr=can_print_qr, today=today)),
            ft.Button("Done", on_click=lambda _: close()),
        ], _dialog_width(page, False))
        page.update()

    def values_title():
        return (title.value or "").strip()

    render_file()
    narrow = (page.width or 1024) <= 600
    third = {"xs": 12, "sm": 4}
    half = {"xs": 12, "sm": 6}
    content = ft.Column([
        _section(widgets, ft.Icons.DESCRIPTION, "The document", [
            _labelled(widgets, title, "Title", ft.Icons.TITLE, required=True),
            ft.ResponsiveRow([
                _labelled(widgets, number, "Number", ft.Icons.TAG, required=True, col=third),
                _labelled(widgets, year, "Year", ft.Icons.CALENDAR_TODAY_OUTLINED, required=True, col=third),
                _labelled(widgets, form.document_type, "Document type", ft.Icons.DESCRIPTION_OUTLINED, required=True, col=third),
            ], spacing=14, run_spacing=12),
            ft.ResponsiveRow([
                _labelled(widgets, form.category, "Category", ft.Icons.LOCAL_OFFER_OUTLINED, required=True, col=third),
                _labelled(widgets, form.priority, "Priority", ft.Icons.FLAG_OUTLINED, required=True, col=third),
                _labelled(widgets, form.due_field(), "Due date", ft.Icons.EVENT_OUTLINED, col=third),
            ], spacing=14, run_spacing=12),
        ]),
        _section(widgets, ft.Icons.ACCOUNT_BALANCE, "Where it starts", [
            _labelled(widgets, form.office, "Office", ft.Icons.APARTMENT, required=True),
            widgets.hint("Employees register into their own office." if options["office_locked"] else "The office that holds the document first."),
        ]),
        _section(widgets, ft.Icons.ATTACH_FILE, "File", [_upload_box(widgets, file_name, file_hint, remove_file, choose_file)]),
        _section(widgets, ft.Icons.ADD_CIRCLE, "More details (optional)", [
            ft.ResponsiveRow([
                _labelled(widgets, form.assigned_to, "Assigned to", ft.Icons.PERSON, col=half),
                _labelled(widgets, form.author, "Author", ft.Icons.PERSON_OUTLINE, col=half),
            ], spacing=14, run_spacing=12),
            _labelled(widgets, form.description, "Description", ft.Icons.NOTES),
        ]),
        duplicate_box,
        progress,
        message.box,
    ], spacing=14, scroll=ft.ScrollMode.AUTO, height=min(560, (page.height or 760) - 200) if narrow else 560)
    problem = form.office_problem() if not options["offices"] else None
    if problem:
        message.value = problem
        register_button.disabled = True
    _style_dialog(
        dialog, widgets, "Register Document", content, [cancel_button, register_button], _dialog_width(page, False),
        subtitle="Fill in the required details to register a new document.", icon=ft.Icons.NOTE_ADD, on_close=close,
    )
    dialog.open = True
    page.update()


def _show_problem(page, dialog, widgets, title, text):
    def close(_):
        dialog.open = False
        page.update()

    _style_dialog(dialog, widgets, title, ft.Text(text, color=widgets.body_color()), [ft.TextButton("Close", on_click=close)], _dialog_width(page, False))
    dialog.open = True
    page.update()


ROW_STATES = {
    # state: (label, colour)
    "uploading": ("Uploading", ft.Colors.BLUE_700),
    "ready": ("Ready", ft.Colors.BLUE_GREY_600),
    "registering": ("Registering…", ft.Colors.BLUE_700),
    "registered": ("Registered", ft.Colors.GREEN_700),
    "duplicate": ("Number already used", ft.Colors.AMBER_800),
    "failed": ("Not registered", ft.Colors.RED_700),
    "refused": ("Refused", ft.Colors.RED_700),
}


def open_multiple_register_dialog(page, dialog, api, files, *, on_registered=None, open_details=None, can_print_qr=False, today=None):
    """Register several files at once: each file gets its own title, number and year, the rest is shared."""
    widgets = TrackingWidgets(page)
    this_year = (today or date.today()).year
    try:
        options = load_options(api)
    except Exception as exc:
        _show_problem(page, dialog, widgets, "Register several documents", f"The registration form could not be loaded: {error_detail(exc)[0]}")
        return
    form = _Form(page, options, widgets)
    rows = []  # each: {name, size, tmp_name, state, progress, reason, documents, allow, document, title, number, year}
    status = {"busy": False}

    rows_column = ft.Column(spacing=0)
    summary = ft.Text("", size=12, color=widgets.body_color())
    message = _Notice()
    year_for_all = _year_dropdown(this_year, width=220, widgets=widgets)
    year_for_all.prefix_icon = ft.Icons.CALENDAR_MONTH_OUTLINED
    register_button = ft.Button("Register", icon=ft.Icons.SAVE_OUTLINED, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda _: submit())
    labels_button = ft.OutlinedButton("QR labels", icon=ft.Icons.QR_CODE_2, visible=False, on_click=lambda _: labels())
    close_button = ft.OutlinedButton("Cancel", on_click=lambda _: close())

    def close():
        dialog.open = False
        files.on_progress = None
        page.update()

    def pending():
        return [row for row in rows if row["state"] in ("ready", "duplicate", "failed")]

    def registered_rows():
        return [row for row in rows if row["state"] == "registered"]

    def render():
        rows_column.controls = [row["_view"] for row in rows] or [widgets.empty("No files yet. Choose the files to register.")]
        for row in rows:
            update_row(row)
        uploading = sum(1 for row in rows if row["state"] == "uploading")
        waiting = pending()
        done = registered_rows()
        parts = [f"{len(rows)} file{'s' if len(rows) != 1 else ''}"]
        if uploading:
            parts.append(f"{uploading} uploading")
        if done:
            parts.append(f"{len(done)} registered")
        summary.value = " · ".join(parts) if rows else ""
        register_button.disabled = status["busy"] or uploading > 0 or not waiting or bool(status.get("problem"))
        if uploading:
            set_label(register_button, "Waiting for uploads…")
        elif done and waiting:
            set_label(register_button, f"Register the other {len(waiting)}")
        else:
            set_label(register_button, f"Register {len(waiting)} document{'s' if len(waiting) != 1 else ''}" if waiting else "Register")
        register_button.visible = bool(waiting) or not done
        labels_button.visible = can_print_qr and bool(done)
        set_label(close_button, "Close" if done else "Cancel")
        form.lock(status["busy"] or bool(done))
        page.update()

    def build_row(row):
        """A file's controls, built once so typing is not interrupted while other files upload."""
        def keep(attribute):
            def changed(e):
                row[attribute] = e.control.value
            return changed

        row["_title"] = ft.TextField(label="Title", value=row["title"], on_change=keep("title"), expand=True)
        row["_number"] = ft.TextField(label="Number", value=row["number"], on_change=keep("number"), width=110)
        row["_year"] = _year_dropdown(this_year, width=120, value=row["year"])
        on_dropdown_change(row["_year"], keep("year"))
        row["_status"] = ft.Row([], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        row["_details"] = ft.Column([], spacing=6)
        row["_shown"] = None
        row["_view"] = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=18, color=widgets.muted_color()),
                    ft.Text(row["name"], size=12, weight=ft.FontWeight.W_600, color=widgets.body_color(), expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    row["_status"],
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([row["_title"]], spacing=8),
                ft.Row([row["_number"], row["_year"]], spacing=8, wrap=True, run_spacing=8),
                row["_details"],
            ], spacing=8),
            padding=ft.Padding(0, 10, 0, 12),
            border=ft.Border(bottom=ft.BorderSide(1, widgets.line_color())),
        )

    def update_row(row):
        locked = row["state"] in ("registered", "registering", "refused") or status["busy"]
        for control in (row["_title"], row["_number"], row["_year"]):
            control.disabled = locked
        row["_year"].value = row["year"]
        shown = (row["state"], round(row["progress"] or 0, 2), locked)
        if shown == row["_shown"]:
            return
        row["_shown"] = shown
        label, color = ROW_STATES[row["state"]]
        if row["state"] == "uploading" and row["progress"]:
            label = f"Uploading {int(row['progress'] * 100)}%"
        if row["state"] == "registered":
            label = f"Registered {row['document']['tracking_number']}"
        row["_status"].controls = [widgets.chip(label, color)]
        if row["state"] == "registered" and open_details:
            row["_status"].controls.append(ft.TextButton("View details", on_click=lambda _, r=row: (close(), open_details({"id": r["document"]["id"]}))))
        if row["state"] not in ("registered", "registering") and not status["busy"]:
            row["_status"].controls.append(ft.IconButton(ft.Icons.CLOSE, tooltip="Remove file", on_click=lambda _, r=row: remove(r)))
        details = []
        if row["state"] == "duplicate":
            allow = ft.Checkbox(label="Register anyway: it is a separate document", value=row["allow"], disabled=locked)

            def toggle(e, r=row):
                r["allow"] = bool(e.control.value)
            allow.on_change = toggle
            details += [widgets.hint(f"Same type, number and year as {', '.join(row['documents'])}."), allow]
        elif row["reason"] and row["state"] in ("failed", "refused"):
            details.append(ft.Text(row["reason"], size=12, color=ft.Colors.RED_700))
        if row["state"] == "uploading":
            details.append(ft.ProgressBar(value=row["progress"] or None))
        row["_details"].controls = details

    def remove(row):
        rows.remove(row)
        render()

    def apply_year(_):
        for row in rows:
            if row["state"] not in ("registered", "refused"):
                row["year"] = year_for_all.value
        render()

    def picked(picked_files):
        message.value = ""
        known = {row["name"] for row in rows}
        fresh = [f for f in picked_files if f["name"] not in known]
        if len(fresh) < len(picked_files):
            message.value = "Files with the same name as one already listed were skipped."
        if not fresh:
            render()
            return
        try:
            created = api("POST", "/documents/uploads/create_tmp_uploads", json={"files": [{"filename": f["name"], "size": f["size"]} for f in fresh]})
        except Exception as exc:
            message.value = f"The files could not be prepared for upload: {error_detail(exc)[0]}"
            render()
            return
        uploads = []
        for f, item in zip(fresh, created.get("files") or []):
            row = {
                "name": f["name"], "size": f["size"], "tmp_name": item.get("tmp_name"), "progress": 0.0, "reason": None,
                "documents": [], "allow": False, "document": None,
                "title": title_from_filename(f["name"]), "number": "", "year": year_for_all.value or str(this_year),
                "state": "uploading" if item.get("ok") else "refused",
            }
            if not item.get("ok"):
                row["reason"] = "Only PDF, DOC and DOCX files can be registered." if item.get("reason") == "Unsupported extension" else item.get("reason")
            else:
                uploads.append((f["name"], item["upload_url"]))
            build_row(row)
            rows.append(row)
        render()
        if uploads:
            files.upload(uploads, on_progress)

    def on_progress(name, value, error):
        row = next((r for r in rows if r["name"] == name and r["state"] == "uploading"), None)
        if row is None:
            return
        if error:
            row["state"], row["reason"] = "refused", f"The upload failed: {error}"
        elif upload_finished(value):
            row["state"], row["progress"] = "ready", 1.0
        else:
            row["progress"] = value
        render()

    def submit():
        if status["busy"]:
            return
        message.value = ""
        problem = form.office_problem() or form.due_problem()
        if problem:
            message.value = problem
            page.update()
            return
        waiting = pending()
        untitled = [row["name"] for row in waiting if not (row["title"] or "").strip()]
        if untitled:
            message.value = "Give every file a title: " + ", ".join(untitled)
            page.update()
            return
        skipped = [row for row in waiting if row["state"] == "duplicate" and not row["allow"]]
        normal = [row for row in waiting if row["state"] != "duplicate"]
        overriding = [row for row in waiting if row["state"] == "duplicate" and row["allow"]]
        if not normal and not overriding:
            message.value = "Tick “Register anyway” or change the number of the files whose number is already used."
            page.update()
            return
        status["busy"] = True
        for row in normal + overriding:
            row["state"] = "registering"
        render()
        for batch, allow in ((normal, False), (overriding, True)):
            if batch:
                confirm(batch, allow)
        status["busy"] = False
        if skipped:
            message.value = f"{len(skipped)} file{'s' if len(skipped) != 1 else ''} with a number already used {'were' if len(skipped) != 1 else 'was'} left out."
        if registered_rows() and on_registered:
            on_registered()
        render()

    def confirm(batch, allow):
        shared = form.shared_fields()
        try:
            result = api("POST", "/documents/bulk-register/confirm_tmp", json={
                "tmp_names": [row["tmp_name"] for row in batch],
                "documents": [{
                    "tmp_name": row["tmp_name"], "series_year": int(row["year"]),
                    "title": row["title"].strip(), "document_number": (row["number"] or "").strip() or None,
                } for row in batch],
                **shared,
                "allow_duplicate_number": allow,
            })
        except Exception as exc:
            text = error_detail(exc)[0]
            for row in batch:
                row["state"], row["reason"] = "failed", text
            return
        by_tmp = {row["tmp_name"]: row for row in batch}
        for item in result.get("documents") or []:
            row = by_tmp.get(item.get("tmp_name"))
            if row:
                row["state"], row["document"], row["reason"] = "registered", item, None
        for error in result.get("errors") or []:
            row = by_tmp.get(error.get("tmp_name"))
            if not row:
                continue
            if error.get("duplicate_number"):
                row["state"], row["documents"], row["allow"] = "duplicate", error.get("documents") or [], False
            elif error.get("reason") == "Temporary file not found":
                row["state"], row["reason"] = "refused", "The uploaded file expired. Remove it and choose it again."
            elif error.get("duplicate"):
                row["state"], row["reason"] = "refused", error.get("reason")
            else:
                row["state"], row["reason"] = "failed", error.get("reason") or "Not registered."
        for row in batch:
            if row["state"] == "registering":
                row["state"], row["reason"] = "failed", "Not registered."

    def labels():
        try:
            _download_labels(page, api, [row["document"]["id"] for row in registered_rows()])
        except Exception as exc:
            message.value = f"The QR labels could not be downloaded: {error_detail(exc)[0]}"
            page.update()

    third = {"xs": 12, "sm": 4}
    half = {"xs": 12, "sm": 6}
    content = ft.Column([
        _section(widgets, ft.Icons.DESCRIPTION, "Document details", [
            ft.ResponsiveRow([
                _labelled(widgets, form.document_type, "Document type", ft.Icons.DESCRIPTION_OUTLINED, required=True, col=half),
                _labelled(widgets, form.category, "Category", ft.Icons.GRID_VIEW, required=True, col=half),
            ], spacing=14, run_spacing=12),
            ft.ResponsiveRow([
                _labelled(widgets, form.office, "Office", ft.Icons.APARTMENT, required=True, col=third),
                _labelled(widgets, form.priority, "Priority", ft.Icons.PRIORITY_HIGH, required=True, col=third),
                _labelled(widgets, form.due_field(), "Due date", ft.Icons.EVENT_OUTLINED, col=third),
            ], spacing=14, run_spacing=12),
            ft.ResponsiveRow([
                _labelled(widgets, form.assigned_to, "Assigned to", ft.Icons.PERSON_OUTLINE, col=half),
                _labelled(widgets, form.author, "Author", ft.Icons.EDIT_OUTLINED, col=half),
            ], spacing=14, run_spacing=12),
            widgets.hint("Employees register into their own office." if options["office_locked"] else "The office that holds the documents first."),
        ]),
        _section(widgets, ft.Icons.ATTACH_FILE, "Files", [
            _upload_box(
                widgets,
                ft.Text("Choose files", size=14, weight=ft.FontWeight.BOLD, color=widgets.heading_color()),
                widgets.hint("PDF, DOC or DOCX. Each file becomes one document; give each its own title, number and year."),
                _pill_button(widgets, "Choose files", ft.Icons.ATTACH_FILE, lambda _: files.pick(True, picked)),
            ),
            summary,
            rows_column,
        ]),
        _section(widgets, ft.Icons.CALENDAR_MONTH, "Year", [
            ft.Row(
                [year_for_all, ft.TextButton("Set year for all", on_click=apply_year, style=ft.ButtonStyle(color=_accent(widgets)))],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            message.box,
        ]),
    ], spacing=14, scroll=ft.ScrollMode.AUTO, height=560)
    status["problem"] = form.office_problem() if not options["offices"] else None
    message.value = status["problem"] or ""
    _style_dialog(
        dialog, widgets, "Register Several Documents", content, [close_button, labels_button, register_button], _dialog_width(page, True),
        subtitle="Fill in the details below to register your documents.", icon=ft.Icons.DESCRIPTION, on_close=close,
    )
    dialog.open = True
    render()
