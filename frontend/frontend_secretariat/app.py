import os
import time
import requests
import base64
import json
from urllib.parse import quote
import flet as ft


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

    def handle_agenda_export(e=None):
        try:
            response = requests.get(f"{BACKEND_URL}/documents/generate-agenda", verify=False)
            if response.status_code == 200:
                output_path = save_binary_file_to_workspace(f"session_agenda_{time.strftime('%Y%m%d_%H%M%S')}.pdf", response.content)
                page.snack_bar = ft.SnackBar(ft.Text(f"Agenda PDF saved to {output_path}"), open=True)
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"Agenda export failed: {response.text}"), open=True)
        except Exception as exc:
            page.snack_bar = ft.SnackBar(ft.Text(f"Agenda export error: {exc}"), open=True)
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

    def open_register_dialog(e=None):
        dialog = ft.AlertDialog(
            title=ft.Text("Register New Measure"),
            content=ft.Column([register_title, register_type, register_committee], tight=True),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: dialog_close(dialog)),
                ft.ElevatedButton("Register", on_click=lambda e: submit_register(dialog)),
            ],
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def dialog_close(dialog):
        try:
            dialog.open = False
            page.update()
        except Exception:
            pass

    def submit_register(dialog):
        title = (register_title.value or "").strip()
        item_type = (register_type.value or "Ordinance").strip()
        committee = (register_committee.value or "").strip()
        if not title or not committee:
            page.snack_bar = ft.SnackBar(ft.Text("Please fill out all mandatory fields."), open=True)
            page.update()
            return
        try:
            response = requests.post(f"{BACKEND_URL}/legislative/register", json={"title": title, "item_type": item_type, "committee": committee}, verify=False)
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
                    "source_filename": None,
                })
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
    
