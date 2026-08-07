import flet as ft


def build_admin_dashboard_view(surface_card, section_header, open_preview_notice, pending_requests=None):
    if pending_requests is None:
        pending_requests = [
            {"name": "John Doe", "role": "Staff", "time": "Submitted 10 minutes ago"},
            {"name": "Maria Santos", "role": "Staff", "time": "Submitted 25 minutes ago"},
            {"name": "Carlos Reyes", "role": "Staff", "time": "Submitted 1 hour ago"},
        ]
    else:
        pending_requests = [
            {
                "name": item.get("applicant_name", "Applicant"),
                "role": item.get("requested_access") or "Staff",
                "time": item.get("created_at", "Submitted recently"),
            }
            for item in pending_requests
        ]

    stat_cards = [
        {"icon": ft.Icons.DESCRIPTION_OUTLINED, "title": "Total Documents", "value": "356", "detail": "+12% from last month", "accent": ft.Colors.BLUE_700},
        {"icon": ft.Icons.PEOPLE_OUTLINED, "title": "Total Users", "value": "24", "detail": "6 active reviewers", "accent": ft.Colors.INDIGO_700},
        {"icon": ft.Icons.HOURGLASS_TOP_OUTLINED, "title": "Pending Requests", "value": "3", "detail": "Needs review today", "accent": ft.Colors.AMBER_700},
        {"icon": ft.Icons.DYNAMIC_FEED_OUTLINED, "title": "Active Documents", "value": "60", "detail": "Currently in motion", "accent": ft.Colors.GREEN_700},
        {"icon": ft.Icons.QR_CODE_OUTLINED, "title": "QR Tracked Documents", "value": "341", "detail": "Scans logged this week", "accent": ft.Colors.PURPLE_700},
        {"icon": ft.Icons.ARCHIVE_OUTLINED, "title": "Archived Documents", "value": "296", "detail": "Stored for reference", "accent": ft.Colors.BLUE_GREY_700},
    ]

    status_items = [
        {"label": "Registered", "value": 45, "color": ft.Colors.BLUE_700},
        {"label": "Routed", "value": 32, "color": ft.Colors.INDIGO_700},
        {"label": "Received", "value": 18, "color": ft.Colors.GREEN_700},
        {"label": "Under Review", "value": 12, "color": ft.Colors.AMBER_700},
        {"label": "Completed", "value": 249, "color": ft.Colors.PURPLE_700},
    ]

    recent_activity_rows = [
        {"id": "DOC-2026-0015", "document": "Proposed Ordinance on Local Revenue", "type": "Ordinance", "status": "Under Review", "location": "Committee on Finance", "time": "11:02 AM"},
        {"id": "DOC-2026-0016", "document": "Resolution No. 2026-008", "type": "Resolution", "status": "Routed", "location": "Committee on Health", "time": "10:45 AM"},
        {"id": "DOC-2026-0017", "document": "Committee Report No. 04", "type": "Committee Report", "status": "Completed", "location": "SB Office", "time": "10:20 AM"},
    ]

    qr_activity = [
        {"icon": ft.Icons.CHECK_CIRCLE_OUTLINED, "title": "DOC-2026-0015", "detail": "Received by Staff A", "time": "11:02 AM", "accent": ft.Colors.GREEN_700},
        {"icon": ft.Icons.CHECK_CIRCLE_OUTLINED, "title": "DOC-2026-0016", "detail": "Scanned by Staff B", "time": "10:45 AM", "accent": ft.Colors.BLUE_700},
        {"icon": ft.Icons.WARNING_AMBER_OUTLINED, "title": "DOC-2026-0017", "detail": "Unrecognized scan", "time": "10:31 AM", "accent": ft.Colors.AMBER_700},
    ]

    pending_requests = [
        {"name": "John Doe", "role": "Staff", "time": "Submitted 10 minutes ago"},
        {"name": "Maria Santos", "role": "Staff", "time": "Submitted 25 minutes ago"},
        {"name": "Carlos Reyes", "role": "Staff", "time": "Submitted 1 hour ago"},
    ]

    system_activity = [
        {"time": "10:32 AM", "text": "Admin approved a registration request", "icon": ft.Icons.CHECK_CIRCLE_OUTLINED},
        {"time": "10:15 AM", "text": "Secretary registered DOC-2026-0015", "icon": ft.Icons.DESCRIPTION_OUTLINED},
        {"time": "09:58 AM", "text": "Staff A received DOC-2026-0015", "icon": ft.Icons.QR_CODE_OUTLINED},
        {"time": "09:40 AM", "text": "Secretary routed DOC-2026-0015", "icon": ft.Icons.SEND_OUTLINED},
        {"time": "09:20 AM", "text": "New registration request submitted", "icon": ft.Icons.CREATE_OUTLINED},
    ]

    alerts = [
        {"text": "3 registration requests require review", "type": "warning", "icon": ft.Icons.WARNING_AMBER_OUTLINED},
        {"text": "2 documents are awaiting action", "type": "info", "icon": ft.Icons.INFO_OUTLINED},
        {"text": "1 unrecognized QR scan detected", "type": "critical", "icon": ft.Icons.ERROR_OUTLINE},
        {"text": "No critical system errors", "type": "success", "icon": ft.Icons.CHECK_CIRCLE_OUTLINED},
    ]

    stat_cards_view = ft.Row(
        [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(item["icon"], color=item["accent"], size=22),
                                ft.Container(width=8),
                                ft.Text(item["title"], size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_700),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(item["value"], size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                        ft.Text(item["detail"], size=12, color=ft.Colors.BLUE_GREY_600),
                    ],
                    spacing=6,
                ),
                width=260,
                padding=20,
                bgcolor=ft.Colors.WHITE,
                border_radius=18,
                border=ft.Border.all(1, ft.Colors.BLUE_GREY_50),
            )
            for item in stat_cards
        ],
        spacing=16,
        wrap=True,
    )

    status_overview = surface_card(
        ft.Column(
            [
                section_header("Document Status Overview", "Static overview for the administration dashboard", ft.Icons.INSIGHTS_OUTLINED, ft.Colors.BLUE_700),
                ft.Divider(height=1),
                *[
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(status["label"], size=13, color=ft.Colors.BLUE_GREY_700, expand=True),
                                    ft.Text(str(status["value"]), size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.ProgressBar(value=min(status["value"] / 260, 1.0), color=status["color"], bgcolor=ft.Colors.BLUE_GREY_50, bar_height=8),
                        ],
                        spacing=6,
                    )
                    for status in status_items
                ],
            ],
            spacing=12,
        ),
        expand=True,
        padding=24,
    )

    recent_activity_table = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Recent Document Activity", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900, expand=True),
                        ft.TextButton("View All", on_click=lambda _: open_preview_notice(None)),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("Document ID", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700, expand=True),
                                    ft.Text("Document", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700, expand=True),
                                    ft.Text("Type", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700, width=90),
                                    ft.Text("Status", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700, width=110),
                                    ft.Text("Current Location", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700, width=140),
                                    ft.Text("Last Activity", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700, width=100),
                                ],
                                spacing=12,
                            ),
                            ft.Divider(height=1),
                            *[
                                ft.Row(
                                    [
                                        ft.Text(item["id"], size=12, color=ft.Colors.BLUE_GREY_800, expand=True),
                                        ft.Text(item["document"], size=12, color=ft.Colors.BLUE_GREY_800, expand=True),
                                        ft.Text(item["type"], size=12, color=ft.Colors.BLUE_GREY_800, width=90),
                                        ft.Text(item["status"], size=12, color=ft.Colors.BLUE_700, width=110),
                                        ft.Text(item["location"], size=12, color=ft.Colors.BLUE_GREY_800, width=140),
                                        ft.Text(item["time"], size=12, color=ft.Colors.BLUE_GREY_600, width=100),
                                    ],
                                    spacing=12,
                                )
                                for item in recent_activity_rows
                            ],
                        ],
                        spacing=10,
                    ),
                    padding=12,
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    border_radius=16,
                ),
            ],
            spacing=12,
        ),
        padding=20,
        bgcolor=ft.Colors.WHITE,
        border_radius=22,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_50),
    )

    qr_section = surface_card(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Recent QR Tracking Activity", size=17, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900, expand=True),
                        ft.Icon(ft.Icons.QR_CODE_OUTLINED, color=ft.Colors.PURPLE_700),
                    ]
                ),
                *[
                    ft.Row(
                        [
                            ft.Icon(item["icon"], color=item["accent"], size=20),
                            ft.Column(
                                [ft.Text(item["title"], size=13, weight=ft.FontWeight.W_600), ft.Text(item["detail"], size=12, color=ft.Colors.BLUE_GREY_600)],
                                expand=True,
                            ),
                            ft.Text(item["time"], size=12, color=ft.Colors.BLUE_GREY_600),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    )
                    for item in qr_activity
                ],
                ft.TextButton("View Tracking", on_click=lambda _: open_preview_notice(None)),
            ],
            spacing=14,
        ),
        padding=24,
    )

    pending_requests_section = surface_card(
        ft.Column(
            [
                ft.Text("Pending Registration Requests", size=17, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                *[
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(item["name"], size=14, weight=ft.FontWeight.W_600),
                                    ft.Text(item["role"], size=12, color=ft.Colors.BLUE_GREY_600),
                                    ft.Text(item["time"], size=12, color=ft.Colors.BLUE_GREY_500),
                                ],
                                expand=True,
                            ),
                            ft.TextButton("View", on_click=lambda _: open_preview_notice(None)),
                            ft.TextButton("Approve", on_click=lambda _: open_preview_notice(None)),
                            ft.TextButton("Reject", on_click=lambda _: open_preview_notice(None)),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                    for item in pending_requests
                ],
            ],
            spacing=14,
        ),
        padding=24,
    )

    system_activity_section = surface_card(
        ft.Column(
            [
                ft.Text("Recent System Activity", size=17, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                *[
                    ft.Row(
                        [
                            ft.Icon(item["icon"], color=ft.Colors.BLUE_700, size=18),
                            ft.Column(
                                [
                                    ft.Text(item["time"], size=12, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_700),
                                    ft.Text(item["text"], size=13, color=ft.Colors.BLUE_GREY_700),
                                ],
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        spacing=10,
                    )
                    for item in system_activity
                ],
            ],
            spacing=14,
        ),
        padding=24,
    )

    alerts_section = surface_card(
        ft.Column(
            [
                ft.Text("System Alerts", size=17, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                *[
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(
                                    alert["icon"],
                                    color=ft.Colors.AMBER_700 if alert["type"] == "warning" else ft.Colors.RED_700 if alert["type"] == "critical" else ft.Colors.GREEN_700 if alert["type"] == "success" else ft.Colors.BLUE_700,
                                    size=18,
                                ),
                                ft.Text(alert["text"], size=13, color=ft.Colors.BLUE_GREY_700, expand=True),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=10,
                        bgcolor=ft.Colors.BLUE_GREY_50,
                        border_radius=12,
                    )
                    for alert in alerts
                ],
            ],
            spacing=14,
        ),
        padding=24,
    )

    quick_actions = surface_card(
        ft.Column(
            [
                ft.Text("Quick Actions", size=17, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                ft.Row(
                    [
                        ft.Button("Review Registrations", icon=ft.Icons.CHECKLIST_OUTLINED, on_click=lambda _: open_preview_notice(None)),
                        ft.OutlinedButton("Documents", icon=ft.Icons.DESCRIPTION_OUTLINED, on_click=lambda _: open_preview_notice(None)),
                        ft.OutlinedButton("QR Tracking", icon=ft.Icons.QR_CODE_OUTLINED, on_click=lambda _: open_preview_notice(None)),
                        ft.OutlinedButton("Users & Roles", icon=ft.Icons.PEOPLE_OUTLINED, on_click=lambda _: open_preview_notice(None)),
                        ft.OutlinedButton("Audit Logs", icon=ft.Icons.HISTORY_OUTLINED, on_click=lambda _: open_preview_notice(None)),
                    ],
                    spacing=12,
                    wrap=True,
                ),
            ],
            spacing=14,
        ),
        padding=24,
    )

    return ft.Column(
        [
            surface_card(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text("SB Tolosa — Administration Dashboard", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                                        ft.Text("System Administration and Document Management Overview", size=13, color=ft.Colors.BLUE_GREY_600),
                                    ],
                                    expand=True,
                                    spacing=2,
                                ),
                                ft.Row(
                                    [
                                        ft.IconButton(ft.Icons.NOTIFICATIONS_OUTLINED, tooltip="Notifications"),
                                        ft.Container(content=ft.Icon(ft.Icons.ACCOUNT_CIRCLE_OUTLINED, size=30, color=ft.Colors.BLUE_700), padding=4),
                                        ft.Column(
                                            [
                                                ft.Text("Administrator", size=13, weight=ft.FontWeight.W_600),
                                                ft.Text("System Administrator", size=12, color=ft.Colors.BLUE_GREY_600),
                                            ],
                                            spacing=1,
                                        ),
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=8,
                ),
                padding=24,
            ),
            ft.Container(height=8),
            stat_cards_view,
            ft.Container(height=6),
            ft.Row([status_overview, ft.Container(width=16), qr_section], spacing=0, wrap=True, vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Container(height=10),
            recent_activity_table,
            ft.Container(height=10),
            ft.Row([pending_requests_section, ft.Container(width=16), alerts_section], spacing=0, wrap=True, vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Container(height=10),
            ft.Row([system_activity_section, ft.Container(width=16), quick_actions], spacing=0, wrap=True, vertical_alignment=ft.CrossAxisAlignment.START),
        ],
        spacing=16,
        expand=True,
    )
