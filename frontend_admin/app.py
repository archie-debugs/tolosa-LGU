import flet as ft
import requests
import base64
import io
import os
import sys
import asyncio
import time
import urllib3
import qrcode
import json
from flet_runtime.uploads import build_upload_url
from urllib.parse import quote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Use the default Windows Proactor event loop policy so Flet can launch the desktop app subprocess.
# The selector policy prevents asyncio subprocess creation on Windows in this environment.
# if sys.platform == 'win32':
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
cert_file = os.path.join(project_root, "scanner.crt")
key_file = os.path.join(project_root, "scanner.key")
local_backend_default = "https://127.0.0.1:8001" if os.path.exists(cert_file) and os.path.exists(key_file) else "http://127.0.0.1:8001"
BACKEND_URL = os.getenv("BACKEND_URL", local_backend_default)
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", BACKEND_URL)
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
UPLOAD_SECRET_KEY = os.getenv("FLET_SECRET_KEY", "sb_tolosa_tracking_secret")
DEFAULT_WORKFLOW_STEPS = [
    "Draft",
    "First Reading",
    "Committee Referral",
    "Public Hearing",
    "Second Reading",
    "Third/Final Reading",
    "Transmitted to Mayor",
    "Approved/Vetoed",
    "Published/Enacted",
]

COMMITTEES = [
    {"name": "Committee on Finance, Budget and Appropriation"},
    {"name": "Committee on Rules, Ordinances, Public Accountability and Good Government"},
    {"name": "Committee on Agriculture"},
    {"name": "Committee on Health"},
    {"name": "Committee on Education, Culture and Arts"},
    {"name": "Committee on Information and Communications Technology (ICT)"},
    {"name": "Committee on Social Services"},
    {"name": "Committee on Public Works and Infrastructures"},
    {"name": "Committee on Women, Children and Family Care"},
    {"name": "Committee on Tourism"},
    {"name": "Committee on Trade and Industry"},
    {"name": "Committee on Youth and Sports Development"},
    {"name": "Committee on Police, Fire, Public Safety and Human Rights"},
    {"name": "Committee on Ways and Means"},
    {"name": "Committee on Market and Slaughterhouse"},
    {"name": "Committee on Personnel"},
    {"name": "Committee on Labor and Employment Policies"},
    {"name": "Committee on Environment Protection and Sanitation"},
    {"name": "Committee on Cooperatives, Entrepreneurship and Livelihood Development"},
    {"name": "Committee on Barangay Affairs"},
    {"name": "Committee on General Services"},
    {"name": "Committee on Games and Amusement"},
    {"name": "Committee on Public Utilities, Transportation, Communication and Public Information"},
    {"name": "Land Use and Housing Committee"},
    {"name": "Committee on Disaster Risk Reduction Management"},
]

# Persist committees to a JSON file so edits survive restarts
committees_file = os.path.join(project_root, "committees.json")

