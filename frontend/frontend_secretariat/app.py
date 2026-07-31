import os
import time
import requests
import flet as ft


def build_secretariat_view(page: ft.Page, current_user_role, workflow_steps, all_documents, secretariat_selected_ids, save_binary_file_to_workspace, BACKEND_URL, surface_card, section_header):
    if current_user_role not in {"secretariat", "admin"}:
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
    secretariat_search_field = ft.TextField(label="Search measures", width=320, prefix_icon=ft.icons.SEARCH)
    secretariat_notice = ft.Text("Select measures to prepare batch paperwork.", size=12, color=ft.colors.BLUE_GREY_600)
    secretariat_table = ft.DataTable(columns=[
        ft.DataColumn(ft.Text("", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("ID", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("Title", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("Type", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD)),
        ft.DataColumn(ft.Text("Committee", weight=ft.FontWeight.BOLD)),
    ], rows=[])
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
        status_value = secretariat_status_filter.value or "All"
        type_value = secretariat_type_filter.value or "All"
        year_value = secretariat_year_filter.value or "All"

        for doc in all_documents:
            if status_value != "All" and doc.get("status", "") != status_value:
                continue
            if type_value != "All" and doc.get("type", "") != type_value:
                continue
            if year_value != "All":
                created_at = str(doc.get("created_at") or "")
                year_text = created_at[:4] if created_at else ""
                if year_text != year_value:
                    continue
            if search_term:
                haystack = " ".join([
                    str(doc.get("title", "")),
                    str(doc.get("type", "")),
                    str(doc.get("committee", "")),
                    str(doc.get("status", "")),
                    str(doc.get("uuid", "")),
                ]).lower()
                if search_term not in haystack:
                    continue

            selected = str(doc.get("id", "")) in secretariat_selected_ids
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Checkbox(value=selected, on_change=lambda e, item=doc: toggle_secretariat_selection(item, bool(e.control.value)))),
                        ft.DataCell(ft.Text(str(doc.get("display_id", doc.get("id", "-"))))),
                        ft.DataCell(ft.Text(doc.get("title", "Untitled"))),
                        ft.DataCell(ft.Text(doc.get("type", "-"))),
                        ft.DataCell(ft.Text(doc.get("status", "-"))),
                        ft.DataCell(ft.Text(doc.get("committee", "-"))),
                    ]
                )
            )

        secretariat_table.rows = rows
        secretariat_notice.value = f"{len(secretariat_selected_ids)} item(s) selected." if secretariat_selected_ids else "Select measures to prepare batch paperwork."
        secretariat_toolbar.visible = bool(secretariat_selected_ids)
        secretariat_toolbar.content = ft.Row(
            [
                ft.Text(f"{len(secretariat_selected_ids)} items selected", weight=ft.FontWeight.BOLD),
                ft.ElevatedButton("Generate Batch QR PDF", icon=ft.icons.PRINT, on_click=handle_batch_qr_export),
                ft.OutlinedButton("Generate Session Agenda", icon=ft.icons.DESCRIPTION_OUTLINED, on_click=handle_agenda_export),
            ],
            spacing=12,
            wrap=True,
        )
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
                                ft.ElevatedButton("+ Register New Measure", icon=ft.icons.ADD),
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
