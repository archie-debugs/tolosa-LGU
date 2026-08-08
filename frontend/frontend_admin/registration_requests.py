import os
import flet as ft
import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")

STATUS_OPTIONS = ["All", "Pending", "Approved", "Rejected"]
POSITION_OPTIONS = ["All", "Admin", "Secretary / Vice Mayor", "Staff"]
ROLE_OPTIONS = ["Admin", "SB Member", "Staff"]
SORT_OPTIONS = ["Newest First", "Oldest First"]
REJECTION_REASONS = [
    "Invalid Information",
    "Identification Could Not Be Verified",
    "Applicant Not Authorized",
    "Duplicate Registration",
    "Other",
]


def _format_badge(status: str):
    style = {
        "Pending": (ft.Colors.AMBER_100, ft.Colors.AMBER_900, "⏳ Pending"),
        "Approved": (ft.Colors.GREEN_100, ft.Colors.GREEN_900, "✓ Approved"),
        "Rejected": (ft.Colors.RED_100, ft.Colors.RED_900, "✕ Rejected"),
    }.get(status, (ft.Colors.BLUE_GREY_50, ft.Colors.BLUE_GREY_700, status))
    return ft.Container(
        content=ft.Text(style[2], size=12, weight=ft.FontWeight.BOLD, color=style[1]),
        padding=ft.Padding(left=10, top=6, right=10, bottom=6),
        bgcolor=style[0],
        border_radius=12,
    )


def _safe_text(value, fallback="—"):
    if value in (None, ""):
        return fallback
    return str(value)


def _format_submission_date(value):
    if not value:
        return "Not available"
    if isinstance(value, str):
        value = value.replace("Z", "+00:00")
    try:
        return str(value).split("T")[0]
    except Exception:
        return str(value)