def load_committees_from_file():
    try:
        if os.path.exists(committees_file):
            with open(committees_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    # normalize to list of dicts with 'name'
                    out = []
                    for item in data:
                        if isinstance(item, dict) and item.get("name"):
                            out.append({"name": str(item.get("name"))})
                        elif isinstance(item, str):
                            out.append({"name": item})
                    if out:
                        return out
    except Exception:
        pass
    return COMMITTEES

def save_committees_to_file(committees):
    try:
        with open(committees_file, "w", encoding="utf-8") as fh:
            json.dump(committees, fh, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

# Override default with persisted list when available
COMMITTEES = load_committees_from_file()

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
    # Subtle neutral background for modern look
    page.bgcolor = ft.colors.BLUE_GREY_100
    page.scroll = ft.ScrollMode.AUTO
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START
    # Use minimal outer padding so content can fill viewport cleanly
    page.padding = 8

    # Current User Session State
    current_user = None
    
    # Data storage for all documents
    all_documents = []
    pending_upload_filename = None
    last_uploaded_filename = None
    workflow_steps = list(DEFAULT_WORKFLOW_STEPS)
    workflow_editor_column = ft.Column(spacing=10)
    workflow_notice = ft.Text("", size=12, color=ft.colors.BLUE_GREY_600)
    workflow_summary = ft.Text("", size=12, color=ft.colors.BLUE_GREY_600)
    users_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Username", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Role", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )
    user_username_input = ft.TextField(label="Username", width=280)
    user_password_input = ft.TextField(label="Password", width=280, password=True, can_reveal_password=True)
    user_role_input = ft.Dropdown(
        label="Role",
        width=220,
        options=[
            ft.dropdown.Option("Admin"),
            ft.dropdown.Option("Secretariat"),
            ft.dropdown.Option("SB Member"),
            ft.dropdown.Option("Mayor's Office"),
        ],
        value="Admin",
    )
    users_notice = ft.Text("", size=12, color=ft.colors.BLUE_GREY_600)
    pending_delete_user = None
    scan_office_dropdown = ft.Dropdown(
        label="Receiving Office",
        width=300,
        options=[
            ft.dropdown.Option("Records Registry"),
            ft.dropdown.Option("Secretariat"),
            ft.dropdown.Option("Mayor's Office"),
            ft.dropdown.Option("Committee Chair"),
            ft.dropdown.Option("Committee Hearing Room"),
            ft.dropdown.Option("Session Hall"),
            ft.dropdown.Option("Legal Office"),
        ],
        value="Secretariat",
    )
    scan_input = ft.TextField(
        label="Scan QR Document UUID",
        hint_text="Scan document QR code and press Enter",
        width=420,
        autofocus=True,
        on_submit=lambda e: process_receive_scan(e),
    )
    scan_notice = ft.Text("Ready to receive scans.", size=12, color=ft.colors.BLUE_GREY_600)
    scan_success_banner = ft.Container(visible=False, content=ft.Text(""))
    scan_document_dropdown = ft.Dropdown(label="Selected Document", width=520, options=[], on_change=lambda e: load_document_timeline(scan_document_dropdown.value))
    timeline_summary = ft.Text("Select a document to see its movement timeline.", size=13, color=ft.colors.BLUE_GREY_600)
    timeline_column = ft.Column(spacing=10)

    def refresh_display_ids():
        def sort_key(doc):
            try:
                return int(doc.get("id", 0))
            except Exception:
                return 0

        all_documents.sort(key=sort_key)
        for index, doc in enumerate(all_documents, start=1):
            doc["display_id"] = index

    def refresh_user_display_ids(users):
        users.sort(key=lambda user: int(user.get("id", 0) or 0))
        for index, user in enumerate(users, start=1):
            user["display_id"] = index

    def build_qr_code_base64(text: str):
        qr = qrcode.QRCode(version=1, box_size=8, border=4)
        qr.add_data(text)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def load_documents_from_backend(show_notice: bool = False):
        nonlocal all_documents
        try:
            response = requests.get(f"{BACKEND_URL}/legislative/list", verify=False)
            if response.status_code == 200:
                payload = response.json()
                all_documents = payload.get("items", [])
                refresh_display_ids()
                if show_notice:
                    scan_notice.value = f"Loaded {len(all_documents)} documents."
            elif show_notice:
                scan_notice.value = f"Document load failed: {response.text}"
        except Exception as exc:
            if show_notice:
                scan_notice.value = f"Document load error: {exc}"

    def refresh_scan_document_options(selected_uuid: str | None = None):
        options = []
        for doc in all_documents:
            label = f"{doc.get('display_id', doc.get('id', '-'))}. {doc.get('title', 'Untitled')}"
            options.append(ft.dropdown.Option(key=doc.get("uuid", ""), text=label))

        scan_document_dropdown.options = options

        if selected_uuid:
            scan_document_dropdown.value = selected_uuid if any(option.key == selected_uuid for option in options) else None
        elif scan_document_dropdown.value not in [option.key for option in options]:
            scan_document_dropdown.value = options[0].key if options else None

    def render_timeline_entry(entry: dict):
        timestamp_text = entry.get("timestamp", "")
        display_time = timestamp_text.replace("T", " ")[:19] if timestamp_text else "Unknown time"
        return ft.Container(
            padding=14,
            border_radius=16,
            bgcolor=ft.colors.BLUE_GREY_50,
            content=ft.Row(
                [
                    ft.Container(
                        width=12,
                        height=12,
                        border_radius=6,
                        bgcolor=ft.colors.BLUE_700,
                    ),
                    ft.Column(
                        [
                            ft.Text(f"{entry.get('previous_location', 'Records Registry')} → {entry.get('new_location', 'Unknown')}", weight=ft.FontWeight.BOLD),
                            ft.Text(f"Received by {entry.get('receiving_office', '-')}", size=12, color=ft.colors.BLUE_GREY_700),
                            ft.Text(f"{display_time} • {entry.get('logged_in_user', 'system')}", size=11, color=ft.colors.BLUE_GREY_500),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        )

    def load_document_timeline(tracking_uuid: str | None):
        if not tracking_uuid:
            timeline_summary.value = "Select a document to see its movement timeline."
            timeline_column.controls = []
            page.update()
            return

        try:
            response = requests.get(f"{BACKEND_URL}/documents/history/{quote(tracking_uuid)}", verify=False)
            if response.status_code == 200:
                payload = response.json()
                document = payload.get("document", {})
                history_items = payload.get("items", [])
                title = document.get("title", "Untitled Document")
                current_location = document.get("current_location", "Records Registry")
                timeline_summary.value = f"{title} is currently at {current_location}."

                if history_items:
                    timeline_column.controls = [render_timeline_entry(entry) for entry in history_items]
                else:
                    timeline_column.controls = [
                        ft.Container(
                            padding=14,
                            border_radius=16,
                            bgcolor=ft.colors.BLUE_GREY_50,
                            content=ft.Text("No scan history yet for this document."),
                        )
                    ]
            else:
                timeline_summary.value = f"Timeline load failed: {response.text}"
                timeline_column.controls = []
        except Exception as exc:
            timeline_summary.value = f"Timeline load error: {exc}"
            timeline_column.controls = []

        page.update()

    def refocus_scan_input():
        try:
            scan_input.focus()
        except Exception:
            pass

    def process_receive_scan(e=None):
        tracking_uuid = (scan_input.value or "").strip()
        if not tracking_uuid:
            scan_notice.value = "Scan a document QR code first."
            page.update()
            refocus_scan_input()
            return

        receiving_office = scan_office_dropdown.value or "Records Registry"
        try:
            response = requests.post(
                f"{BACKEND_URL}/documents/receive/{quote(tracking_uuid)}",
                params={
                    "receiving_office": receiving_office,
                    "logged_in_user": current_user or "system",
                },
                verify=False,
            )
            if response.status_code == 200:
                payload = response.json()
                document_title = payload.get("document_title", tracking_uuid)
                previous_location = payload.get("previous_location", "Unknown")
                new_location = payload.get("new_location", receiving_office)

                for doc in all_documents:
                    if doc.get("uuid") == tracking_uuid:
                        doc["current_location"] = new_location
                        break

                scan_success_banner.content = ft.Container(
                    padding=16,
                    border_radius=18,
                    bgcolor=ft.colors.GREEN_100,
                    content=ft.Row(
                        [
                            ft.Icon(ft.icons.CHECK_CIRCLE, color=ft.colors.GREEN_700),
                            ft.Column(
                                [
                                    ft.Text(f"{document_title}", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_900),
                                    ft.Text(f"{previous_location} → {new_location}", color=ft.colors.GREEN_900),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
                scan_success_banner.visible = True
                scan_notice.value = f"Scanned by {current_user or 'system'} for {receiving_office}."
                load_documents_from_backend()
                refresh_scan_document_options(tracking_uuid)
                scan_document_dropdown.value = tracking_uuid
                load_document_timeline(tracking_uuid)
                update_table_view()
                scan_input.value = ""
                page.update()
                refocus_scan_input()
                return

            scan_notice.value = f"Receive failed: {response.text}"
        except Exception as exc:
            scan_notice.value = f"Receive error: {exc}"

        page.update()
        refocus_scan_input()

    def surface_card(content, width=None, padding=24, expand=False):
        return ft.Container(
            content=content,
            width=width,
            expand=expand,
            padding=padding,
            bgcolor=ft.colors.WHITE,
            border_radius=24,
        )

    def section_header(title, subtitle, icon, accent_color):
        return ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, color=accent_color, size=24),
                    padding=10,
                    bgcolor=ft.colors.BLUE_GREY_50,
                    border_radius=14,
                ),
                ft.Column(
                    [
                        ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
                        ft.Text(subtitle, size=13, color=ft.colors.BLUE_GREY_600),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

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

    def sync_status_filter_options():
        status_filter.options = [ft.dropdown.Option("All")] + [ft.dropdown.Option(step) for step in workflow_steps]
        if status_filter.value not in ["All", *workflow_steps]:
            status_filter.value = "All"

    def refresh_workflow_summary():
        if workflow_steps:
            workflow_summary.value = "Current lifecycle: " + " → ".join(workflow_steps)
        else:
            workflow_summary.value = "No workflow steps configured yet."

    def next_workflow_step_label():
        base_label = "New Milestone"
        existing_labels = {str(step).strip().lower() for step in workflow_steps}
        if base_label.lower() not in existing_labels:
            return base_label

        suffix = 2
        while f"{base_label} {suffix}".lower() in existing_labels:
            suffix += 1
        return f"{base_label} {suffix}"

    def rebuild_workflow_editor():
        workflow_editor_column.controls = []
        if not workflow_steps:
            workflow_editor_column.controls.append(
                ft.Container(
                    padding=16,
                    border_radius=16,
                    bgcolor=ft.colors.BLUE_GREY_50,
                    content=ft.Text("No steps yet. Add a milestone to start building the workflow."),
                )
            )
            refresh_workflow_summary()
            return

        for index, step in enumerate(workflow_steps):
            workflow_editor_column.controls.append(
                ft.Container(
                    padding=14,
                    border_radius=16,
                    bgcolor=ft.colors.BLUE_GREY_50,
                    content=ft.Row(
                        [
                            ft.Container(
                                width=38,
                                height=38,
                                alignment=ft.alignment.center,
                                border_radius=12,
                                bgcolor=ft.colors.WHITE,
                                content=ft.Text(str(index + 1), weight=ft.FontWeight.BOLD),
                            ),
                            ft.TextField(
                                label=f"Milestone {index + 1}",
                                value=step,
                                expand=True,
                                on_change=lambda e, idx=index: update_workflow_step(idx, e.control.value),
                            ),
                            ft.IconButton(
                                icon=ft.icons.ARROW_UPWARD,
                                tooltip="Move up",
                                on_click=lambda e, idx=index: move_workflow_step(idx, -1),
                            ),
                            ft.IconButton(
                                icon=ft.icons.ARROW_DOWNWARD,
                                tooltip="Move down",
                                on_click=lambda e, idx=index: move_workflow_step(idx, 1),
                            ),
                            ft.IconButton(
                                icon=ft.icons.DELETE_OUTLINE,
                                tooltip="Remove milestone",
                                icon_color=ft.colors.RED_700,
                                on_click=lambda e, idx=index: remove_workflow_step(idx),
                            ),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        refresh_workflow_summary()

    def update_workflow_step(index: int, value: str):
        if 0 <= index < len(workflow_steps):
            workflow_steps[index] = value.strip()
            refresh_workflow_summary()

    def add_workflow_step(e=None):
        workflow_steps.append(next_workflow_step_label())
        rebuild_workflow_editor()
        page.update()

    def remove_workflow_step(index: int):
        if 0 <= index < len(workflow_steps):
            workflow_steps.pop(index)
            rebuild_workflow_editor()
            page.update()

    def move_workflow_step(index: int, direction: int):
        target_index = index + direction
        if 0 <= index < len(workflow_steps) and 0 <= target_index < len(workflow_steps):
            workflow_steps[index], workflow_steps[target_index] = workflow_steps[target_index], workflow_steps[index]
            rebuild_workflow_editor()
            page.update()

    def load_workflow_config():
        nonlocal workflow_steps
        try:
            response = requests.get(f"{BACKEND_URL}/workflow/config", verify=False)
            if response.status_code == 200:
                payload = response.json()
                workflow_steps = payload.get("statuses", list(DEFAULT_WORKFLOW_STEPS)) or list(DEFAULT_WORKFLOW_STEPS)
        except Exception:
            workflow_steps = list(DEFAULT_WORKFLOW_STEPS)

        sync_status_filter_options()
        rebuild_workflow_editor()

    def save_workflow_config(e=None):
        cleaned_steps = [step.strip() for step in workflow_steps if str(step).strip()]
        if not cleaned_steps:
            workflow_notice.value = "Add at least one milestone before saving."
            page.update()
            return

        try:
            response = requests.put(
                f"{BACKEND_URL}/workflow/config",
                json={"statuses": cleaned_steps},
                verify=False,
            )
            if response.status_code == 200:
                payload = response.json()
                workflow_steps[:] = payload.get("statuses", cleaned_steps)
                sync_status_filter_options()
                rebuild_workflow_editor()
                workflow_notice.value = "Workflow saved successfully."
            else:
                workflow_notice.value = f"Save failed: {response.text}"
        except Exception as exc:
            workflow_notice.value = f"Save error: {exc}"

        page.update()

    def reset_workflow_config(e=None):
        try:
            response = requests.post(f"{BACKEND_URL}/workflow/reset", verify=False)
            if response.status_code == 200:
                payload = response.json()
                workflow_steps[:] = payload.get("statuses", list(DEFAULT_WORKFLOW_STEPS))
                sync_status_filter_options()
                rebuild_workflow_editor()
                workflow_notice.value = "Workflow reset to the default milestone sequence."
            else:
                workflow_notice.value = f"Reset failed: {response.text}"
        except Exception as exc:
            workflow_notice.value = f"Reset error: {exc}"

        page.update()

    audit_logs_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Time", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Actor", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Action", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Target", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Details", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )
    
    data_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Title", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Type", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Committee", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Current Location", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Current Status", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Milestone Path", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD)),
        ],
        rows=[]
    )

    qr_dialog = ft.AlertDialog(
        title=ft.Text("Generated Legislative QR Code"),
        content=ft.Container(alignment=ft.alignment.center, width=250, height=250)
    )
    page.overlay.append(qr_dialog)

    preview_dialog = ft.AlertDialog(
        title=ft.Text("Document Preview"),
        content=ft.Container(width=700, height=500)
    )

    delete_dialog = ft.AlertDialog(
        title=ft.Text("Delete Legislative Record"),
        content=ft.Text(""),
        actions=[],
    )
    page.overlay.append(delete_dialog)
    pending_delete_doc = None
    pending_delete_user = None

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
            else:
                message = response.text or f"Status {response.status_code}"
                page.snack_bar = ft.SnackBar(ft.Text(f"QR load failed: {message}"), open=True)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Connection error: {ex}"), open=True)
        finally:
            page.update()

    def _doc_print(e, doc):
        # Build a printable HTML and open it in a new tab which triggers print
        html = f"""<!doctype html><html><head><meta charset='utf-8'><title>{doc['title']}</title></head><body><h1>{doc['title']}</h1><p><strong>Type:</strong> {doc['type']}</p><p><strong>Committee:</strong> {doc['committee']}</p><p><strong>Status:</strong> {doc['status']}</p><p><strong>UUID:</strong> {doc['uuid']}</p><script>window.onload=function(){{window.print();}};</script></body></html>"""
        data = base64.b64encode(html.encode('utf-8')).decode('utf-8')
        url = f"data:text/html;base64,{data}"
        page.launch_url(url)

    def _doc_preview(e, doc):
        src = doc.get("source_filename")
        if not src:
            page.snack_bar = ft.SnackBar(ft.Text("No uploaded source file available for preview."), open=True)
            page.update()
            return

        # If PDF, open preview endpoint in browser tab for inline rendering
        if src.lower().endswith('.pdf'):
            page.launch_url(f"{BACKEND_URL}/legislative/preview/{quote(src)}")
            return

        # For DOCX, request extracted text from backend preview endpoint and show in dialog
        try:
            resp = requests.get(f"{BACKEND_URL}/legislative/preview/{quote(src)}", verify=False)
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("text", "")
                preview_dialog.content = ft.Container(
                    ft.Column([
                        ft.Text(doc.get("title", ""), weight=ft.FontWeight.BOLD),
                        ft.Divider(),
                        ft.Text(text)
                    ], tight=True, scroll=ft.ScrollMode.AUTO),
                    width=700, height=500
                )
                page.overlay.append(preview_dialog)
                preview_dialog.open = True
                page.update()
                return

        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Preview failed: {exc}"), open=True)
            page.update()
            return

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

    def advance_document_status(doc):
        try:
            response = requests.post(
                f"{BACKEND_URL}/legislative/advance/{quote(doc['uuid'])}",
                params={"actor": current_user or "system", "location": "Admin Dashboard"},
                verify=False,
            )
            if response.status_code == 200:
                payload = response.json()
                new_stage = payload.get("current_stage", doc.get("status", ""))
                doc["status"] = new_stage
                update_table_view()
                page.snack_bar = ft.SnackBar(ft.Text(payload.get("message", f"Advanced to {new_stage}")), open=True)
                page.update()
                return

            page.snack_bar = ft.SnackBar(ft.Text(f"Advance failed: {response.text}"), open=True)
            page.update()
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Advance error: {exc}"), open=True)
            page.update()

    def delete_document_record(doc):
        try:
            response = requests.delete(
                f"{BACKEND_URL}/legislative/delete/{quote(doc['uuid'])}",
                params={"actor": current_user or "system", "location": "Admin Dashboard"},
                verify=False,
            )
            if response.status_code == 200:
                all_documents[:] = [item for item in all_documents if item.get("uuid") != doc.get("uuid")]
                refresh_display_ids()
                update_table_view()
                page.snack_bar = ft.SnackBar(ft.Text(response.json().get("message", "Record deleted")), open=True)
                page.update()
                return

            page.snack_bar = ft.SnackBar(ft.Text(f"Delete failed: {response.text}"), open=True)
            page.update()
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Delete error: {exc}"), open=True)
            page.update()

    def load_users_table():
        try:
            response = requests.get(f"{BACKEND_URL}/auth/users", verify=False)
            if response.status_code == 200:
                users = response.json().get("items", [])
                refresh_user_display_ids(users)
                rows = []
                for user in users:
                    rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(str(user.get("display_id", user.get("id", "-"))))),
                                ft.DataCell(ft.Text(user.get("username", "-"))),
                                ft.DataCell(ft.Text(user.get("role", "Admin"))),
                                ft.DataCell(
                                    ft.PopupMenuButton(
                                        icon=ft.icons.MORE_VERT,
                                        tooltip="User actions",
                                        items=[
                                            ft.PopupMenuItem(text="Set Admin", on_click=lambda e, u=user: update_user_role(u, "Admin")),
                                            ft.PopupMenuItem(text="Set Secretariat", on_click=lambda e, u=user: update_user_role(u, "Secretariat")),
                                            ft.PopupMenuItem(text="Set SB Member", on_click=lambda e, u=user: update_user_role(u, "SB Member")),
                                            ft.PopupMenuItem(text="Set Mayor's Office", on_click=lambda e, u=user: update_user_role(u, "Mayor's Office")),
                                            ft.PopupMenuItem(text="Delete User", on_click=lambda e, u=user: confirm_delete_user(u)),
                                        ],
                                    )
                                ),
                            ]
                        )
                    )
                users_table.rows = rows
            else:
                users_table.rows = []
                users_notice.value = f"Load failed: {response.text}"
        except Exception as exc:
            users_table.rows = []
            users_notice.value = f"Load error: {exc}"

        page.update()

    def create_user_record(e=None):
        if not user_username_input.value or not user_password_input.value:
            users_notice.value = "Username and password are required."
            page.update()
            return

        try:
            response = requests.post(
                f"{BACKEND_URL}/auth/register",
                params={
                    "username": user_username_input.value.strip(),
                    "password": user_password_input.value,
                    "role": user_role_input.value or "Admin",
                },
                verify=False,
            )
            if response.status_code == 200:
                user_username_input.value = ""
                user_password_input.value = ""
                users_notice.value = "User created successfully."
                load_users_table()
            else:
                users_notice.value = f"Create failed: {response.text}"
        except Exception as exc:
            users_notice.value = f"Create error: {exc}"

        page.update()

    def update_user_role(user, role):
        try:
            response = requests.put(
                f"{BACKEND_URL}/auth/users/{quote(user['username'])}/role",
                params={"role": role},
                verify=False,
            )
            if response.status_code == 200:
                load_users_table()
                users_notice.value = response.json().get("message", "Role updated.")
            else:
                users_notice.value = f"Role update failed: {response.text}"
        except Exception as exc:
            users_notice.value = f"Role update error: {exc}"

        page.update()

    def delete_user_record(user):
        try:
            response = requests.delete(f"{BACKEND_URL}/auth/users/{quote(user['username'])}", verify=False)
            if response.status_code == 200:
                users_notice.value = response.json().get("message", "User deleted.")
                load_users_table()
            else:
                users_notice.value = f"Delete failed: {response.text}"
        except Exception as exc:
            users_notice.value = f"Delete error: {exc}"

        page.update()

    def confirm_delete_user(user):
        nonlocal pending_delete_user
        pending_delete_user = user
        delete_dialog.title = ft.Text("Delete User")
        delete_dialog.content = ft.Text(f"Delete user \"{user.get('username', 'this user')}\"? This cannot be undone.")
        delete_dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda e: close_delete_dialog()),
            ft.ElevatedButton("Delete", icon=ft.icons.DELETE_OUTLINE, bgcolor=ft.colors.RED_700, color=ft.colors.WHITE, on_click=lambda e: run_delete_user_action()),
        ]
        delete_dialog.open = True
        page.update()

    def run_delete_user_action():
        nonlocal pending_delete_user
        user = pending_delete_user
        close_delete_dialog()
        if user:
            delete_user_record(user)

    def confirm_delete_document(doc):
        nonlocal pending_delete_doc
        pending_delete_doc = doc
        delete_dialog.title = ft.Text("Delete Legislative Record")
        delete_dialog.content = ft.Text(f"Delete \"{doc.get('title', 'this record')}\"? This cannot be undone.")
        delete_dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda e: close_delete_dialog()),
            ft.ElevatedButton("Delete", icon=ft.icons.DELETE_OUTLINE, bgcolor=ft.colors.RED_700, color=ft.colors.WHITE, on_click=lambda e: run_delete_dialog_action()),
        ]
        delete_dialog.open = True
        page.update()

    def close_delete_dialog():
        nonlocal pending_delete_doc, pending_delete_user
        delete_dialog.open = False
        pending_delete_doc = None
        pending_delete_user = None
        page.update()

    def run_delete_dialog_action():
        nonlocal pending_delete_doc, pending_delete_user
        doc = pending_delete_doc
        user = pending_delete_user
        close_delete_dialog()
        if doc:
            delete_document_record(doc)
        elif user:
            delete_user_record(user)

    def workflow_step_index(step_name):
        normalized_step = str(step_name or "").strip().lower()
        for index, step in enumerate(workflow_steps):
            if str(step).strip().lower() == normalized_step:
                return index
        return -1

    def milestone_path_for_status(status):
        status_text = str(status or "").strip()
        if not workflow_steps:
            return status_text or "-"

        current_index = workflow_step_index(status_text)
        if current_index < 0:
            return status_text or "-"

        path_steps = [str(step).strip() for step in workflow_steps[: current_index + 1] if str(step).strip()]
        if not path_steps:
            return status_text or "-"

        numbered_steps = [f"{index + 1}. {step}" for index, step in enumerate(path_steps)]
        return " → ".join(numbered_steps)

    def build_document_row(doc):
        current_status = doc.get("status", "-")
        return ft.DataRow(
            cells=[
                ft.DataCell(ft.Text(str(doc.get("display_id", doc.get("id", "-"))))),
                ft.DataCell(ft.Text(doc["title"])),
                ft.DataCell(ft.Text(doc["type"])),
                ft.DataCell(ft.Text(doc["committee"])),
                ft.DataCell(ft.Text(doc.get("current_location", "Records Registry"))),
                ft.DataCell(ft.Text(current_status, color=ft.colors.BLUE)),
                ft.DataCell(
                    ft.Container(
                        content=ft.Text(
                            milestone_path_for_status(current_status),
                            size=12,
                            color=ft.colors.BLUE_GREY_700,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        width=180,
                    )
                ),
                ft.DataCell(document_action_buttons(doc)),
            ]
        )

    def document_action_buttons(doc):
        return ft.PopupMenuButton(
            icon=ft.icons.MORE_VERT,
            tooltip="Actions",
            items=[
                ft.PopupMenuItem(text="Get QR Code", on_click=lambda e, uid=doc["uuid"]: view_qr_code(e, uid)),
                ft.PopupMenuItem(text="Preview file", on_click=lambda e, d=doc: _doc_preview(e, d)),
                ft.PopupMenuItem(text="Print file", on_click=lambda e, d=doc: _doc_print(e, d)),
                ft.PopupMenuItem(text="Download file", on_click=lambda e, d=doc: _doc_download(e, d)),
                ft.PopupMenuItem(text="Advance status", on_click=lambda e, d=doc: advance_document_status(d)),
                ft.PopupMenuItem(text="Delete record", on_click=lambda e, d=doc: confirm_delete_document(d)),
            ],
        )

    def render_shell(title_text: str, subtitle_text: str, content_view):
        """Build the shared admin shell with a fixed header and a left navigation rail."""
        # Use flexible layout instead of a large fixed body height to avoid
        # extra blank space when the window is scrolled. The containers will
        # expand to the available space.
        body_height = max((page.window_height or 900) - 170, 520)

        header = ft.Container(
            padding=ft.padding.symmetric(vertical=12, horizontal=14),
            bgcolor=None,
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.icons.ACCOUNT_BALANCE, size=22, color=ft.colors.WHITE),
                        padding=10,
                        bgcolor=ft.colors.BLUE_800,
                        border_radius=10,
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "LGU Tolosa - Sangguniang Bayan",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=ft.colors.BLUE_900,
                            ),
                            ft.Text(
                                "Tracking Dashboard",
                                size=12,
                                color=ft.colors.BLUE_GREY_600,
                            ),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Text("Logged in as", size=11, color=ft.colors.BLUE_GREY_500),
                                        ft.Text(current_user or "-", size=13, weight=ft.FontWeight.W_600),
                                    ],
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                ),
                                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                bgcolor=ft.colors.WHITE,
                                border_radius=10,
                            ),
                            ft.IconButton(icon=ft.icons.LOGOUT, tooltip="Log out", on_click=lambda e: logout_user()),
                        ],
                        spacing=8,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
        )

        def switch_view(index: int):
            content_holder.controls.clear()
            if index == 0:
                content_holder.controls.append(registry_view())
            elif index == 1:
                content_holder.controls.append(committees_view())
            elif index == 2:
                content_holder.controls.append(users_roles_view())
            elif index == 3:
                content_holder.controls.append(audit_logs_view())
            else:
                content_holder.controls.append(settings_view())
            content_holder.update()
            page.update()

        def handle_nav_change(e):
            # Some Flet runtimes set the selected index on the event control,
            # others update the NavigationRail instance. Try both safely.
            try:
                idx = getattr(e.control, "selected_index", None)
            except Exception:
                idx = None

            if idx is None:
                try:
                    idx = getattr(nav, "selected_index", 0)
                except Exception:
                    idx = 0

            switch_view(idx if idx is not None else 0)

        # Compute a height for the main content card so it fills the viewport
        card_height = max((page.window_height or 900) - 160, 360)

        # Build a simple top-aligned navigation column and allow rebuilding
        selected_index = 0

        nav_container = ft.Column(spacing=12)

        def set_selected(idx: int):
            nonlocal selected_index
            selected_index = idx
            build_nav()
            switch_view(idx)

        def nav_item(icon, label, idx):
            is_selected = (idx == selected_index)
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, color=ft.colors.BLUE_800 if is_selected else ft.colors.BLUE_GREY_700),
                        ft.Container(width=8),
                        ft.Text(label, size=12, color=ft.colors.BLUE_800 if is_selected else ft.colors.BLUE_GREY_700),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.padding.symmetric(vertical=10, horizontal=12),
                width=200,
                bgcolor=ft.colors.BLUE_50 if is_selected else None,
                border_radius=10,
                on_click=lambda e, i=idx: set_selected(i),
            )

        def build_nav():
            nav_container.controls.clear()
            nav_container.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Icon(ft.icons.DASHBOARD, color=ft.colors.BLUE_800),
                                padding=8,
                                bgcolor=ft.colors.BLUE_50,
                                border_radius=12,
                            ),
                            ft.Text("Admin", size=12, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_900),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    padding=ft.padding.only(top=6, bottom=8),
                    alignment=ft.alignment.top_center,
                )
            )
            nav_container.controls.append(nav_item(ft.icons.LIST_ALT_OUTLINED, "Documents", 0))
            nav_container.controls.append(nav_item(ft.icons.GROUP_OUTLINED, "Committees", 1))
            nav_container.controls.append(nav_item(ft.icons.PEOPLE_OUTLINED, "Users & Roles", 2))
            nav_container.controls.append(nav_item(ft.icons.HISTORY_OUTLINED, "Audit Logs", 3))
            nav_container.controls.append(nav_item(ft.icons.SETTINGS_OUTLINED, "Settings", 4))

        build_nav()

        content_holder = ft.ListView(
            expand=True,
            spacing=12,
            padding=ft.padding.only(top=0, right=0, left=0, bottom=0),
        )
        content_holder.controls = [content_view]

        def load_audit_logs_view():
            try:
                response = requests.get(f"{BACKEND_URL}/audit/logs?limit=200", verify=False)
                if response.status_code == 200:
                    payload = response.json()
                    rows = []
                    for entry in payload.get("items", []):
                        target_label = "-"
                        if entry.get("target_type") or entry.get("target_id"):
                            target_label = f"{entry.get('target_type') or '-'} #{entry.get('target_id') or '-'}"

                        rows.append(
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(ft.Text((entry.get("created_at") or "").replace("T", " ")[:19])),
                                    ft.DataCell(ft.Text(entry.get("actor", "-"))),
                                    ft.DataCell(ft.Text(entry.get("action", "-"))),
                                    ft.DataCell(ft.Text(target_label)),
                                    ft.DataCell(ft.Text(entry.get("details") or "-")),
                                ]
                            )
                        )

                    audit_logs_table.rows = rows
                else:
                    audit_logs_table.rows = [
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text("-")),
                                ft.DataCell(ft.Text("-")),
                                ft.DataCell(ft.Text("Failed to load audit logs")),
                                ft.DataCell(ft.Text("-")),
                                ft.DataCell(ft.Text(response.text)),
                            ]
                        )
                    ]
            except Exception as exc:
                audit_logs_table.rows = [
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text("-")),
                            ft.DataCell(ft.Text("-")),
                            ft.DataCell(ft.Text("Load error")),
                            ft.DataCell(ft.Text("-")),
                            ft.DataCell(ft.Text(str(exc))),
                        ]
                    )
                ]

        def audit_logs_view():
            load_audit_logs_view()
            return ft.Column(
                [
                    surface_card(
                        ft.Column(
                            [
                                section_header(
                                    "Audit Logs",
                                    "System Activity & History Logs",
                                    ft.icons.HISTORY,
                                    ft.colors.ORANGE_700,
                                ),
                                ft.Divider(height=1),
                                ft.Container(
                                    content=audit_logs_table,
                                    bgcolor=ft.colors.BLUE_GREY_50,
                                    border_radius=18,
                                    padding=12,
                                ),
                            ],
                            spacing=16,
                        ),
                    )
                ],
                expand=True,
            )

        page.clean()
        page.horizontal_alignment = ft.CrossAxisAlignment.START
        page.vertical_alignment = ft.MainAxisAlignment.START
        page.add(
            ft.Column(
                [
                    header,
                    ft.Row(
                        [
                            ft.Container(
                                width=200,
                                padding=ft.padding.only(top=8, right=6),
                                content=nav_container,
                                bgcolor=None,
                                border_radius=12,
                                alignment=ft.alignment.top_center,
                            ),
                            ft.Container(
                                expand=True,
                                padding=ft.padding.only(top=8),
                                content=ft.Container(
                                    expand=True,
                                    padding=20,
                                    bgcolor=ft.colors.WHITE,
                                    border_radius=12,
                                    border=ft.border.all(1, ft.colors.BLUE_GREY_50),
                                    content=content_holder,
                                ),
                            ),
                        ],
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                ],
                spacing=16,
                expand=True,
            )
        )

    def empty_state(title: str, subtitle: str, icon, accent_color):
        return ft.Container(
            expand=True,
            alignment=ft.alignment.center,
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(icon, size=54, color=accent_color),
                        padding=16,
                        bgcolor=ft.colors.BLUE_GREY_50,
                        border_radius=20,
                    ),
                    ft.Text(title, size=22, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_900),
                    ft.Text(subtitle, size=14, color=ft.colors.BLUE_GREY_600, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
        )

    def registry_view():
        return ft.Column(
            [
                surface_card(
                    ft.Column(
                        [
                            section_header(
                                "Documents",
                                "Active Legislative Tracker & Document Registration",
                                ft.icons.LIST_ALT,
                                ft.colors.BLUE_800,
                            ),
                            ft.Divider(height=1),
                            ft.Row([title_input, import_button], spacing=16),
                            ft.Row([type_dropdown, committee_input, submit_button], spacing=16),
                            ft.Container(height=6),
                            ft.Row([search_field, type_filter, status_filter], spacing=15),
                            ft.Container(height=4),
                            ft.Container(
                                content=data_table,
                                bgcolor=ft.colors.BLUE_GREY_50,
                                border_radius=18,
                                padding=12,
                            ),
                        ],
                        spacing=16,
                    ),
                )
            ],
            expand=True,
        )

    # --- Committees editing helpers ---
    committee_edit_index = None

    committee_name_input = ft.TextField(label="Committee Name", width=420)

    committee_edit_dialog = ft.AlertDialog(
        title=ft.Text("Edit Committee"),
        content=ft.Column([
            committee_name_input,
        ]),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: close_committee_dialog()),
            ft.ElevatedButton("Save", on_click=lambda e: on_committee_save()),
        ],
    )
    page.overlay.append(committee_edit_dialog)

    pending_delete_committee = None
    delete_committee_dialog = ft.AlertDialog(
        title=ft.Text("Delete Committee"),
        content=ft.Text("Are you sure you want to delete this committee?"),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: close_delete_committee_dialog()),
            ft.ElevatedButton("Delete", bgcolor=ft.colors.RED_600, color=ft.colors.WHITE, on_click=lambda e: delete_committee_action()),
        ],
    )
    page.overlay.append(delete_committee_dialog)

    def open_committee_dialog(index: int | None):
        nonlocal committee_edit_index
        committee_edit_index = index
        if index is None:
            committee_name_input.value = ""
            committee_edit_dialog.title.value = "Add Committee"
        else:
            committee_name_input.value = COMMITTEES[index]["name"]
            committee_edit_dialog.title.value = "Edit Committee"
        committee_edit_dialog.open = True
        page.update()

    def close_committee_dialog():
        committee_edit_dialog.open = False
        page.update()

    def on_committee_save():
        nonlocal committee_edit_index
        name = (committee_name_input.value or "").strip()
        if not name:
            return
        if committee_edit_index is None:
            COMMITTEES.append({"name": name})
        else:
            COMMITTEES[committee_edit_index]["name"] = name
        save_committees_to_file(COMMITTEES)
        committee_edit_dialog.open = False
        page.update()

    def confirm_delete_committee(index: int):
        nonlocal pending_delete_committee
        pending_delete_committee = index
        delete_committee_dialog.open = True
        page.update()

    def delete_committee_action():
        nonlocal pending_delete_committee
        try:
            if pending_delete_committee is not None and 0 <= pending_delete_committee < len(COMMITTEES):
                COMMITTEES.pop(pending_delete_committee)
                save_committees_to_file(COMMITTEES)
        finally:
            pending_delete_committee = None
            delete_committee_dialog.open = False
            page.update()

    def close_delete_committee_dialog():
        nonlocal pending_delete_committee
        pending_delete_committee = None
        delete_committee_dialog.open = False
        page.update()

    def committees_view():
        # Build rows with Edit/Delete actions
        committee_rows = []
        for index, committee in enumerate(COMMITTEES):
            committee_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(index + 1))),
                        ft.DataCell(ft.Text(committee["name"])),
                        ft.DataCell(
                            ft.Row(
                                [
                                    ft.IconButton(ft.icons.EDIT, tooltip="Edit", on_click=lambda e, idx=index: open_committee_dialog(idx)),
                                    ft.IconButton(ft.icons.DELETE, tooltip="Delete", on_click=lambda e, idx=index: confirm_delete_committee(idx)),
                                ],
                                spacing=4,
                            )
                        ),
                    ]
                )
            )

        committee_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("#", weight=ft.FontWeight.BOLD, size=12)),
                ft.DataColumn(ft.Text("Committee", weight=ft.FontWeight.BOLD, size=12)),
                ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD, size=12)),
            ],
            rows=committee_rows,
            column_spacing=12,
        )

        return ft.Column(
            [
                surface_card(
                    ft.Column(
                        [
                            section_header(
                                "Committees",
                                "Reference list of SB committee assignments and organization.",
                                ft.icons.GROUP,
                                ft.colors.GREEN_700,
                            ),
                            ft.Divider(height=1),
                            ft.Row([
                                ft.Text(
                                    "These are the standing committee names used for document assignment and reporting.",
                                    size=13,
                                    color=ft.colors.BLUE_GREY_600,
                                ),
                                ft.ElevatedButton("Add Committee", icon=ft.icons.ADD, on_click=lambda e: open_committee_dialog(None)),
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ft.Container(
                                content=committee_table,
                                bgcolor=ft.colors.BLUE_GREY_50,
                                border_radius=18,
                                padding=12,
                            ),
                        ],
                        spacing=14,
                    ),
                )
            ],
            expand=True,
        )

    def scan_receive_view():
        refresh_scan_document_options(scan_document_dropdown.value)
        if not scan_document_dropdown.value and scan_document_dropdown.options:
            scan_document_dropdown.value = scan_document_dropdown.options[0].key
        load_document_timeline(scan_document_dropdown.value)
        return ft.Column(
            [
                surface_card(
                    ft.Column(
                        [
                            section_header(
                                "Scan & Receive Document",
                                "Use a QR scanner or paste a UUID to move a document between offices.",
                                ft.icons.QR_CODE_SCANNER,
                                ft.colors.TEAL_700,
                            ),
                            ft.Divider(height=1),
                            ft.Row([scan_office_dropdown, scan_input], spacing=16, wrap=True),
                            scan_notice,
                            scan_success_banner,
                            ft.Container(
                                padding=16,
                                border_radius=18,
                                bgcolor=ft.colors.BLUE_GREY_50,
                                content=ft.Row(
                                    [
                                        ft.Column(
                                            [
                                                ft.Text("Phone Scanner Access", size=18, weight=ft.FontWeight.BOLD),
                                                ft.Text(
                                                    "Open the mobile scanner on a phone, log in first, then scan the document QR code that is already generated.",
                                                    size=13,
                                                    color=ft.colors.BLUE_GREY_600,
                                                ),
                                                ft.ElevatedButton(
                                                    "Open Mobile Scanner",
                                                    icon=ft.icons.PHONE_ANDROID,
                                                    on_click=lambda e: page.launch_url(f"{BACKEND_PUBLIC_URL}/scanner/mobile?api_base={quote(BACKEND_PUBLIC_URL)}"),
                                                ),
                                            ],
                                            spacing=10,
                                            expand=True,
                                        ),
                                    ],
                                    spacing=18,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            ),
                            ft.Text("Movement Timeline", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text("Select a document to review its received-at history.", size=13, color=ft.colors.BLUE_GREY_600),
                            scan_document_dropdown,
                            timeline_summary,
                            ft.Container(
                                content=timeline_column,
                                bgcolor=ft.colors.BLUE_GREY_50,
                                border_radius=18,
                                padding=12,
                            ),
                        ],
                        spacing=14,
                    ),
                )
            ],
            expand=True,
        )

    def users_roles_view():
        load_users_table()
        return ft.Column(
            [
                surface_card(
                    ft.Column(
                        [
                            section_header(
                                "Users & Roles",
                                "Create accounts, set roles, and remove users from the system.",
                                ft.icons.PEOPLE,
                                ft.colors.INDIGO_700,
                            ),
                            ft.Divider(height=1),
                            ft.Row([user_username_input, user_password_input, user_role_input], spacing=12, wrap=True),
                            ft.Row([ft.ElevatedButton("Create User", icon=ft.icons.PERSON_ADD, on_click=create_user_record)], spacing=12),
                            users_notice,
                            ft.Container(
                                content=users_table,
                                bgcolor=ft.colors.BLUE_GREY_50,
                                border_radius=18,
                                padding=12,
                            ),
                        ],
                        spacing=14,
                    ),
                )
            ],
            expand=True,
        )

    def settings_view():
        rebuild_workflow_editor()
        return ft.Column(
            [
                surface_card(
                    ft.Column(
                        [
                            section_header(
                                "Settings",
                                "Templates, municipality headers, backups, and configuration tools belong here.",
                                ft.icons.SETTINGS,
                                ft.colors.BLUE_GREY_700,
                            ),
                            ft.Divider(height=1),
                            ft.Text("Custom Status & Lifecycle Workflow Builder", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                "Configure the milestones used for legislative records, filtering, and default statuses.",
                                size=13,
                                color=ft.colors.BLUE_GREY_600,
                            ),
                            workflow_summary,
                            ft.Divider(height=1),
                            workflow_editor_column,
                            ft.Row(
                                [
                                    ft.OutlinedButton("Add Milestone", icon=ft.icons.ADD, on_click=add_workflow_step),
                                    ft.OutlinedButton("Reset Default Workflow", icon=ft.icons.REFRESH, on_click=reset_workflow_config),
                                    ft.ElevatedButton("Save Workflow", icon=ft.icons.SAVE, on_click=save_workflow_config),
                                ],
                                spacing=12,
                                wrap=True,
                            ),
                            workflow_notice,
                        ],
                        spacing=14,
                    ),
                )
            ],
            spacing=16,
        )

    # Copy metadata action removed by user request

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
                current_stage = result.get("current_stage", workflow_steps[0] if workflow_steps else "Draft")

                # Add to data storage (associate uploaded filename if any)
                all_documents.append({
                    "id": result.get("id", "-"),
                    "title": title_input.value,
                    "type": type_dropdown.value,
                    "committee": committee_input.value,
                    "current_location": result.get("current_location", "Records Registry"),
                    "status": current_stage,
                    "uuid": uuid_code,
                    "source_filename": last_uploaded_filename,
                })

                title_input.value = ""
                committee_input.value = ""
                page.snack_bar = ft.SnackBar(ft.Text("Legislative Document Registered Successfully!"), open=True)

                # clear last uploaded filename after associating with a record
                last_uploaded_filename = None

                refresh_display_ids()

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
                if str(doc.get("display_id", doc.get("id", ""))) == search_term:
                    data_table.rows.append(build_document_row(doc))
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
                location_match = search_term in str(doc.get("current_location", "")).lower()
                status_match = search_term in doc["status"].lower()
                uuid_match = search_term in doc["uuid"].lower()
                
                if not (title_match or type_match or committee_match or location_match or status_match or uuid_match):
                    continue
            
            # Add matching row to table
            data_table.rows.append(build_document_row(doc))
        
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
        load_workflow_config()

        load_documents_from_backend(show_notice=True)

        search_field.on_change = lambda e: update_table_view()
        type_filter.on_change = lambda e: update_table_view()
        status_filter.on_change = lambda e: update_table_view()
        
        # Initial population of table
        update_table_view()
        render_shell("Registry", "Active Legislative Tracker & Document Registration", registry_view())
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
            surface_card(
                ft.Column([
                    ft.Container(
                        content=ft.Icon(ft.icons.ACCOUNT_BALANCE, size=52, color=ft.colors.BLUE_800),
                        padding=14,
                        bgcolor=ft.colors.BLUE_GREY_50,
                        border_radius=20,
                    ),
                    ft.Text("LGU Tolosa - Sangguniang Bayan", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_900),
                    ft.Text("Legislative Tracking System Login", size=14, color=ft.colors.BLUE_GREY_600),
                    ft.Container(height=4),
                    username_field,
                    password_field,
                    ft.Container(height=6),
                    login_btn,
                    signup_link
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                width=420,
                padding=36,
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
            surface_card(
                ft.Column([
                    ft.Container(
                        content=ft.Icon(ft.icons.PERSON_ADD, size=52, color=ft.colors.GREEN_700),
                        padding=14,
                        bgcolor=ft.colors.GREEN_50,
                        border_radius=20,
                    ),
                    ft.Text("Create Administrator Account", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_800),
                    ft.Text("Sangguniang Bayan Registry", size=14, color=ft.colors.BLUE_GREY_600),
                    ft.Container(height=4),
                    reg_username,
                    reg_password,
                    reg_confirm_password,
                    ft.Container(height=6),
                    register_btn,
                    back_to_login
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                width=420,
                padding=36,
            )
        )
        page.update()

    # Initial boot stage starts at Login
    show_login()

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, upload_dir=UPLOAD_DIR)