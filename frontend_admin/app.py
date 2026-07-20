import flet as ft
import requests
import base64
import os
import sys
import asyncio
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Fix for Windows asyncio event loop bug on shutdown
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")

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

    def handle_file_import(e):
        """Handle document template import and auto-fill form fields"""
        if not file_picker.result or not file_picker.result.files:
            page.snack_bar = ft.SnackBar(ft.Text("No file selected."), open=True)
            page.update()
            return
        
        try:
            file_path = file_picker.result.files[0].path
            filename = os.path.basename(file_path)
            
            # Check file extension
            if not (filename.lower().endswith('.docx') or filename.lower().endswith('.pdf')):
                page.snack_bar = ft.SnackBar(ft.Text("Only .docx and .pdf files are supported."), open=True)
                page.update()
                return
            
            # Read file and send to backend
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f)}
                response = requests.post(f"{BACKEND_URL}/legislative/parse", files=files, verify=False)
            
            if response.status_code == 200:
                parsed_data = response.json()
                
                # Auto-fill form fields
                title_input.value = parsed_data.get("title", "")
                type_dropdown.value = parsed_data.get("item_type", "Ordinance")
                committee_input.value = parsed_data.get("committee", "")
                
                page.snack_bar = ft.SnackBar(
                    ft.Text("✓ Document template parsed successfully! Form auto-filled."),
                    open=True,
                    bgcolor=ft.colors.GREEN
                )
                page.update()
            else:
                error_msg = response.json().get("detail", "Unknown error")
                page.snack_bar = ft.SnackBar(ft.Text(f"Parse error: {error_msg}"), open=True)
                page.update()
        
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Error importing document: {str(ex)}"), open=True)
            page.update()

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
                result = response.json()
                uuid_code = result["tracking_uuid"]
                
                # Add to data storage
                all_documents.append({
                    "id": result.get("id", "-"),
                    "title": title_input.value,
                    "type": type_dropdown.value,
                    "committee": committee_input.value,
                    "status": "First Reading",
                    "uuid": uuid_code
                })
                
                title_input.value = ""
                committee_input.value = ""
                page.snack_bar = ft.SnackBar(ft.Text("Legislative Document Registered Successfully!"), open=True)
                
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
        
        for doc in all_documents:
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
                                    ft.ElevatedButton(
                                        "Get QR Code", 
                                        icon=ft.icons.QR_CODE,
                                        on_click=lambda e, uid=doc["uuid"]: view_qr_code(e, uid)
                                    )
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
                            ft.ElevatedButton(
                                "Get QR Code", 
                                icon=ft.icons.QR_CODE,
                                on_click=lambda e, uid=doc["uuid"]: view_qr_code(e, uid)
                            )
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
        
        # Connect file picker callback
        file_picker.on_result = handle_file_import
        
        # Reconnect filter callbacks to update_table_view
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
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)