def build_registration_requests_view(page, surface_card, section_header, refresh_callback=None, headers_provider=None):
    requests_data = []
    active_status_tab = "Pending"
    active_position = "All"
    active_date = "All"
    search_query = ""
    active_sort = "Newest First"
    selected_request = None
    selected_rejection_reason = REJECTION_REASONS[0]
    custom_rejection_note = ""
    selected_final_role = "SB Member"
    available_dates = ["All"]

    id_preview_dialog = ft.AlertDialog(
        title=ft.Text("ID Preview"),
        content=ft.Container(
            content=ft.Text("The uploaded identification document is not available in this build."),
            padding=20,
            width=550,
            height=300,
            bgcolor=ft.Colors.BLUE_GREY_50,
            border_radius=12,
        ),
        actions=[ft.TextButton("Close", on_click=lambda _: close_id_preview())],
    )

    approve_dialog = ft.AlertDialog(
        title=ft.Text("Approve Registration?"),
        content=ft.Column([], spacing=8),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_approve_dialog()),
            ft.Button("Approve", on_click=lambda _: confirm_approval(), bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE),
        ],
    )

    reject_dialog = ft.AlertDialog(
        title=ft.Text("Reject Registration?"),
        content=ft.Column([], spacing=8),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_reject_dialog()),
            ft.Button("Reject", on_click=lambda _: confirm_rejection(), bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE),
        ],
    )

    review_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Registration Application"),
        content=ft.Column([], spacing=18),
        actions=[ft.TextButton("Close", on_click=lambda _: close_review_dialog())],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def summary_card(title, value, icon, accent):
        return surface_card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=accent, size=20),
                            ft.Container(width=8),
                            ft.Text(title, size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_800),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(value, size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                ],
                spacing=8,
            ),
            padding=20,
        )

    def get_summary_counts():
        counts = {"Pending": 0, "Approved": 0, "Rejected": 0}
        for item in requests_data:
            counts[item.get("status", "Pending")] += 1
        return counts

    def filter_requests():
        filtered = []
        query = search_query.strip().lower()
        for item in requests_data:
            status = item.get("status", "Pending")
            position = item.get("position") or ""
            submitted_date = _format_submission_date(item.get("created_at"))
            if active_status_tab != "All" and status != active_status_tab:
                continue
            if active_position != "All" and position != active_position:
                continue
            if active_date != "All" and submitted_date != active_date:
                continue
            if query:
                target = " ".join([item.get("applicant_name", ""), item.get("username", ""), item.get("email", ""), item.get("registration_reference", "")]).lower()
                if query not in target:
                    continue
            filtered.append(item)
        filtered.sort(key=lambda item: item.get("created_at") or "", reverse=active_sort == "Newest First")
        return filtered

    def update_requests_view():
        nonlocal active_date
        filtered = filter_requests()
        summary_counts = get_summary_counts()
        tabs_row.controls.clear()
        tabs_row.controls.extend([build_filter_tab(name, summary_counts) for name in STATUS_OPTIONS])
        summary_row.controls.clear()
        summary_row.controls.extend(
            [
                summary_card("⏳ Pending", summary_counts["Pending"], ft.Icons.HOURGLASS_TOP, ft.Colors.AMBER_700),
                summary_card("✓ Approved", summary_counts["Approved"], ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN_700),
                summary_card("✕ Rejected", summary_counts["Rejected"], ft.Icons.CANCEL, ft.Colors.RED_700),
                summary_card("Total", len(requests_data), ft.Icons.DESCRIPTION_OUTLINED, ft.Colors.BLUE_700),
            ]
        )
        body_holder.content = build_requests_body(filtered)
        date_filter_dropdown.options = [ft.dropdown.Option(option) for option in available_dates]
        if active_date not in available_dates:
            active_date = "All"
        page.update()

    def build_filter_tab(name, summary_counts):
        count = len(filter_requests()) if name == active_status_tab else summary_counts.get(name, len(requests_data))
        label = f"{name} ({count})" if name != "All" else f"All ({len(requests_data)})"
        selected = name == active_status_tab
        side = ft.BorderSide(1, ft.Colors.BLUE_GREY_100)
        return ft.Container(
            content=ft.Text(label, size=12, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_900 if selected else ft.Colors.BLUE_GREY_800),
            padding=ft.Padding(left=16, top=10, right=16, bottom=10),
            bgcolor=ft.Colors.BLUE_50 if selected else ft.Colors.WHITE,
            border=ft.Border(top=side, right=side, bottom=side, left=side),
            border_radius=16,
            on_click=lambda e, tab=name: select_status_tab(tab),
        )

    def select_status_tab(tab_name):
        nonlocal active_status_tab
        active_status_tab = tab_name
        load_requests()

    def clear_filters(_=None):
        nonlocal active_position, active_date, search_query, active_status_tab, active_sort
        active_position = "All"
        active_date = "All"
        active_status_tab = "Pending"
        active_sort = "Newest First"
        search_query = ""
        search_field.value = ""
        position_dropdown.value = "All"
        status_dropdown.value = "Pending"
        date_filter_dropdown.value = "All"
        load_requests()

    def build_requests_body(filtered):
        side = ft.BorderSide(1, ft.Colors.BLUE_GREY_100)
        if not filtered:
            return ft.Column(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text("No Pending Registration Requests", size=18, weight=ft.FontWeight.BOLD),
                                ft.Text("There are currently no pending registrations to review.", size=13, color=ft.Colors.BLUE_GREY_600),
                                ft.Button("Clear Filters", on_click=clear_filters),
                            ],
                            spacing=12,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(left=30, top=30, right=30, bottom=30),
                        bgcolor=ft.Colors.BLUE_GREY_50,
                        border_radius=18,
                        alignment=ft.Alignment.CENTER,
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )

        if page.window_width and page.window_width < 760:
            cards = [build_request_card(item) for item in filtered]
            return ft.Column(cards, spacing=16)

        return ft.Column(
            [
                ft.Container(
                    content=ft.DataTable(
                        columns=[
                            ft.DataColumn(ft.Text("Registration Reference", weight=ft.FontWeight.BOLD)),
                            ft.DataColumn(ft.Text("Applicant", weight=ft.FontWeight.BOLD)),
                            ft.DataColumn(ft.Text("Position", weight=ft.FontWeight.BOLD)),
                            ft.DataColumn(ft.Text("Office", weight=ft.FontWeight.BOLD)),
                            ft.DataColumn(ft.Text("Requested Access", weight=ft.FontWeight.BOLD)),
                            ft.DataColumn(ft.Text("Submitted", weight=ft.FontWeight.BOLD)),
                            ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD)),
                            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD)),
                        ],
                        rows=[
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(ft.Text(_safe_text(item.get("registration_reference"), "-"))),
                                    ft.DataCell(ft.Text(_safe_text(item.get("applicant_name"), "-"))),
                                    ft.DataCell(ft.Text(_safe_text(item.get("position"), "-"))),
                                    ft.DataCell(ft.Text(_safe_text(item.get("office"), "-"))),
                                    ft.DataCell(ft.Text(_safe_text(item.get("requested_access"), "-"))),
                                    ft.DataCell(ft.Text(_format_submission_date(item.get("created_at")))),
                                    ft.DataCell(_format_badge(item.get("status", "Pending"))),
                                    ft.DataCell(
                                        ft.Row(
                                            [
                                                ft.Button(
                                                    "View Details",
                                                    on_click=lambda e, req=item: open_review(req),
                                                    bgcolor=ft.Colors.BLUE_800,
                                                    color=ft.Colors.WHITE,
                                                )
                                            ],
                                            alignment=ft.MainAxisAlignment.END,
                                        )
                                    ),
                                ]
                            )
                            for item in filtered
                        ],
                        heading_row_height=40,
                        border=ft.Border(top=side, right=side, bottom=side, left=side),
                    ),
                    padding=12,
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    border_radius=18,
                )
            ],
            spacing=12,
        )

    def build_request_card(item):
        return surface_card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(_safe_text(item.get("registration_reference"), "-"), weight=ft.FontWeight.BOLD),
                                    ft.Text(_safe_text(item.get("applicant_name"), "-"), size=13, color=ft.Colors.BLUE_GREY_700),
                                ],
                                expand=True,
                            ),
                            _format_badge(item.get("status", "Pending")),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        [
                            ft.Column([ft.Text("Position", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(_safe_text(item.get("position"), "-"), size=13)], expand=True),
                            ft.Column([ft.Text("Office", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(_safe_text(item.get("office"), "-"), size=13)], expand=True),
                        ],
                        spacing=16,
                    ),
                    ft.Row(
                        [
                            ft.Column([ft.Text("Requested Access", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(_safe_text(item.get("requested_access"), "-"), size=13)], expand=True),
                            ft.Column([ft.Text("Submitted", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(_format_submission_date(item.get("created_at")), size=13)], expand=True),
                        ],
                        spacing=16,
                    ),
                    ft.Row(
                        [
                            ft.Button(
                                "View Details",
                                on_click=lambda e, req=item: open_review(req),
                                bgcolor=ft.Colors.BLUE_800,
                                color=ft.Colors.WHITE,
                            )
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=14,
            ),
            padding=20,
        )

    def open_id_preview(_=None):
        page.dialog = id_preview_dialog
        id_preview_dialog.open = True
        page.update()

    def close_id_preview():
        id_preview_dialog.open = False
        page.update()

    def open_review(request):
        nonlocal selected_request, selected_final_role, selected_rejection_reason, custom_rejection_note
        selected_request = request
        selected_final_role = request.get("requested_access") or "Staff"
        selected_rejection_reason = REJECTION_REASONS[0]
        custom_rejection_note = ""

        try:
            headers = headers_provider() if headers_provider else {}
            url = f"{BACKEND_URL}/registration/requests/{request['id']}"
            print(f"[registration_requests] GET {url}")
            response = requests.get(url, headers=headers, verify=False, timeout=10)
            print(f"[registration_requests] status: {response.status_code}")
            print(f"[registration_requests] body: {response.text}")
            if response.status_code == 200:
                details = response.json()
            else:
                raise ValueError(response.text)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            details = request

        review_dialog.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Registration Application", size=20, weight=ft.FontWeight.BOLD),
                        _format_badge(details.get("status", "Pending")),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text("Review the applicant details and choose the final system role.", size=13, color=ft.Colors.BLUE_GREY_600),
                ft.Divider(height=1),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Personal Information", size=16, weight=ft.FontWeight.BOLD),
                                ft.Row(
                                    [
                                        ft.Column([ft.Text("Full Name", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(_safe_text(details.get("first_name")) + " " + _safe_text(details.get("last_name")), size=13)], expand=True),
                                        ft.Column([ft.Text("Contact Number", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(_safe_text(details.get("contact_number"), "-"), size=13)], expand=True),
                                    ],
                                    spacing=16,
                                ),
                                ft.Row(
                                    [
                                        ft.Column([ft.Text("Email Address", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(_safe_text(details.get("email"), "-"), size=13)], expand=True),
                                        ft.Column([ft.Text("Username", size=12, color=ft.Colors.BLUE_GREY_600), ft.Text(_safe_text(details.get("username"), "-"), size=13)], expand=True),
                                    ],
                                    spacing=16,
                                ),
                            ],
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text("Office Information", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text("Office", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(_safe_text(details.get("office"), "-"), size=13),
                                ft.Text("Position", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(_safe_text(details.get("position"), "-"), size=13),
                                ft.Text("Requested Access", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(_safe_text(details.get("requested_access"), "-"), size=13, weight=ft.FontWeight.W_600),
                            ],
                            width=280,
                        ),
                    ],
                    spacing=24,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Divider(height=1),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Registration Details", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text("Registration Reference", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(_safe_text(details.get("registration_reference"), "-"), size=13),
                                ft.Text("Submission Date", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(_format_submission_date(details.get("created_at")), size=13),
                                ft.Text("Current Status", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(_safe_text(details.get("status"), "Pending"), size=13),
                            ],
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text("System Role Assignment", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text("Final Role", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Dropdown(
                                    width=260,
                                    options=[ft.dropdown.Option(role) for role in ROLE_OPTIONS],
                                    value=selected_final_role,
                                    on_select=lambda e: set_final_role(e.control.value),
                                    disabled=details.get("status") != "Pending",
                                ),
                                ft.Container(height=12),
                                ft.Text("The requested access is a request only. The administrator selects the final role.", size=12, color=ft.Colors.BLUE_GREY_600),
                            ],
                            width=320,
                        ),
                    ],
                    spacing=24,
                ),
                ft.Divider(height=1),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Contact & Identity", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text("Email", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(_safe_text(details.get("email"), "-"), size=13),
                                ft.Text("ID Type", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(_safe_text(details.get("id_type"), "-"), size=13),
                                ft.Text("Uploaded ID", size=12, color=ft.Colors.BLUE_GREY_600),
                                ft.Text(_safe_text(details.get("id_file_path"), "Not available"), size=13),
                            ],
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text("Notes", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text(_safe_text(details.get("notes"), "No notes provided."), size=13),
                            ],
                            width=320,
                        ),
                    ],
                    spacing=24,
                ),
            ],
            spacing=16,
        )

        if details.get("status") == "Pending":
            review_dialog.actions = [
                ft.TextButton("Close", on_click=lambda _: close_review_dialog()),
                ft.OutlinedButton("Reject Registration", on_click=lambda _: open_reject_dialog()),
                ft.Button("Approve Registration", on_click=lambda _: open_approve_dialog(), bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE),
            ]
        else:
            review_dialog.actions = [ft.TextButton("Close", on_click=lambda _: close_review_dialog())]

        page.dialog = review_dialog
        review_dialog.open = True
        page.update()

    def set_final_role(value):
        nonlocal selected_final_role
        selected_final_role = value
        page.update()

    def open_approve_dialog():
        if not selected_request:
            return
        approve_dialog.content = ft.Column(
            [
                ft.Text(f"Full Name: {selected_request.get('applicant_name', 'Applicant')}", size=13),
                ft.Text(f"Username: {selected_request.get('username', '-')}", size=13),
                ft.Text(f"Registration Date: {selected_request.get('created_at') or '-'}", size=13),
                ft.Text("Assign Role", size=13, weight=ft.FontWeight.BOLD),
                ft.Dropdown(
                    width=260,
                    options=[ft.dropdown.Option(role) for role in ROLE_OPTIONS],
                    value=selected_final_role,
                    on_select=lambda e: set_final_role(e.control.value),
                ),
                ft.Text("This approval will create an active user account.", size=12, color=ft.Colors.BLUE_GREY_600),
            ],
            spacing=10,
        )
        page.dialog = approve_dialog
        approve_dialog.open = True
        page.update()

    def confirm_approval():
        nonlocal selected_request
        if not selected_request:
            return
        try:
            headers = headers_provider() if headers_provider else {}
            url = f"{BACKEND_URL}/registration/requests/{selected_request['id']}/approve"
            print(f"[registration_requests] PUT {url}")
            response = requests.put(
                url,
                json={"final_role": selected_final_role},
                headers=headers,
                verify=False,
                timeout=10,
            )
            print(f"[registration_requests] status: {response.status_code}")
            print(f"[registration_requests] body: {response.text}")
            if response.status_code != 200:
                raise ValueError(response.text)
            page.snack_bar = ft.SnackBar(ft.Text("Registration Approved Successfully"), open=True)
            approve_dialog.open = False
            review_dialog.open = False
            load_requests()
            if refresh_callback:
                refresh_callback()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            page.snack_bar = ft.SnackBar(ft.Text(f"Approval failed: {exc}"), open=True)
            page.update()

    def open_reject_dialog():
        if not selected_request:
            return
        reject_dialog.content = ft.Column(
            [
                ft.Text(f"Applicant: {selected_request.get('applicant_name', 'Applicant')}", size=13),
                ft.Text("Reason for Rejection:", size=13, weight=ft.FontWeight.BOLD),
                ft.Dropdown(
                    width=400,
                    options=[ft.dropdown.Option(reason) for reason in REJECTION_REASONS],
                    value=selected_rejection_reason,
                    on_select=lambda e: set_rejection_reason(e.control.value),
                ),
                ft.Text("Custom reason (optional)", size=12, color=ft.Colors.BLUE_GREY_600),
                ft.TextField(width=400, height=100, multiline=True, value=custom_rejection_note, on_change=lambda e: set_custom_rejection_note(e.control.value)),
            ],
            spacing=10,
        )
        page.dialog = reject_dialog
        reject_dialog.open = True
        page.update()

    def set_rejection_reason(value):
        nonlocal selected_rejection_reason
        selected_rejection_reason = value
        page.update()

    def set_custom_rejection_note(value):
        nonlocal custom_rejection_note
        custom_rejection_note = value
        page.update()

    def confirm_rejection():
        nonlocal selected_request
        if not selected_request:
            return
        reason = selected_rejection_reason if selected_rejection_reason != "Other" else (custom_rejection_note or "Other")
        if not reason.strip():
            page.snack_bar = ft.SnackBar(ft.Text("Please enter a rejection reason."), open=True)
            page.update()
            return
        try:
            headers = headers_provider() if headers_provider else {}
            url = f"{BACKEND_URL}/registration/requests/{selected_request['id']}/reject"
            print(f"[registration_requests] PUT {url}")
            response = requests.put(
                url,
                json={"reason": reason},
                headers=headers,
                verify=False,
                timeout=10,
            )
            print(f"[registration_requests] status: {response.status_code}")
            print(f"[registration_requests] body: {response.text}")
            if response.status_code != 200:
                raise ValueError(response.text)
            page.snack_bar = ft.SnackBar(ft.Text("Registration Rejected Successfully"), open=True)
            reject_dialog.open = False
            review_dialog.open = False
            load_requests()
            if refresh_callback:
                refresh_callback()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            page.snack_bar = ft.SnackBar(ft.Text(f"Rejection failed: {exc}"), open=True)
            page.update()

    def close_review_dialog():
        review_dialog.open = False
        page.update()

    def close_approve_dialog():
        approve_dialog.open = False
        page.update()

    def close_reject_dialog():
        reject_dialog.open = False
        page.update()

    def load_requests():
        nonlocal requests_data, available_dates
        try:
            headers = headers_provider() if headers_provider else {}
            url = f"{BACKEND_URL}/registration/requests"
            params = {}
            if active_status_tab and active_status_tab != "All":
                params["status"] = active_status_tab
            print(f"[registration_requests] GET {url} params={params}")
            response = requests.get(url, headers=headers, params=params, verify=False, timeout=10)
            print(f"[registration_requests] status: {response.status_code}")
            print(f"[registration_requests] body: {response.text}")
            if response.status_code != 200:
                raise ValueError(response.text)
            payload = response.json()
            requests_data = payload.get("items", [])
            available_dates = ["All"] + sorted({ _format_submission_date(item.get("created_at")) for item in requests_data if item.get("created_at") })
        except Exception as exc:
            import traceback
            traceback.print_exc()
            requests_data = []
            available_dates = ["All"]
            page.snack_bar = ft.SnackBar(ft.Text(f"Unable to load registration requests: {exc}"), open=True)
        update_requests_view()

    def build_requests_header():
        return ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Registration Requests", size=22, weight=ft.FontWeight.BOLD),
                        ft.Text("Review and manage user registration requests.", size=13, color=ft.Colors.BLUE_GREY_600),
                    ],
                    expand=True,
                ),
                ft.Button("Refresh", icon=ft.Icons.REFRESH, on_click=lambda _: load_requests(), bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def build_search_area():
        return ft.Row(
            [
                ft.TextField(label="Search applicants...", width=320, value=search_query, on_change=lambda e: set_search_query(e.control.value), prefix_icon=ft.Icons.SEARCH),
                ft.Dropdown(label="Position", width=180, options=[ft.dropdown.Option(option) for option in POSITION_OPTIONS], value=active_position, on_select=lambda e: set_position_filter(e.control.value)),
                ft.Dropdown(label="Status", width=180, options=[ft.dropdown.Option(option) for option in STATUS_OPTIONS], value=active_status_tab, on_select=lambda e: set_status_filter(e.control.value)),
                ft.Dropdown(label="Sort", width=180, options=[ft.dropdown.Option(option) for option in SORT_OPTIONS], value=active_sort, on_select=lambda e: set_sort_filter(e.control.value)),
                ft.Dropdown(label="Date", width=180, options=[ft.dropdown.Option(option) for option in available_dates], value=active_date, on_select=lambda e: set_date_filter(e.control.value)),
                ft.TextButton("Clear Filters", on_click=clear_filters),
            ],
            spacing=12,
            wrap=True,
        )

    def set_search_query(value):
        nonlocal search_query
        search_query = value
        update_requests_view()

    def set_position_filter(value):
        nonlocal active_position
        active_position = value
        update_requests_view()

    def set_status_filter(value):
        select_status_tab(value)

    def set_date_filter(value):
        nonlocal active_date
        active_date = value
        update_requests_view()

    def set_sort_filter(value):
        nonlocal active_sort
        active_sort = value
        update_requests_view()

    tab_buttons = ft.Row(spacing=12)
    tabs_row = ft.Row(spacing=10)
    summary_row = ft.Row(spacing=12, wrap=True)
    search_field = ft.TextField()
    position_dropdown = ft.Dropdown()
    status_dropdown = ft.Dropdown()
    date_filter_dropdown = ft.Dropdown()
    body_holder = ft.Container()

    def on_resize(e=None):
        body_holder.content = build_requests_body(filter_requests())
        page.update()

    page.on_resize = on_resize

    content = ft.Column(
        [
            build_requests_header(),
            tabs_row,
            summary_row,
            surface_card(build_search_area(), padding=20),
            body_holder,
        ],
        spacing=18,
        expand=True,
    )

    load_requests()
    page.dialog = page.dialog or None
    page.overlay.append(id_preview_dialog)
    page.overlay.append(approve_dialog)
    page.overlay.append(reject_dialog)
    page.overlay.append(review_dialog)
    return content
