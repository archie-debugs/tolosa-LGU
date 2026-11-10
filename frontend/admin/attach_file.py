"""Replace a document's file. (A document without one gets its file through the edit form.)

The browser sends the chosen file to a temporary upload first (the web app never holds the bytes),
then the document takes it by its temporary name, the same way registration does.
"""

import flet as ft

from frontend.admin.registration import error_detail, set_label, upload_finished

RULES = "The file must be a PDF, DOC, or DOCX file and must not duplicate existing file content."


def open_attach_file_dialog(page, dialog, api, files, document, *, on_saved=None):
    """`api(method, path, **kwargs)` returns the JSON body or raises with the backend's detail;
    `files` is a registration.PickerFiles; `on_saved(message)` runs after the file is stored.
    `document` must have a file."""
    current = next(a for a in document.get("attachments") or [] if isinstance(a, dict) and a.get("id"))
    action = "Replace File"
    # "tmp_name": the chosen file once uploaded, reused if saving fails: a browser sends a picked file only once.
    state = {"file": None, "busy": False, "tmp_name": None}
    chosen_text = ft.Text("No file selected", size=12, color=ft.Colors.BLUE_GREY_600)
    message = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)
    progress = ft.ProgressBar(value=0, visible=False)
    submit = ft.FilledButton(action, icon=ft.Icons.UPLOAD_FILE, on_click=lambda _: start())

    def show(text=""):
        message.value, message.visible = text, bool(text)
        page.update()

    def set_busy(busy, label=None):
        state["busy"] = busy
        submit.disabled = busy
        set_label(submit, label or action)
        progress.visible = busy

    def fail(text):
        set_busy(False)
        show(text)

    def picked(chosen):
        state["file"] = chosen[0] if chosen else None
        state["tmp_name"] = None
        chosen_text.value = state["file"]["name"] if state["file"] else "No file selected"
        show()

    def close():
        dialog.open = False
        page.update()

    def start():
        chosen = state["file"]
        if state["busy"]:
            return
        if not chosen:
            show("Choose a file first.")
            return
        show()
        if state["tmp_name"]:
            set_busy(True, "Saving…")
            save(state["tmp_name"])
            return
        set_busy(True, "Uploading…")
        try:
            created = api("POST", "/documents/uploads/create_tmp_uploads", json={"files": [{"filename": chosen["name"], "size": chosen["size"]}]})
        except Exception as exc:
            fail(f"The file could not be prepared for upload: {error_detail(exc)[0]}")
            return
        item = next(iter(created.get("files") or []), {})
        if not item.get("ok"):
            fail("Only PDF, DOC and DOCX files can be used.")
            return

        def on_progress(name, value, error):
            if name != chosen["name"] or not state["busy"]:
                return
            if error:
                fail(f"The upload failed: {error}")
            elif upload_finished(value):
                state["tmp_name"] = item["tmp_name"]
                save(item["tmp_name"])
            else:
                progress.value = value
                page.update()

        progress.value = 0
        page.update()
        files.upload([(chosen["name"], item["upload_url"])], on_progress)

    def save(tmp_name):
        try:
            api("POST", f"/documents/{document['id']}/attachments/{current['id']}/replace", data={"tmp_name": tmp_name})
        except Exception as exc:
            fail(error_detail(exc)[0])
            return
        state["busy"] = False
        close()
        if on_saved:
            on_saved("File replaced.")

    dialog.title = ft.Text(action, size=20, weight=ft.FontWeight.BOLD)
    dialog.content = ft.Column(
        [
            ft.Text(RULES, size=12, color=ft.Colors.BLUE_GREY_600),
            ft.Text("Current file", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700),
            ft.Text(str(current.get("original_filename") or "-"), size=13),
            ft.Row(
                [
                    ft.Icon(ft.Icons.UPLOAD_FILE, color=ft.Colors.BLUE_700, size=22),
                    ft.Column([ft.Text("New file", size=13, weight=ft.FontWeight.BOLD), chosen_text], spacing=3, expand=True),
                    ft.OutlinedButton("Choose file", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=lambda _: files.pick(False, picked)),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            progress,
            message,
        ],
        spacing=10,
        width=min(620, (page.width or 700) - 48),
        tight=True,
    )
    dialog.actions = [ft.TextButton("Cancel", on_click=lambda _: close()), submit]
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    dialog.open = True
    page.update()
