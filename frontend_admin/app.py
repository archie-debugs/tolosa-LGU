import flet as ft
import requests
import base64
import os
import sys
import asyncio
import time
import urllib3
from flet_runtime.uploads import build_upload_url
from urllib.parse import quote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Use the default Windows Proactor event loop policy so Flet can launch the desktop app subprocess.
# The selector policy prevents asyncio subprocess creation on Windows in this environment.
# if sys.platform == 'win32':
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
UPLOAD_SECRET_KEY = os.getenv("FLET_SECRET_KEY", "sb_tolosa_tracking_secret")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.environ["FLET_SECRET_KEY"] = UPLOAD_SECRET_KEY
os.environ["FLET_UPLOAD_DIR"] = UPLOAD_DIR
os.environ["FLET_UPLOAD_HANDLER_ENDPOINT"] = os.getenv("FLET_UPLOAD_HANDLER_ENDPOINT", "upload")
print(f"FLET_UPLOAD_DIR={UPLOAD_DIR}")
print(f"FLET_SECRET_KEY={UPLOAD_SECRET_KEY}")
UPLOAD_ENDPOINT = os.getenv("FLET_UPLOAD_HANDLER_ENDPOINT", "upload")

def main(page: ft.Page):
    page.title = "LGU Tolosa - Sangguniang Bayan Admin System"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.scroll = ft.ScrollMode.AUTO
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.padding = 30

    # Current User Session State
    current_user = None
    
    # Data storage for all documents
    all_documents = []
    pending_upload_filename = None
    last_uploaded_filename = None

    # --- UI COMPONENTS ---
    title_input = ft.TextField(label="Document / Ordinance Title", hint_text="Enter full legislative title...", width=500)
    type_dropdown = ft.Dropdown(
        label="Item Type",
        width=200,
        options=[
            ft.dropdown.Option("Ordinance"),
            ft.dropdown.Option("Resolution"),
            ft.dropdown.Option("Committee Report"),
        ],
        value="Ordinance"
    )
    committee_input = ft.TextField(label="Assigned Committee", hint_text="e.g., Committee on Finance", width=300)
    
    # File picker for document template import
    file_picker = ft.FilePicker(on_result=lambda e: None)  # Will be set in load_dashboard
    page.overlay.append(file_picker)
    
    # --- SEARCH AND FILTER COMPONENTS ---
    search_field = ft.TextField(
        label="Search by Title or Tracking UUID",
        hint_text="Type to search...",
        width=400,
        prefix_icon=ft.icons.SEARCH,
        on_change=lambda e: None  # Will be set in load_dashboard
    )
    
    type_filter = ft.Dropdown(
        label="Filter by Type",
        width=200,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("Ordinance"),
            ft.dropdown.Option("Resolution"),
            ft.dropdown.Option("Committee Report"),
        ],
        value="All",
        on_change=lambda e: None  # Will be set in load_dashboard
    )
    
    status_filter = ft.Dropdown(
        label="Filter by Status",
        width=200,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("First Reading"),
            ft.dropdown.Option("Second Reading"),
            ft.dropdown.Option("Committee Review"),
            ft.dropdown.Option("Approved"),
            ft.dropdown.Option("Pending"),
        ],
        value="All",
        on_change=lambda e: None  # Will be set in load_dashboard
    )
    
    data_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Title", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Type", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Committee", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Current Status", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD)),
        ],
        rows=[]
    )

    qr_dialog = ft.AlertDialog(
        title=ft.Text("Generated Legislative QR Code"),
        content=ft.Container(alignment=ft.alignment.center, width=250, height=250)
    )

    # --- ACTIONS ---
    def view_qr_code(e, uuid_code):
        qr_url = f"{BACKEND_URL}/legislative/qrcode/{uuid_code}"
        try:
            response = requests.get(qr_url, verify=False)
            if response.status_code == 200:
                img_base64 = base64.b64encode(response.content).decode("utf-8")
                qr_dialog.content = ft.Image(
                    src_base64=img_base64,
                    width=200,
                    height=200,
                    fit=ft.ImageFit.CONTAIN
                )
                page.overlay.append(qr_dialog)
                qr_dialog.open = True
                page.update()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Connection error: {ex}"), open=True)
            page.update()

    def _doc_print(e, doc):
        # Build a printable HTML and open it in a new tab which triggers print
        html = f"""<!doctype html><html><head><meta charset='utf-8'><title>{doc['title']}</title></head><body><h1>{doc['title']}</h1><p><strong>Type:</strong> {doc['type']}</p><p><strong>Committee:</strong> {doc['committee']}</p><p><strong>Status:</strong> {doc['status']}</p><p><strong>UUID:</strong> {doc['uuid']}</p><script>window.onload=function(){{window.print();}};</script></body></html>"""
        data = base64.b64encode(html.encode('utf-8')).decode('utf-8')
        url = f"data:text/html;base64,{data}"
        page.launch_url(url)

    def _doc_download(e, doc):
        # If the document has a source filename, download it from the backend uploads endpoint
        src = doc.get("source_filename")
        if src:
            try:
                url = f"{BACKEND_URL}/uploads/{quote(src)}"
                page.launch_url(url)
                return
            except Exception:
                pass

        # Fallback: Offer document metadata as JSON download
        import json

        json_str = json.dumps(doc, indent=2)
        data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        url = f"data:application/json;base64,{data}"
        page.launch_url(url)

    def _doc_copy_json(e, doc):
        import json

        json_str = json.dumps(doc, indent=2)
        try:
            page.set_clipboard(json_str)
            page.snack_bar = ft.SnackBar(ft.Text("Document metadata copied to clipboard."), open=True)
            page.update()
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Copy failed: {exc}"), open=True)
            page.update()

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

    def _debug_upload_dir():
        try:
            return sorted(os.listdir(UPLOAD_DIR))
        except Exception as exc:
            return [f"ERROR: {exc}"]

    def _process_uploaded_file(filename: str, file_path: str):
        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        if not filename.lower().endswith(('.docx', '.pdf')):
            page.snack_bar = ft.SnackBar(ft.Text("Only .docx and .pdf files are supported."), open=True)
            page.update()
            return

        files = {'file': (filename, file_bytes)}
        response = requests.post(f"{BACKEND_URL}/legislative/parse", files=files, verify=False)

        if response.status_code == 200:
            parsed_data = response.json()
            title_input.value = parsed_data.get("title", "")
            type_dropdown.value = parsed_data.get("item_type", "Ordinance")
            committee_input.value = parsed_data.get("committee", "")
            # remember uploaded filename for association on register
            nonlocal last_uploaded_filename
            last_uploaded_filename = filename
            page.snack_bar = ft.SnackBar(
                ft.Text("✓ Document template parsed successfully! Form auto-filled."),
                open=True,
                bgcolor=ft.colors.GREEN,
            )
            update_table_view()
            page.update()
        else:
            error_msg = response.json().get("detail", response.text)
            page.snack_bar = ft.SnackBar(ft.Text(f"Parse error: {error_msg}"), open=True)
            page.update()

    def _try_process_pending_upload():
        nonlocal pending_upload_filename
        if not pending_upload_filename:
            return False
        uploaded_path = _resolve_uploaded_file_path(None, pending_upload_filename)
        if uploaded_path:
            pending_upload_filename = None
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Upload complete: {os.path.basename(uploaded_path)}. Parsing document..."),
                open=True,
            )
            page.update()
            _process_uploaded_file(os.path.basename(uploaded_path), uploaded_path)
            return True
        return False

    def handle_file_upload(e):
        """Handle browser upload progress and errors for FilePicker."""
        nonlocal pending_upload_filename

        print(f"handle_file_upload event: file_name={getattr(e,'file_name',None)} progress={getattr(e,'progress',None)} error={getattr(e,'error',None)}")

        if e.error:
            pending_upload_filename = None
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Upload error: {e.error}"),
                open=True,
                bgcolor=ft.colors.RED_400,
            )
            page.update()
            return

        progress_value = e.progress
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

            page.snack_bar = ft.SnackBar(
                ft.Text(progress_text),
                open=True,
            )
            page.update()

        if not e.file_name:
            return

        uploaded_path = _resolve_uploaded_file_path(None, e.file_name)
        if uploaded_path:
            pending_upload_filename = None
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Upload complete: {e.file_name}. Parsing document..."),
                open=True,
            )
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
                    page.snack_bar = ft.SnackBar(
                        ft.Text(f"Upload complete: {e.file_name}. Parsing document..."),
                        open=True,
                    )
                    page.update()
                    _process_uploaded_file(e.file_name, uploaded_path)
                    return

        page.snack_bar = ft.SnackBar(
            ft.Text(
                f"Upload still pending for {e.file_name}. If this repeats, verify FLET_SECRET_KEY and upload_dir settings."
            ),
            open=True,
            bgcolor=ft.colors.YELLOW_700,
        )
        page.update()
        return

    def handle_file_import(e):
        """Handle document template import and auto-fill form fields"""
        nonlocal pending_upload_filename

        if not getattr(e, "files", None):
            page.snack_bar = ft.SnackBar(ft.Text("No file selected."), open=True)
            page.update()
            return

        picked = e.files[0]
        filename = picked.name or "document"
        raw_path = getattr(e, "path", None) or getattr(picked, "path", None)

        if raw_path:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Selected {filename}. raw_path={raw_path}. Uploading..."),
                open=True,
            )
        else:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Selected {filename}. Uploading to browser server..."),
                open=True,
            )
        page.update()

        if raw_path:
            resolved_path = _resolve_uploaded_file_path(raw_path, filename)
            if resolved_path:
                _process_uploaded_file(os.path.basename(resolved_path), resolved_path)
                pending_upload_filename = None
                return

        # If no raw_path, we are running in browser mode and must request
        # signed upload URLs and instruct the runtime to perform the upload.
        if not raw_path:
            try:
                expires_seconds = 60 * 60
                upload_objs = []
                names = []
                for fmeta in e.files:
                    fname = fmeta.name or filename
                    # build a signed upload URL for the runtime upload handler
                    upload_url = build_upload_url(UPLOAD_ENDPOINT, fname, expires_seconds, UPLOAD_SECRET_KEY)
                    upload_objs.append(ft.FilePickerUploadFile(name=fname, upload_url=upload_url, method="PUT"))
                    names.append(fname)

                # instruct the FilePicker runtime to upload selected files
                file_picker.upload(upload_objs)

                page.snack_bar = ft.SnackBar(ft.Text(f"Uploading {', '.join(names)}..."), open=True)
                page.update()
            except Exception as exc:
                page.snack_bar = ft.SnackBar(ft.Text(f"Upload start failed: {exc}"), open=True)
                page.update()

        pending_upload_filename = filename
        _try_process_pending_upload()
        return

    def submit_form(e):
        if not title_input.value or not committee_input.value:
            page.snack_bar = ft.SnackBar(ft.Text("Please fill out all mandatory fields."), open=True)
            page.update()
            return

        params = {
            "title": title_input.value,
            "item_type": type_dropdown.value,
            "committee": committee_input.value
        }

        try:
            response = requests.post(f"{BACKEND_URL}/legislative/register", params=params, verify=False)
            if response.status_code == 200:
                nonlocal last_uploaded_filename
                result = response.json()
                uuid_code = result["tracking_uuid"]

                # Add to data storage (associate uploaded filename if any)
                all_documents.append({
                    "id": result.get("id", "-"),
                    "title": title_input.value,
                    "type": type_dropdown.value,
                    "committee": committee_input.value,
                    "status": "First Reading",
                    "uuid": uuid_code,
                    "source_filename": last_uploaded_filename,
                })

                title_input.value = ""
                committee_input.value = ""
                page.snack_bar = ft.SnackBar(ft.Text("Legislative Document Registered Successfully!"), open=True)

                # clear last uploaded filename after associating with a record
                last_uploaded_filename = None

                # Update the table immediately
                update_table_view()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Connection Failed: Ensure Backend server is running. Error: {ex}"), open=True)
            page.update()
    
    # Function to update table view based on filters
    def update_table_view():
        """Filter and update the data table based on search and filter values - SMART search with ID priority"""
        search_term = (search_field.value or "").strip().lower()
        type_val = type_filter.value
        status_val = status_filter.value
        
        data_table.rows.clear()
        
        docs_to_render = list(all_documents)

        for doc in docs_to_render:
            # Check if search term is NUMERIC (all digits) - treat as ID search
            is_numeric_search = search_term and search_term.isdigit()
            
            if is_numeric_search:
                # ID search: show ONLY documents with matching ID (ignore type/status filters)
                if str(doc["id"]) == search_term:
                    data_table.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(str(doc["id"]))),
                                ft.DataCell(ft.Text(doc["title"])),
                                ft.DataCell(ft.Text(doc["type"])),
                                ft.DataCell(ft.Text(doc["committee"])),
                                ft.DataCell(ft.Text(doc["status"], color=ft.colors.BLUE)),
                                ft.DataCell(
                                    ft.Row([
                                        ft.IconButton(icon=ft.icons.QR_CODE, tooltip="Get QR Code", on_click=lambda e, uid=doc["uuid"]: view_qr_code(e, uid)),
                                        ft.IconButton(icon=ft.icons.PRINT, tooltip="Print", on_click=lambda e, d=doc: _doc_print(e, d)),
                                        ft.IconButton(icon=ft.icons.FILE_DOWNLOAD, tooltip="Download JSON", on_click=lambda e, d=doc: _doc_download(e, d)),
                                        ft.IconButton(icon=ft.icons.CONTENT_COPY, tooltip="Copy JSON", on_click=lambda e, d=doc: _doc_copy_json(e, d)),
                                    ], spacing=2)
                                ),
                            ]
                        )
                    )
                continue
            
            # Non-numeric search: apply type/status filters first
            if type_val != "All" and doc["type"] != type_val:
                continue
            
            if status_val != "All" and doc["status"] != status_val:
                continue
            
            # Apply smart search across text fields (Title, Type, Committee, Status, UUID)
            if search_term:
                title_match = search_term in doc["title"].lower()
                type_match = search_term in doc["type"].lower()
                committee_match = search_term in doc["committee"].lower()
                status_match = search_term in doc["status"].lower()
                uuid_match = search_term in doc["uuid"].lower()
                
                if not (title_match or type_match or committee_match or status_match or uuid_match):
                    continue
            
            # Add matching row to table
            data_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(doc["id"]))),
                        ft.DataCell(ft.Text(doc["title"])),
                        ft.DataCell(ft.Text(doc["type"])),
                        ft.DataCell(ft.Text(doc["committee"])),
                        ft.DataCell(ft.Text(doc["status"], color=ft.colors.BLUE)),
                        ft.DataCell(
                            ft.Row([
                                ft.IconButton(icon=ft.icons.QR_CODE, tooltip="Get QR Code", on_click=lambda e, uid=doc["uuid"]: view_qr_code(e, uid)),
                                ft.IconButton(icon=ft.icons.PRINT, tooltip="Print", on_click=lambda e, d=doc: _doc_print(e, d)),
                                ft.IconButton(icon=ft.icons.FILE_DOWNLOAD, tooltip="Download JSON", on_click=lambda e, d=doc: _doc_download(e, d)),
                                ft.IconButton(icon=ft.icons.CONTENT_COPY, tooltip="Copy JSON", on_click=lambda e, d=doc: _doc_copy_json(e, d)),
                            ], spacing=2)
                        ),
                    ]
                )
            )
        
        page.update()

    import_button = ft.ElevatedButton(
        "Import Document Template",
        icon=ft.icons.UPLOAD_FILE,
        bgcolor=ft.colors.GREEN,
        color=ft.colors.WHITE,
        on_click=lambda e: file_picker.pick_files(allowed_extensions=["docx", "pdf"])
    )
    
    submit_button = ft.ElevatedButton("Register and Auto-Generate QR", icon=ft.icons.ADD, on_click=submit_form)

    # --- MAIN DASHBOARD LAYOUT VIEW ---
    def load_dashboard():
        nonlocal all_documents
        
        # Connect file picker callbacks
        file_picker.on_result = handle_file_import
        file_picker.on_upload = handle_file_upload
        search_field.on_change = lambda e: update_table_view()
        type_filter.on_change = lambda e: update_table_view()
        status_filter.on_change = lambda e: update_table_view()
        
        # Initial population of table
        update_table_view()
        
        page.clean()
        page.horizontal_alignment = ft.CrossAxisAlignment.START
        page.vertical_alignment = ft.MainAxisAlignment.START
        page.add(
            ft.Column([
                ft.Row([
                    ft.Icon(ft.icons.ACCOUNT_BALANCE, size=40, color=ft.colors.BLUE_800),
                    ft.Text("LGU Tolosa - Sangguniang Bayan Tracking Dashboard", size=26, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_800),
                    ft.Container(expand=True),
                    ft.Text(f"Logged in as: {current_user}", size=14, italic=True),
                    ft.IconButton(icon=ft.icons.LOGOUT, on_click=lambda e: logout_user())
                ], alignment=ft.MainAxisAlignment.START),
                ft.Divider(height=10, thickness=2),
                ft.Text("Register New Proposed Resolution / Ordinance", size=18, weight=ft.FontWeight.W_600),
                ft.Row([title_input, import_button]),
                ft.Row([type_dropdown, committee_input, submit_button]),
                ft.Container(height=20),
                ft.Text("Active Legislative Document Records Tracker", size=18, weight=ft.FontWeight.W_600),
                ft.Row([search_field, type_filter, status_filter], spacing=15),
                ft.Container(height=10),
                data_table
            ], spacing=20)
        )
        page.update()

    def logout_user():
        nonlocal current_user
        current_user = None
        show_login()

    # --- LOGIN SCREEN ---
    def show_login():
        page.clean()
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER
        
        username_field = ft.TextField(label="Username", width=300, icon=ft.icons.PERSON)
        password_field = ft.TextField(label="Password", width=300, password=True, can_reveal_password=True, icon=ft.icons.LOCK)
        
        def attempt_login(e):
            nonlocal current_user
            if not username_field.value or not password_field.value:
                page.snack_bar = ft.SnackBar(ft.Text("Please fill out both fields."), open=True)
                page.update()
                return

            try:
                params = {"username": username_field.value, "password": password_field.value}
                res = requests.post(f"{BACKEND_URL}/auth/login", params=params, verify=False)
                
                if res.status_code == 200:
                    current_user = res.json()["username"]
                    load_dashboard()
                else:
                    page.snack_bar = ft.SnackBar(ft.Text("Invalid credentials."), open=True)
                    page.update()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Connection Failed: Ensure Backend is running. {ex}"), open=True)
                page.update()

        login_btn = ft.ElevatedButton("Log In", width=300, on_click=attempt_login, bgcolor=ft.colors.BLUE_800, color=ft.colors.WHITE)
        signup_link = ft.TextButton("Don't have an account? Sign Up", on_click=lambda e: show_signup())

        page.add(
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.icons.ACCOUNT_BALANCE, size=50, color=ft.colors.BLUE_800),
                        ft.Text("LGU Tolosa - Sangguniang Bayan", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_800),
                        ft.Text("Legislative Tracking System Login", size=14, color=ft.colors.GREY_600),
                        ft.Container(height=10),
                        username_field,
                        password_field,
                        ft.Container(height=10),
                        login_btn,
                        signup_link
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=40,
                    width=380,
                    alignment=ft.alignment.center
                )
            )
        )
        page.update()

    # --- SIGN UP SCREEN (NEW FEATURE) ---
    def show_signup():
        page.clean()
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER

        reg_username = ft.TextField(label="Desired Username", width=300, icon=ft.icons.PERSON_ADD)
        reg_password = ft.TextField(label="Password", width=300, password=True, can_reveal_password=True, icon=ft.icons.LOCK_OUTLINE)
        reg_confirm_password = ft.TextField(label="Confirm Password", width=300, password=True, can_reveal_password=True, icon=ft.icons.LOCK)

        def attempt_signup(e):
            if not reg_username.value or not reg_password.value or not reg_confirm_password.value:
                page.snack_bar = ft.SnackBar(ft.Text("Please fill out all registration fields."), open=True)
                page.update()
                return

            if reg_password.value != reg_confirm_password.value:
                page.snack_bar = ft.SnackBar(ft.Text("Passwords do not match!"), open=True)
                page.update()
                return

            try:
                params = {"username": reg_username.value, "password": reg_password.value}
                res = requests.post(f"{BACKEND_URL}/auth/register", params=params, verify=False)

                if res.status_code == 200:
                    page.snack_bar = ft.SnackBar(ft.Text("Account created successfully! You can now log in."), open=True)
                    show_login()
                else:
                    error_msg = res.json().get("detail", "Registration failed.")
                    page.snack_bar = ft.SnackBar(ft.Text(f"Error: {error_msg}"), open=True)
                    page.update()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Connection Failed: Ensure Backend is running. {ex}"), open=True)
                page.update()

        register_btn = ft.ElevatedButton("Register Account", width=300, on_click=attempt_signup, bgcolor=ft.colors.GREEN_700, color=ft.colors.WHITE)
        back_to_login = ft.TextButton("Already have an account? Log In", on_click=lambda e: show_login())

        page.add(
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.icons.PERSON_ADD, size=50, color=ft.colors.GREEN_700),
                        ft.Text("Create Administrator Account", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700),
                        ft.Text("Sangguniang Bayan Registry", size=14, color=ft.colors.GREY_600),
                        ft.Container(height=10),
                        reg_username,
                        reg_password,
                        reg_confirm_password,
                        ft.Container(height=10),
                        register_btn,
                        back_to_login
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=40,
                    width=380,
                    alignment=ft.alignment.center
                )
            )
        )
        page.update()

    # Initial boot stage starts at Login
    show_login()

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, upload_dir=UPLOAD_DIR)