import os
import time
import requests
import base64
import json
from urllib.parse import quote
from dotenv import load_dotenv
import flet as ft
from flet_runtime.uploads import build_upload_url

# Load .env for standalone runs
load_dotenv()


def build_secretariat_view(page: ft.Page, current_user_role, workflow_steps, all_documents, secretariat_selected_ids, save_binary_file_to_workspace, BACKEND_URL, surface_card, section_header):
    role = (current_user_role or "").strip().lower()

    if role not in {"secretariat", "admin"}:
        return ft.Column(
            [
                surface_card(
                    ft.Column(
                        [
                            section_header(
                                "Secretariat Access",
                                "Only Secretariat staff and administrators can use this workspace.",
                                ft.icons.LOCK_OUTLINE,
                                ft.colors.RED_700,
                            ),
                            ft.Text("Your account role does not currently permit access to the Secretariat Operations Hub."),
                        ],
                        spacing=14,
                    ),
                    expand=True,
                )
            ],
            expand=True,
        )

    secretariat_status_filter = ft.Dropdown(
        label="Status",
        width=180,
        options=[ft.dropdown.Option("All")] + [ft.dropdown.Option(step) for step in workflow_steps],
        value="All",
    )
    secretariat_type_filter = ft.Dropdown(
        label="Item Type",
        width=180,
        options=[ft.dropdown.Option("All"), ft.dropdown.Option("Ordinance"), ft.dropdown.Option("Resolution"), ft.dropdown.Option("Committee Report")],
        value="All",
    )
    current_year = time.localtime().tm_year
    secretariat_year_filter = ft.Dropdown(
        label="Year",
        width=140,
        options=[ft.dropdown.Option("All")] + [ft.dropdown.Option(str(year)) for year in range(current_year, current_year - 6, -1)],
        value="All",
    )
    secretariat_search_field = ft.TextField(label="Search document", width=320, prefix_icon=ft.icons.SEARCH)
    secretariat_notice = ft.Text("Select measures to prepare batch paperwork.", size=12, color=ft.colors.BLUE_GREY_600)
    secretariat_table = ft.DataTable(columns=[
        ft.DataColumn(ft.Text("", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("ID", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("Title", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("Type", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("Committee", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD)),
    ], rows=[])

    def build_secretariat_row(doc, selected: bool):
        return ft.DataRow(
            cells=[
                ft.DataCell(ft.Checkbox(value=selected, on_change=lambda e, item=doc: toggle_secretariat_selection(item, bool(e.control.value)))),
                ft.DataCell(ft.Text(str(doc.get("display_id", doc.get("id", "-"))))),
                ft.DataCell(
                    ft.Container(
                        content=ft.Row(
                            [ft.Text(doc.get("title", "Untitled"), size=14)],
                            scroll=ft.ScrollMode.AUTO,
                            tight=True,
                            wrap=False,
                        ),
                        width=420,
                    )
                ),
                ft.DataCell(ft.Text(doc.get("type", "-"))),
                ft.DataCell(ft.Text(doc.get("status", "-"))),
                ft.DataCell(ft.Text(doc.get("committee", "-"))),
                ft.DataCell(
                    ft.PopupMenuButton(
                        icon=ft.icons.MORE_VERT,
                        tooltip="Actions",
                        items=[
                            ft.PopupMenuItem(text="Get QR Code", on_click=lambda e, uid=doc.get("uuid"): view_qr_code(e, uid)),
                            ft.PopupMenuItem(text="Preview file", on_click=lambda e, d=doc: _doc_preview(e, d)),
                            ft.PopupMenuItem(text="Print file", on_click=lambda e, d=doc: _doc_print(e, d)),
                            ft.PopupMenuItem(text="Download file", on_click=lambda e, d=doc: _doc_download(e, d)),
                            ft.PopupMenuItem(text="Advance status", on_click=lambda e, d=doc: advance_document_status(d)),
                            ft.PopupMenuItem(text="Delete record", on_click=lambda e, d=doc: confirm_delete_document(d)),
                        ],
                    )
                ),
            ]
        )

    qr_dialog = ft.AlertDialog(
        title=ft.Text("Generated Legislative QR Code"),
        content=ft.Container(alignment=ft.alignment.center, width=250, height=250),
    )
    page.overlay.append(qr_dialog)

    preview_dialog = ft.AlertDialog(
        title=ft.Text("Document Preview"),
        content=ft.Container(width=700, height=500),
    )
    page.overlay.append(preview_dialog)

    delete_dialog = ft.AlertDialog(
        title=ft.Text("Delete Legislative Record"),
        content=ft.Text(""),
        actions=[],
    )
    page.overlay.append(delete_dialog)
    pending_delete_doc = None
    secretariat_toolbar = ft.Container(
        visible=False,
        padding=ft.padding.all(12),
        bgcolor=ft.colors.BLUE_50,
        border_radius=16,
        content=ft.Row([], spacing=12),
    )

    # mode flag to indicate next picked file should be attached to selected items
    bulk_attach_mode = False

    # File picker for uploading source documents
    file_picker = ft.FilePicker(on_result=lambda e: None)
    page.overlay.append(file_picker)
    # Upload handling variables (mirror admin flow)
    pending_upload_filename = None
    UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
    UPLOAD_SECRET_KEY = os.getenv("FLET_SECRET_KEY", "sb_tolosa_tracking_secret")
    UPLOAD_ENDPOINT = os.getenv("FLET_UPLOAD_HANDLER_ENDPOINT", "upload")
    last_uploaded_filename = None

    def _resolve_uploaded_file_path(path_candidate: str, filename: str) -> str | None:
        candidates = []
        if path_candidate:
            if os.path.isabs(path_candidate):
                candidates.append(path_candidate)
            else:
                candidates.append(os.path.join(UPLOAD_DIR, os.path.basename(path_candidate)))
        candidates.append(os.path.join(UPLOAD_DIR, filename))

        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return os.path.abspath(candidate)

        for root, _, files in os.walk(UPLOAD_DIR):
            if filename in files:
                return os.path.join(root, filename)

        return None

    def _process_uploaded_file(filename: str, file_path: str):
        nonlocal last_uploaded_filename, register_title, register_type, register_committee, register_source_filename
        try:
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Failed to open uploaded file: {ex}"), open=True)
            page.update()
            return

        if not filename.lower().endswith(('.docx', '.pdf')):
            page.snack_bar = ft.SnackBar(ft.Text("Only .docx and .pdf files are supported."), open=True)
            page.update()
            return

        files = {'file': (filename, file_bytes)}
        response = requests.post(f"{BACKEND_URL}/legislative/parse", files=files, verify=False)

        if response.status_code == 200:
            parsed_data = response.json()
            try:
                register_title.value = parsed_data.get('title', register_title.value)
                register_type.value = parsed_data.get('item_type', register_type.value)
                register_committee.value = parsed_data.get('committee', register_committee.value)
            except Exception:
                pass
            last_uploaded_filename = filename
            register_source_filename = filename
            page.snack_bar = ft.SnackBar(ft.Text("✓ Document template parsed successfully! Form auto-filled."), open=True, bgcolor=ft.colors.GREEN)
            refresh_secretariat_table()
            page.update()
        else:
            try:
                error_msg = response.json().get("detail", response.text)
            except Exception:
                error_msg = response.text
            page.snack_bar = ft.SnackBar(ft.Text(f"Parse error: {error_msg}"), open=True)
            page.update()

    def _try_process_pending_upload():
        nonlocal pending_upload_filename
        if not pending_upload_filename:
            return False
        uploaded_path = _resolve_uploaded_file_path(None, pending_upload_filename)
        if uploaded_path:
            pending_upload_filename = None
            page.snack_bar = ft.SnackBar(ft.Text(f"Upload complete: {os.path.basename(uploaded_path)}. Parsing document..."), open=True)
            page.update()
            _process_uploaded_file(os.path.basename(uploaded_path), uploaded_path)
            return True
        return False

    def handle_file_upload(e):
        """Handle browser upload progress and errors for FilePicker."""
        nonlocal pending_upload_filename

        if getattr(e, 'error', None):
            pending_upload_filename = None
            page.snack_bar = ft.SnackBar(ft.Text(f"Upload error: {e.error}"), open=True, bgcolor=ft.colors.RED_400)
            page.update()
            return

        progress_value = getattr(e, 'progress', None)
        if progress_value is not None:
            progress_text = ""
            try:
                if isinstance(progress_value, float) and 0 <= progress_value <= 1:
                    progress_text = f"Upload progress: {int(progress_value * 100)}%"
                elif isinstance(progress_value, int) and progress_value >= 0:
                    progress_text = f"Upload progress: {progress_value}%"
                else:
                    progress_text = f"Uploaded {int(progress_value)} bytes"
            except Exception:
                progress_text = f"Upload progress: {progress_value}"

            page.snack_bar = ft.SnackBar(ft.Text(progress_text), open=True)
            page.update()

        if not getattr(e, 'file_name', None):
            return

        uploaded_path = _resolve_uploaded_file_path(None, e.file_name)
        if uploaded_path:
            pending_upload_filename = None
            page.snack_bar = ft.SnackBar(ft.Text(f"Upload complete: {e.file_name}. Parsing document..."), open=True)
            page.update()
            _process_uploaded_file(e.file_name, uploaded_path)
            return

        # Retry a few times because browser upload may finish after the first event.
        if pending_upload_filename == e.file_name:
            for _ in range(5):
                time.sleep(0.25)
                uploaded_path = _resolve_uploaded_file_path(None, e.file_name)
                if uploaded_path:
                    pending_upload_filename = None
                    page.snack_bar = ft.SnackBar(ft.Text(f"Upload complete: {e.file_name}. Parsing document..."), open=True)
                    page.update()
                    _process_uploaded_file(e.file_name, uploaded_path)
                    return

        page.snack_bar = ft.SnackBar(ft.Text(f"Upload still pending for {e.file_name}. If this repeats, verify FLET_SECRET_KEY and upload_dir settings."), open=True, bgcolor=ft.colors.YELLOW_700)
        page.update()
        return

    def handle_file_import(e):
        """Handle document template import and auto-fill form fields"""
        nonlocal pending_upload_filename

        if not getattr(e, 'files', None):
            page.snack_bar = ft.SnackBar(ft.Text("No file selected."), open=True)
            page.update()
            return

        picked = e.files[0]
        filename = picked.name or 'document'
        raw_path = getattr(e, 'path', None) or getattr(picked, 'path', None)

        if raw_path:
            page.snack_bar = ft.SnackBar(ft.Text(f"Selected {filename}. raw_path={raw_path}. Uploading..."), open=True)
        else:
            page.snack_bar = ft.SnackBar(ft.Text(f"Selected {filename}. Uploading to browser server..."), open=True)
        page.update()

        if raw_path:
            resolved_path = _resolve_uploaded_file_path(raw_path, filename)
            if resolved_path:
                _process_uploaded_file(os.path.basename(resolved_path), resolved_path)
                pending_upload_filename = None
                return

        # If no raw_path, we are running in browser mode and must request signed upload URLs
        if not raw_path:
            try:
                expires_seconds = 60 * 60
                upload_objs = []
                names = []
                for fmeta in e.files:
                    fname = fmeta.name or filename
                    upload_url = build_upload_url(UPLOAD_ENDPOINT, fname, expires_seconds, UPLOAD_SECRET_KEY)
                    upload_objs.append(ft.FilePickerUploadFile(name=fname, upload_url=upload_url, method='PUT'))
                    names.append(fname)

                file_picker.upload(upload_objs)
                page.snack_bar = ft.SnackBar(ft.Text(f"Uploading {', '.join(names)}..."), open=True)
                page.update()
            except Exception as exc:
                page.snack_bar = ft.SnackBar(ft.Text(f"Upload start failed: {exc}"), open=True)
                page.update()

        pending_upload_filename = filename
        _try_process_pending_upload()
        return


    def refresh_secretariat_table():
        rows = []
        search_term = (secretariat_search_field.value or "").strip().lower()
        type_val = secretariat_type_filter.value
        status_val = secretariat_status_filter.value
        year_val = secretariat_year_filter.value

        docs_to_render = list(all_documents)

        for doc in docs_to_render:
            # Numeric ID search: match display_id or id exactly
            is_numeric_search = search_term and search_term.isdigit()
            if is_numeric_search:
                if str(doc.get("display_id", doc.get("id", ""))) == search_term:
                    selected = str(doc.get("id", "")) in secretariat_selected_ids
                    rows.append(build_secretariat_row(doc, selected))
                continue

            # Apply type/status filters first
            if type_val != "All" and doc.get("type", "") != type_val:
                continue
            if status_val != "All" and doc.get("status", "") != status_val:
                continue

            # Year filter based on created_at if available
            if year_val != "All":
                created_at = str(doc.get("created_at") or "")
                year_text = created_at[:4] if created_at else ""
                if year_text != year_val:
                    continue

            # Smart text search across multiple fields
            if search_term:
                title_match = search_term in (doc.get("title") or "").lower()
                type_match = search_term in (doc.get("type") or "").lower()
                committee_match = search_term in (doc.get("committee") or "").lower()
                location_match = search_term in str(doc.get("current_location", "")).lower()
                status_match = search_term in (doc.get("status") or "").lower()
                uuid_match = search_term in (doc.get("uuid") or "").lower()

                if not (title_match or type_match or committee_match or location_match or status_match or uuid_match):
                    continue

            selected = str(doc.get("id", "")) in secretariat_selected_ids
            rows.append(build_secretariat_row(doc, selected))

        secretariat_table.rows = rows
        secretariat_notice.value = f"{len(secretariat_selected_ids)} item(s) selected." if secretariat_selected_ids else "Select measures to prepare batch paperwork."
        secretariat_toolbar.visible = bool(secretariat_selected_ids)
        secretariat_toolbar.content = ft.Row([
            ft.Text(f"{len(secretariat_selected_ids)} items selected", weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("Generate Batch QR PDF", icon=ft.icons.PRINT, on_click=handle_batch_qr_export),
            ft.OutlinedButton("Generate Session Agenda", icon=ft.icons.DESCRIPTION_OUTLINED, on_click=handle_agenda_export),
            ft.ElevatedButton("Change Status", icon=ft.icons.SYNC_ALT, on_click=handle_bulk_change_status),
            ft.ElevatedButton("Assign Committee", icon=ft.icons.GROUP, on_click=handle_bulk_assign_committee),
            ft.ElevatedButton("Attach File to Selected", icon=ft.icons.ATTACH_FILE, on_click=lambda e: start_bulk_attach()),
            ft.ElevatedButton("Export CSV", icon=ft.icons.DOWNLOAD, on_click=handle_export_csv),
        ], spacing=12, wrap=True)
        page.update()

    def toggle_secretariat_selection(doc, checked: bool):
        key = str(doc.get("id", ""))
        if checked:
            secretariat_selected_ids.add(key)
        else:
            secretariat_selected_ids.discard(key)
        refresh_secretariat_table()

    def handle_batch_qr_export(e=None):
        ids = [int(item_id) for item_id in secretariat_selected_ids if str(item_id).isdigit()]
        if not ids:
            page.snack_bar = ft.SnackBar(ft.Text("Select at least one measure first."), open=True)
            page.update()
            return
        try:
            response = requests.post(f"{BACKEND_URL}/documents/batch-qr-pdf", json={"item_ids": ids}, verify=False)
            if response.status_code == 200:
                output_path = save_binary_file_to_workspace("batch_qr_stickers.pdf", response.content)
                page.snack_bar = ft.SnackBar(ft.Text(f"Batch QR PDF saved to {output_path}"), open=True)
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"Batch PDF failed: {response.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Batch PDF error: {exc}"), open=True)
        page.update()


    def start_bulk_attach():
        nonlocal bulk_attach_mode
        if not secretariat_selected_ids:
            page.snack_bar = ft.SnackBar(ft.Text("Select at least one measure first."), open=True)
            page.update()
            return
        bulk_attach_mode = True
        try:
            file_picker.pick_files()
        except Exception:
            page.snack_bar = ft.SnackBar(ft.Text("File picker not available."), open=True)
            bulk_attach_mode = False
            page.update()



    def handle_file_picker_result(e):
        nonlocal register_source_filename, import_mode, bulk_attach_mode
        try:
            # e.files is available in desktop/runtime file picker; use first file only
            files = getattr(e, 'files', None) or []
            if not files:
                page.snack_bar = ft.SnackBar(ft.Text("No file selected."), open=True)
                page.update()
                return

            picked = files[0]
            # runtime provides a path attribute when running locally
            raw_path = getattr(picked, 'path', None)
            filename = picked.name or getattr(picked, 'file_name', None) or os.path.basename(raw_path or "uploaded")

            if not filename.lower().endswith(('.pdf', '.docx')):
                page.snack_bar = ft.SnackBar(ft.Text("Only .pdf and .docx files are supported."), open=True)
                page.update()
                return

            # Read file bytes either from runtime-provided path or via FilePicker upload data
            file_bytes = None
            tried = []
            # If picked is raw bytes-like
            try:
                if isinstance(picked, (bytes, bytearray)):
                    file_bytes = bytes(picked)
                    tried.append("picked_bytes")
            except Exception:
                pass
            # 1) Try raw path if provided (handle file:// URIs)
            if raw_path:
                p = raw_path
                try:
                    if p.startswith("file://"):
                        from urllib.parse import unquote

                        p = unquote(p.split("file://", 1)[1])
                    p = os.path.expanduser(p)
                    tried.append(f"path:{p}")
                    if os.path.exists(p):
                        with open(p, "rb") as fh:
                            file_bytes = fh.read()
                except Exception as ex:
                    tried.append(f"path_error:{ex}")

            # 2) Try common buffer attributes on the picked file (attribute access)
            if file_bytes is None:
                for attr in ("bytes", "data", "content", "raw_bytes", "file_bytes", "bytes_base64", "base64", "file"):
                    try:
                        val = getattr(picked, attr, None)
                    except Exception:
                        val = None
                    if val:
                        # if base64, decode
                        if attr in ("bytes_base64", "base64") and isinstance(val, str):
                            try:
                                import base64 as _b64

                                file_bytes = _b64.b64decode(val)
                                tried.append(f"attr:{attr}:base64")
                                break
                            except Exception:
                                continue
                        # convert memoryview or bytearray to bytes
                        if isinstance(val, (bytes, bytearray, memoryview)):
                            file_bytes = bytes(val)
                            tried.append(f"attr:{attr}")
                            break
                        # if it's a callable file-like getter, try call
                        if callable(val):
                            try:
                                tmp = val()
                                if isinstance(tmp, (bytes, bytearray)):
                                    file_bytes = bytes(tmp)
                                    tried.append(f"attr_call:{attr}")
                                    break
                            except Exception:
                                pass

            # 3) If the picked object exposes an open/read interface, try that
            if file_bytes is None:
                try:
                    opener = getattr(picked, "open", None)
                    if callable(opener):
                        fobj = opener("rb")
                        try:
                            file_bytes = fobj.read()
                        finally:
                            try:
                                fobj.close()
                            except Exception:
                                pass
                        tried.append("open()")
                except Exception as ex:
                    tried.append(f"open_error:{ex}")

            # 4) If picked supports mapping protocol (web), try .get
            if file_bytes is None:
                try:
                    get = getattr(picked, "get", None)
                    if callable(get):
                        for key in ("bytes", "data", "content", "file", "blob", "file_bytes"):
                            try:
                                v = get(key, None)
                            except Exception:
                                v = None
                            if v:
                                if isinstance(v, str):
                                    try:
                                        import base64 as _b64

                                        file_bytes = _b64.b64decode(v)
                                        tried.append(f"get:{key}:base64")
                                        break
                                    except Exception:
                                        continue
                                if isinstance(v, (bytes, bytearray, memoryview)):
                                    file_bytes = bytes(v)
                                    tried.append(f"get:{key}")
                                    break
                except Exception:
                    pass

            # If still nothing, record picked type to help debugging
            if file_bytes is None:
                try:
                    tried.append(f"type:{type(picked).__name__}")
                except Exception:
                    pass

            if file_bytes is None:
                page.snack_bar = ft.SnackBar(ft.Text(f"Failed to read selected file ({';'.join(tried)})"), open=True)
                page.update()
                return

            # Prepare files payload for potential parse/upload actions
            files_payload = {'file': (filename, file_bytes)}

            # If import_mode is set, parse file and open register dialog pre-filled
            if import_mode:
                try:
                    # Parse the document to auto-fill fields
                    parse_resp = requests.post(f"{BACKEND_URL}/legislative/parse", files=files_payload, verify=False)
                    if parse_resp.status_code == 200:
                        parsed = parse_resp.json()
                        register_title.value = parsed.get('title', register_title.value)
                        register_type.value = parsed.get('item_type', register_type.value)
                        register_committee.value = parsed.get('committee', register_committee.value)
                    else:
                        page.snack_bar = ft.SnackBar(ft.Text(f"Parse failed: {parse_resp.text}"), open=True)
                        page.update()
                        import_mode = False
                        return
                except Exception as exc:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Parse error: {exc}"), open=True)
                    page.update()
                    import_mode = False
                    return

                # Keep file bytes in memory and defer saving/attaching until Register is confirmed
                pending_import_bytes = file_bytes
                pending_import_filename = filename
                register_source_filename = None

                # Open register dialog with parsed values
                import_mode = False
                open_register_dialog()
                page.update()
                return

            # If bulk_attach_mode is set, upload file and attach filename to all selected items
            files_payload = {'file': (filename, file_bytes)}
            if bulk_attach_mode:
                try:
                    up_resp = requests.post(f"{BACKEND_URL}/uploads", files=files_payload, verify=False)
                    if up_resp.status_code == 200:
                        saved_name = up_resp.json().get('filename')
                        # call batch update to set source_filename on selected items
                        ids = [int(i) for i in secretariat_selected_ids if str(i).isdigit()]
                        if ids:
                            bat_resp = requests.post(f"{BACKEND_URL}/documents/batch-update", json={"item_ids": ids, "set_source_filename": saved_name}, verify=False)
                            if bat_resp.status_code == 200:
                                # update local cache
                                for d in all_documents:
                                    if str(d.get('id')) in secretariat_selected_ids:
                                        d['source_filename'] = saved_name
                                refresh_secretariat_table()
                                page.snack_bar = ft.SnackBar(ft.Text(f"Attached {saved_name} to {len(ids)} items"), open=True)
                            else:
                                page.snack_bar = ft.SnackBar(ft.Text(f"Batch attach failed: {bat_resp.text}"), open=True)
                        else:
                            page.snack_bar = ft.SnackBar(ft.Text("No valid selected item IDs to attach to."), open=True)
                    else:
                        page.snack_bar = ft.SnackBar(ft.Text(f"Upload failed: {up_resp.text}"), open=True)
                except Exception as exc:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Bulk attach error: {exc}"), open=True)
                finally:
                    bulk_attach_mode = False
                page.update()
                return

            # If exactly one document is selected in the table, associate upload with it
            target_uuid = None
            if len(secretariat_selected_ids) == 1:
                sid = next(iter(secretariat_selected_ids))
                # find document by id
                doc = next((d for d in all_documents if str(d.get('id')) == str(sid)), None)
                if doc:
                    target_uuid = doc.get('uuid')

            if target_uuid:
                url = f"{BACKEND_URL}/legislative/upload/{target_uuid}"
            else:
                url = f"{BACKEND_URL}/uploads"

            response = requests.post(url, files=files_payload, verify=False)
            if response.status_code == 200:
                payload = response.json()
                saved_name = payload.get('filename')
                page.snack_bar = ft.SnackBar(ft.Text(f"Uploaded {saved_name}"), open=True)

                # Update local document record if associated
                if target_uuid:
                    for d in all_documents:
                        if d.get('uuid') == target_uuid:
                            d['source_filename'] = saved_name
                            break
                    refresh_secretariat_table()
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"Upload failed: {response.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Upload error: {exc}"), open=True)
        page.update()

    def start_import():
        nonlocal import_mode
        import_mode = True
        try:
            file_picker.pick_files()
        except Exception:
            page.snack_bar = ft.SnackBar(ft.Text("File picker not available."), open=True)
            import_mode = False
            page.update()

    # assign handler now that it's defined
    # wire file picker callbacks to use admin-like import/upload flow
    try:
        file_picker.on_result = handle_file_import
        file_picker.on_upload = handle_file_upload
    except Exception:
        try:
            file_picker.on_result = handle_file_picker_result
        except Exception:
            pass

    def handle_agenda_export(e=None):
        try:
            ids = [int(item_id) for item_id in secretariat_selected_ids if str(item_id).isdigit()]
            # If ids provided, POST them to the backend; otherwise request default agenda
            if ids:
                response = requests.post(f"{BACKEND_URL}/documents/generate-agenda", json={"item_ids": ids}, verify=False)
            else:
                response = requests.get(f"{BACKEND_URL}/documents/generate-agenda", verify=False)

            if response.status_code == 200:
                filename = f"session_agenda_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
                output_path = save_binary_file_to_workspace(filename, response.content)
                # Show an explicit preview dialog with an Open button
                try:
                    from pathlib import Path

                    file_uri = Path(output_path).absolute().as_uri()
                except Exception:
                    file_uri = None

                def _open_agenda(e=None):
                    try:
                        if file_uri:
                            page.launch_url(file_uri)
                        else:
                            import base64 as _b64

                            b64 = _b64.b64encode(response.content).decode('utf-8')
                            url = f"data:application/pdf;base64,{b64}"
                            page.launch_url(url)
                    except Exception as ex:
                        page.snack_bar = ft.SnackBar(ft.Text(f"Failed to open preview: {ex}"), open=True)
                    preview_alert.open = False
                    page.update()

                preview_alert = ft.AlertDialog(
                    title=ft.Text("Agenda Generated"),
                    content=ft.Column([ft.Text(f"Saved to: {output_path}"), ft.Text("Click Open to preview the PDF.")]),
                    actions=[
                        ft.TextButton("Close", on_click=lambda e: (setattr(preview_alert, 'open', False), page.update())),
                        ft.ElevatedButton("Open", on_click=_open_agenda),
                    ],
                )
                page.dialog = preview_alert
                preview_alert.open = True
                page.update()
                page.snack_bar = ft.SnackBar(ft.Text(f"Agenda PDF saved to {output_path}"), open=True)
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"Agenda export failed: {response.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Agenda export error: {exc}"), open=True)
        page.update()


    def handle_bulk_change_status(e=None):
        if not secretariat_selected_ids:
            page.snack_bar = ft.SnackBar(ft.Text("Select at least one measure first."), open=True)
            page.update()
            return

        # dialog to choose a status from workflow_steps
        options = [ft.dropdown.Option(step) for step in workflow_steps]
        status_dropdown = ft.Dropdown(label="Set Status To", width=320, options=options, value=(workflow_steps[0] if workflow_steps else None))

        def do_set_status(ev=None):
            chosen = status_dropdown.value
            if not chosen:
                page.snack_bar = ft.SnackBar(ft.Text("Please choose a status."), open=True)
                page.update()
                return
            ids = [int(i) for i in secretariat_selected_ids if str(i).isdigit()]
            try:
                payload = {"item_ids": ids, "set_status": chosen}
                resp = requests.post(f"{BACKEND_URL}/documents/batch-update", json=payload, verify=False)
                if resp.status_code == 200:
                    for d in all_documents:
                        if str(d.get('id')) in secretariat_selected_ids:
                            d['status'] = chosen
                    refresh_secretariat_table()
                    page.snack_bar = ft.SnackBar(ft.Text(f"Updated status for {len(ids)} items."), open=True)
                else:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Batch update failed (code {resp.status_code}): {resp.text}"), open=True)
            except Exception as exc:
                page.snack_bar = ft.SnackBar(ft.Text(f"Batch update error: {exc}"), open=True)
            # close dialog and refresh
            try:
                dialog.open = False
            except Exception:
                try:
                    page.dialog.open = False
                except Exception:
                    pass
            page.update()

        dialog = ft.AlertDialog(title=ft.Text("Change Status for Selected Items"), content=ft.Column([status_dropdown]), actions=[ft.TextButton("Cancel", on_click=lambda e: (setattr(dialog, 'open', False), page.update())), ft.ElevatedButton("Apply", on_click=do_set_status)])
        page.dialog = dialog
        dialog.open = True
        page.update()


    def handle_bulk_assign_committee(e=None):
        if not secretariat_selected_ids:
            page.snack_bar = ft.SnackBar(ft.Text("Select at least one measure first."), open=True)
            page.update()
            return

        committee_field = ft.TextField(label="Committee Name", width=360)

        def do_assign(ev=None):
            name = (committee_field.value or "").strip()
            if not name:
                page.snack_bar = ft.SnackBar(ft.Text("Please provide a committee name."), open=True)
                page.update()
                return
            ids = [int(i) for i in secretariat_selected_ids if str(i).isdigit()]
            try:
                payload = {"item_ids": ids, "set_committee": name}
                resp = requests.post(f"{BACKEND_URL}/documents/batch-update", json=payload, verify=False)
                if resp.status_code == 200:
                    for d in all_documents:
                        if str(d.get('id')) in secretariat_selected_ids:
                            d['committee'] = name
                    refresh_secretariat_table()
                    page.snack_bar = ft.SnackBar(ft.Text(f"Assigned committee to {len(ids)} items."), open=True)
                else:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Batch assign failed (code {resp.status_code}): {resp.text}"), open=True)
            except Exception as exc:
                page.snack_bar = ft.SnackBar(ft.Text(f"Batch assign error: {exc}"), open=True)
            try:
                dialog.open = False
            except Exception:
                try:
                    page.dialog.open = False
                except Exception:
                    pass
            page.update()

        dialog = ft.AlertDialog(title=ft.Text("Assign Committee to Selected Items"), content=ft.Column([committee_field]), actions=[ft.TextButton("Cancel", on_click=lambda e: (setattr(dialog, 'open', False), page.update())), ft.ElevatedButton("Apply", on_click=do_assign)])
        page.dialog = dialog
        dialog.open = True
        page.update()


    def handle_export_csv(e=None):
        ids = [int(i) for i in secretariat_selected_ids if str(i).isdigit()]
        try:
            if ids:
                param = ",".join(str(i) for i in ids)
                resp = requests.get(f"{BACKEND_URL}/documents/export", params={"item_ids": param}, verify=False)
            else:
                resp = requests.get(f"{BACKEND_URL}/documents/export", verify=False)
            if resp.status_code == 200:
                path = save_binary_file_to_workspace("secretariat_export.csv", resp.content)
                page.snack_bar = ft.SnackBar(ft.Text(f"Export saved to {path}"), open=True)
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"Export failed: {resp.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Export error: {exc}"), open=True)
        page.update()

    # wire filters and search (assigned after action functions are defined)

    # --- Actions borrowed from admin UI ---
    def view_qr_code(e, uuid_code):
        if not uuid_code:
            page.snack_bar = ft.SnackBar(ft.Text("No UUID available for QR generation."), open=True)
            page.update()
            return
        qr_url = f"{BACKEND_URL}/legislative/qrcode/{uuid_code}"
        try:
            response = requests.get(qr_url, verify=False)
            if response.status_code == 200:
                img_base64 = base64.b64encode(response.content).decode("utf-8")
                qr_dialog.content = ft.Image(src_base64=img_base64, width=200, height=200, fit=ft.ImageFit.CONTAIN)
                qr_dialog.open = True
                page.update()
                return
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"QR load failed: {response.text}"), open=True)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Connection error: {ex}"), open=True)
        page.update()

    def _doc_print(e, doc):
        html = f"""<!doctype html><html><head><meta charset='utf-8'><title>{doc.get('title')}</title></head><body><h1>{doc.get('title')}</h1><p><strong>Type:</strong> {doc.get('type')}</p><p><strong>Committee:</strong> {doc.get('committee')}</p><p><strong>Status:</strong> {doc.get('status')}</p><p><strong>UUID:</strong> {doc.get('uuid')}</p><script>window.onload=function(){{window.print();}};</script></body></html>"""
        data = base64.b64encode(html.encode('utf-8')).decode('utf-8')
        url = f"data:text/html;base64,{data}"
        page.launch_url(url)

    def _doc_preview(e, doc):
        src = doc.get("source_filename")
        if not src:
            page.snack_bar = ft.SnackBar(ft.Text("No uploaded source file available for preview."), open=True)
            page.update()
            return

        if src.lower().endswith('.pdf'):
            page.launch_url(f"{BACKEND_URL}/legislative/preview/{quote(src)}")
            return

        try:
            resp = requests.get(f"{BACKEND_URL}/legislative/preview/{quote(src)}", verify=False)
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("text", "")
                preview_dialog.content = ft.Container(
                    ft.Column([ft.Text(doc.get("title", ""), weight=ft.FontWeight.BOLD), ft.Divider(), ft.Text(text)], tight=True, scroll=ft.ScrollMode.AUTO),
                    width=700,
                    height=500,
                )
                preview_dialog.open = True
                page.update()
                return
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Preview failed: {exc}"), open=True)
            page.update()
            return

    def _doc_download(e, doc):
        src = doc.get("source_filename")
        if src:
            try:
                url = f"{BACKEND_URL}/uploads/{quote(src)}"
                page.launch_url(url)
                return
            except Exception:
                pass

        json_str = json.dumps(doc, indent=2)
        data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        url = f"data:application/json;base64,{data}"
        page.launch_url(url)

    def advance_document_status(doc):
        try:
            response = requests.post(f"{BACKEND_URL}/legislative/advance/{quote(doc.get('uuid'))}", params={"actor": "secretariat", "location": "Secretariat Hub"}, verify=False)
            if response.status_code == 200:
                payload = response.json()
                new_stage = payload.get("current_stage", doc.get("status", ""))
                doc["status"] = new_stage
                refresh_secretariat_table()
                page.snack_bar = ft.SnackBar(ft.Text(payload.get("message", f"Advanced to {new_stage}")), open=True)
                page.update()
                return
            page.snack_bar = ft.SnackBar(ft.Text(f"Advance failed: {response.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Advance error: {exc}"), open=True)
        page.update()

    def confirm_delete_document(doc):
        nonlocal pending_delete_doc
        pending_delete_doc = doc
        delete_dialog.content = ft.Text(f"Are you sure you want to delete '{doc.get('title')}'?")
        delete_dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda e: close_delete_dialog()),
            ft.ElevatedButton("Delete", bgcolor=ft.colors.RED_600, color=ft.colors.WHITE, on_click=lambda e: delete_document_record(pending_delete_doc)),
        ]
        delete_dialog.open = True
        page.update()

    def close_delete_dialog():
        nonlocal pending_delete_doc
        pending_delete_doc = None
        delete_dialog.open = False
        page.update()

    def delete_document_record(doc):
        try:
            response = requests.delete(f"{BACKEND_URL}/legislative/delete/{quote(doc.get('uuid'))}", params={"actor": "secretariat", "location": "Secretariat Hub"}, verify=False)
            if response.status_code == 200:
                all_documents[:] = [item for item in all_documents if item.get("uuid") != doc.get("uuid")]
                refresh_secretariat_table()
                page.snack_bar = ft.SnackBar(ft.Text(response.json().get("message", "Record deleted")), open=True)
                delete_dialog.open = False
                page.update()
                return
            page.snack_bar = ft.SnackBar(ft.Text(f"Delete failed: {response.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Delete error: {exc}"), open=True)
        page.update()

    # --- Register new measure dialog ---
    register_title = ft.TextField(label="Title", width=520)
    register_type = ft.Dropdown(label="Item Type", width=220, options=[ft.dropdown.Option("Ordinance"), ft.dropdown.Option("Resolution"), ft.dropdown.Option("Committee Report")], value="Ordinance")
    register_committee = ft.TextField(label="Assigned Committee", width=320)
    register_source_filename: str | None = None
    # in-memory buffer for imported file until user confirms Register
    pending_import_bytes: bytes | None = None
    pending_import_filename: str | None = None
    
    def refresh_measure_number_preview(e=None):
        try:
            # only prefill when title is empty or looks like a Draft placeholder
            val = (register_title.value or "").strip()
            if val and not val.startswith("Draft"):
                return
            resp = requests.get(f"{BACKEND_URL}/documents/next-number", params={"item_type": register_type.value or "Ordinance"}, verify=False)
            if resp.status_code == 200:
                next_number = resp.json().get("next_number")
                if next_number:
                    register_title.value = next_number
                    page.update()
        except Exception:
            pass

    register_type.on_change = lambda e: refresh_measure_number_preview(e)
    import_mode = False


    def open_register_dialog(e=None):
        # show staged/imported filename or already-attached source filename
        staged_row = None
        display_name = register_source_filename or pending_import_filename
        if display_name:
            staged_row = ft.Row([
                ft.Text("Staged file:", weight=ft.FontWeight.BOLD),
                ft.Text(display_name, selectable=True),
                ft.IconButton(icon=ft.icons.CLOSE, tooltip="Remove staged file", on_click=lambda e: (clear_staged_file(), page.update())),
            ], spacing=12)

        contents = [register_title, register_type, register_committee]
        if staged_row:
            contents.append(ft.Divider())
            contents.append(staged_row)

        dialog = ft.AlertDialog(
            title=ft.Text("Register New Measure"),
            content=ft.Column(contents, tight=True),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: dialog_close(dialog)),
                ft.ElevatedButton("Register", on_click=lambda e: submit_register(dialog)),
            ],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()


    def clear_staged_file():
        nonlocal pending_import_bytes, pending_import_filename, register_source_filename
        pending_import_bytes = None
        pending_import_filename = None
        register_source_filename = None

    def dialog_close(dialog):
        try:
            nonlocal pending_import_bytes, pending_import_filename, register_source_filename
            dialog.open = False
            # clear any staged import when dialog is closed without registering
            pending_import_bytes = None
            pending_import_filename = None
            register_source_filename = None
            page.update()
        except Exception:
            pass

    def submit_register(dialog):
        nonlocal pending_import_bytes, pending_import_filename, register_source_filename
        title = (register_title.value or "").strip()
        item_type = (register_type.value or "Ordinance").strip()
        committee = (register_committee.value or "").strip()
        if not title or not committee:
            page.snack_bar = ft.SnackBar(ft.Text("Please fill out all mandatory fields."), open=True)
            page.update()
            return
        try:
            # If there's a pending imported file buffered in memory, upload it first
            if pending_import_bytes and not register_source_filename:
                try:
                    upload_payload = {'file': (pending_import_filename, pending_import_bytes)}
                    up_resp = requests.post(f"{BACKEND_URL}/uploads", files=upload_payload, verify=False)
                    if up_resp.status_code == 200:
                        register_source_filename = up_resp.json().get('filename')
                    else:
                        page.snack_bar = ft.SnackBar(ft.Text(f"Failed to attach imported file: {up_resp.text}"), open=True)
                        page.update()
                        return
                except Exception as exc:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Upload error: {exc}"), open=True)
                    page.update()
                    return
            response = requests.post(
                f"{BACKEND_URL}/legislative/register",
                json={"title": title, "item_type": item_type, "committee": committee, "source_filename": register_source_filename},
                verify=False,
            )
            if response.status_code == 200:
                result = response.json()
                all_documents.append({
                    "id": result.get("id", "-"),
                    "title": title,
                    "type": item_type,
                    "committee": committee,
                    "status": result.get("current_stage", "Draft"),
                    "current_location": result.get("current_location", "Records Registry"),
                    "uuid": result.get("tracking_uuid"),
                    "source_filename": result.get("source_filename") or register_source_filename,
                })
                # clear any pending import buffer now that file (if any) has been uploaded and attached
                pending_import_bytes = None
                pending_import_filename = None
                register_source_filename = None

                register_title.value = ""
                register_committee.value = ""
                dialog.open = False
                refresh_secretariat_table()
                page.snack_bar = ft.SnackBar(ft.Text("Legislative Document Registered Successfully!"), open=True)
                page.update()
                return
            page.snack_bar = ft.SnackBar(ft.Text(f"Register failed: {response.text}"), open=True)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Connection Failed: Ensure Backend server is running. Error: {ex}"), open=True)
        page.update()

    # wire register button
    # replace the placeholder button by updating UI controls after build
    try:
        # find the Register button in the controls by text and assign on_click
        pass
    except Exception:
        pass

    # wire filters and search
    secretariat_status_filter.on_change = lambda e: refresh_secretariat_table()
    secretariat_type_filter.on_change = lambda e: refresh_secretariat_table()
    secretariat_year_filter.on_change = lambda e: refresh_secretariat_table()
    secretariat_search_field.on_change = lambda e: refresh_secretariat_table()
    refresh_secretariat_table()

    return ft.Column(
        [
            surface_card(
                ft.Column(
                    [
                        section_header(
                            "Secretariat Operations Hub",
                            "Manage high-volume legislative paperwork, batch QR stickers, and session agendas.",
                            ft.icons.ACCOUNT_BALANCE_OUTLINED,
                            ft.colors.BLUE_800,
                        ),
                        ft.Divider(height=1),
                        ft.Row(
                            [
                                ft.ElevatedButton("+ Register New Measure", icon=ft.icons.ADD, on_click=lambda e: open_register_dialog(e)),
                                    ft.ElevatedButton("Import Document", icon=ft.icons.FILE_UPLOAD, on_click=lambda e: start_import()),
                                ft.ElevatedButton("🖨️ Batch QR Sheet", icon=ft.icons.PRINT, on_click=handle_batch_qr_export),
                                ft.ElevatedButton("📄 Generate Session Agenda", icon=ft.icons.DESCRIPTION_OUTLINED, on_click=handle_agenda_export),
                            ],
                            spacing=12,
                            wrap=True,
                        ),
                        ft.Row([secretariat_status_filter, secretariat_type_filter, secretariat_year_filter, secretariat_search_field], spacing=12, wrap=True),
                        ft.Container(height=4),
                        ft.Container(content=secretariat_table, bgcolor=ft.colors.BLUE_GREY_50, border_radius=18, padding=12),
                        secretariat_toolbar,
                        secretariat_notice,
                    ],
                    spacing=14,
                ),
            )
        ],
        expand=True,
    )
    
