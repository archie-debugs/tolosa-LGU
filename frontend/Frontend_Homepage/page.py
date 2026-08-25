import flet as ft
from frontend.frontend_admin.app import main as admin_main

if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors
if not hasattr(ft, "Icons") and hasattr(ft, "icons"):
    ft.Icons = ft.icons
if hasattr(ft, "Alignment") and hasattr(ft, "alignment"):
    for alignment_name, alignment_value in {
        "CENTER": getattr(ft.alignment, "center", None),
        "CENTER_LEFT": getattr(ft.alignment, "center_left", None),
        "CENTER_RIGHT": getattr(ft.alignment, "center_right", None),
    }.items():
        if alignment_value is not None and not hasattr(ft.Alignment, alignment_name):
            setattr(ft.Alignment, alignment_name, alignment_value)


def build_homepage_view(page=None):
    navy = "#103449"
    teal = "#176b70"
    gold = "#c9953d"
    ink = "#173042"
    muted = "#607684"
    pale = "#eef4f3"
    hero_photo = "sb_tolosa_homepage.jpg"

    def visual_link(label, color=ink, on_click=None):
        return ft.TextButton(
            text=label,
            on_click=on_click,
            style=ft.ButtonStyle(color=color, padding=ft.Padding(8, 8, 8, 8)),
        )

    def open_login(_):
        if page is not None:
            admin_main(page)

    utility_bar = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Text(
                        "Republic of the Philippines  •  Province of Leyte  •  Municipality of Tolosa",
                        size=11,
                        color="#e7f0ef",
                    ),
                    col={"xs": 12, "md": 8},
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text("Accessibility", size=11, color="#e7f0ef"),
                            ft.Text("Contact", size=11, color="#e7f0ef"),
                            ft.Text("Help", size=11, color="#e7f0ef"),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=18,
                        wrap=True,
                    ),
                    col={"xs": 12, "md": 4},
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=navy,
        padding=ft.Padding(28, 9, 28, 9),
    )

    brand = ft.Row(
        [
            ft.Container(
                content=ft.Icon(ft.Icons.ACCOUNT_BALANCE_OUTLINED, color=navy, size=27),
                width=48,
                height=48,
                alignment=ft.Alignment.CENTER,
                bgcolor="#e8f0ee",
                border=ft.border.all(1, "#c4d8d3"),
                border_radius=10,
            ),
            ft.Column(
                [
                    ft.Text("SANGGUNIAN BAYAN", size=15, weight=ft.FontWeight.BOLD, color=navy),
                    ft.Text("MUNICIPALITY OF TOLOSA", size=10, color=muted),
                ],
                spacing=1,
            ),
        ],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    navigation = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(content=brand, col={"xs": 12, "lg": 4}),
                ft.Container(
                    content=ft.Row(
                        [
                            visual_link("Home", on_click=lambda _: content_scroll.scroll_to(offset=0, duration=300)),
                            visual_link("About", on_click=lambda _: content_scroll.scroll_to(key="about-section", duration=300)),
                            visual_link("Public Records", on_click=lambda _: content_scroll.scroll_to(key="records-section", duration=300)),
                            visual_link("Announcements", on_click=lambda _: content_scroll.scroll_to(key="announcements-section", duration=300)),
                            visual_link("Contact", on_click=lambda _: content_scroll.scroll_to(key="contact-section", duration=300)),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=2,
                        wrap=True,
                    ),
                    col={"xs": 12, "lg": 5},
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            visual_link("Login", muted, on_click=open_login),
                            ft.ElevatedButton(
                                "Public Documents",
                                color=navy,
                                bgcolor=gold,
                                style=ft.ButtonStyle(padding=ft.Padding(15, 11, 15, 11)),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        wrap=True,
                    ),
                    col={"xs": 12, "lg": 3},
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor="#ffffff",
        padding=ft.Padding(28, 16, 28, 16),
        shadow=ft.BoxShadow(blur_radius=12, color="#183b4a12", offset=ft.Offset(0, 3)),
    )

    hero_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("SANGGUNIAN BAYAN OF TOLOSA", size=12, color=teal, weight=ft.FontWeight.BOLD),
                ft.Container(height=3, width=56, bgcolor=gold),
                ft.Text(
                    "Legislative Documents, Made Accessible.",
                    size=34,
                    color=ink,
                    weight=ft.FontWeight.BOLD,
                    font_family="Georgia",
                ),
                ft.Text(
                    "Access legislative information, official documents, and public records of the Sangguniang Bayan of Tolosa through one centralized digital platform.",
                    size=15,
                    color=muted,
                ),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "EXPLORE PUBLIC DOCUMENTS ->",
                            color="#ffffff",
                            bgcolor=navy,
                            style=ft.ButtonStyle(padding=ft.Padding(18, 13, 18, 13)),
                        ),
                        ft.TextButton(
                            text="LEARN ABOUT THE SYSTEM",
                            style=ft.ButtonStyle(color=navy, padding=ft.Padding(8, 13, 8, 13)),
                        ),
                    ],
                    spacing=8,
                    wrap=True,
                ),
            ],
            spacing=18,
        ),
        bgcolor="#ffffff",
        padding=ft.Padding(30, 34, 30, 34),
        col={"xs": 12, "md": 5},
    )

    hero_image = ft.Container(
        content=ft.Image(src=hero_photo, fit=ft.ImageFit.COVER, expand=True),
        aspect_ratio=1.55,
        col={"xs": 12, "md": 7},
        border_radius=12,
        shadow=ft.BoxShadow(blur_radius=16, spread_radius=1, color="#17304220", offset=ft.Offset(0, 5)),
    )

    hero = ft.Container(
        content=ft.ResponsiveRow([hero_content, hero_image], spacing=34, run_spacing=24),
        bgcolor="#f7faf9",
        padding=ft.Padding(34, 46, 34, 54),
    )

    def access_item(icon, title, description):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, color=gold, size=24),
                    ft.Column(
                        [
                            ft.Text(title, size=12, color=navy, weight=ft.FontWeight.BOLD),
                            ft.Text(description, size=12, color=muted),
                        ],
                        spacing=5,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding(4, 6, 4, 6),
            col={"xs": 12, "md": 4},
        )

    quick_access = ft.Container(
        content=ft.ResponsiveRow(
            [
                access_item(ft.Icons.DESCRIPTION_OUTLINED, "PUBLIC DOCUMENTS", "Browse available legislative records and documents."),
                access_item(ft.Icons.CAMPAIGN_OUTLINED, "ANNOUNCEMENTS", "View public notices and legislative updates."),
                access_item(ft.Icons.INFO_OUTLINED, "ABOUT THE SYSTEM", "Learn how the digital tracking system supports transparency."),
            ],
            spacing=26,
            run_spacing=14,
        ),
        bgcolor="#ffffff",
        padding=ft.Padding(30, 22, 30, 22),
        border=ft.border.only(top=ft.border.all(1, "#dce7e5"), bottom=ft.border.all(1, "#dce7e5")),
    )

    system_intro = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("ABOUT THE SYSTEM", size=12, color=teal, weight=ft.FontWeight.BOLD),
                            ft.Text("A clearer way to follow local legislation", size=28, color=ink, weight=ft.FontWeight.BOLD, font_family="Georgia"),
                        ],
                        spacing=12,
                    ),
                    col={"xs": 12, "md": 5},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("The Legislative Document Tracking Management System brings the records of the Sangguniang Bayan of Tolosa into one organized digital space.", size=15, color=ink),
                            ft.Text("It helps the public find available ordinances, resolutions, and legislative information with greater convenience and confidence.", size=14, color=muted),
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.VERIFIED_OUTLINED, color=gold, size=20),
                                    ft.Text("Designed to support transparent public service", size=13, color=teal, weight=ft.FontWeight.BOLD),
                                ],
                                spacing=9,
                            ),
                        ],
                        spacing=14,
                    ),
                    col={"xs": 12, "md": 7},
                ),
            ],
            spacing=34,
            run_spacing=22,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor="#f7faf9",
        border=ft.border.only(top=ft.border.all(1, "#dce7e5"), bottom=ft.border.all(1, "#dce7e5")),
        padding=ft.Padding(44, 42, 44, 42),
        key="about-section",
    )

    records_promo = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("PUBLIC RECORDS", size=12, color="#e1bd72", weight=ft.FontWeight.BOLD),
                            ft.Text("Explore Public Legislative Records", size=27, color="#ffffff", weight=ft.FontWeight.BOLD, font_family="Georgia"),
                            ft.Text("Find publicly available ordinances, resolutions, and other legislative documents of the Sangguniang Bayan of Tolosa.", size=14, color="#dbeae5"),
                        ],
                        spacing=12,
                    ),
                    col={"xs": 12, "md": 8},
                ),
                ft.Container(
                    content=ft.ElevatedButton("VIEW PUBLIC DOCUMENTS ->", color=navy, bgcolor=gold, style=ft.ButtonStyle(padding=ft.Padding(18, 13, 18, 13))),
                    alignment=ft.Alignment.CENTER_RIGHT,
                    col={"xs": 12, "md": 4},
                ),
            ],
            spacing=20,
            run_spacing=18,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=navy,
        padding=ft.Padding(42, 34, 42, 34),
        key="records-section",
    )

    announcements = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("ANNOUNCEMENTS", size=12, color=teal, weight=ft.FontWeight.BOLD),
                            ft.Text("What is happening in Tolosa", size=27, color=ink, weight=ft.FontWeight.BOLD, font_family="Georgia"),
                            ft.Text("Public notices and legislative updates from the Sangguniang Bayan.", size=14, color=muted),
                        ],
                        spacing=12,
                    ),
                    col={"xs": 12, "md": 4},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Column(
                                            [
                                                ft.Text("PUBLIC NOTICE", size=11, color=gold, weight=ft.FontWeight.BOLD),
                                                ft.Text("Public sessions and notices", size=14, color=ink, weight=ft.FontWeight.BOLD),
                                            ],
                                            spacing=5,
                                            expand=True,
                                        ),
                                        ft.Text("NOTICE", size=10, color=muted),
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.START,
                                ),
                                padding=ft.Padding(0, 0, 0, 14),
                                border=ft.border.only(bottom=ft.border.all(1, "#dce7e5")),
                            ),
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Column(
                                            [
                                                ft.Text("LEGISLATIVE UPDATE", size=11, color=gold, weight=ft.FontWeight.BOLD),
                                                ft.Text("Official records and updates", size=14, color=ink, weight=ft.FontWeight.BOLD),
                                            ],
                                            spacing=5,
                                            expand=True,
                                        ),
                                        ft.Text("UPDATE", size=10, color=muted),
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.START,
                                ),
                                padding=ft.Padding(0, 14, 0, 0),
                            ),
                        ],
                        spacing=0,
                    ),
                    col={"xs": 12, "md": 8},
                ),
            ],
            spacing=36,
            run_spacing=24,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor="#ffffff",
        padding=ft.Padding(44, 46, 44, 46),
        border=ft.border.only(top=ft.border.all(1, "#dce7e5")),
        key="announcements-section",
    )

    civic_message = ft.Container(
        content=ft.Column(
            [
                ft.Text("Information for the Community", size=24, color=ink, weight=ft.FontWeight.BOLD, font_family="Georgia"),
                ft.Text("Providing accessible legislative information helps promote transparency, accountability, and informed participation in the community.", size=14, color=muted, text_align=ft.TextAlign.CENTER),
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor="#ffffff",
        padding=ft.Padding(40, 44, 40, 44),
    )

    footer = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("SANGGUNIAN BAYAN", size=15, color="#ffffff", weight=ft.FontWeight.BOLD),
                            ft.Text("Municipality of Tolosa", size=12, color="#c5d9d7"),
                            ft.Text("Legislative Document Tracking Management System", size=12, color="#c5d9d7"),
                        ],
                        spacing=6,
                    ),
                    col={"xs": 12, "md": 5},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("CONTACT", size=11, color="#e1bd72", weight=ft.FontWeight.BOLD),
                            ft.Text("Municipal Hall, Tolosa, Leyte", size=12, color="#ffffff"),
                            ft.Text("For public information and legislative concerns, visit the Municipal Hall.", size=12, color="#c5d9d7"),
                        ],
                        spacing=8,
                    ),
                    col={"xs": 12, "md": 4},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("EXPLORE", size=11, color="#e1bd72", weight=ft.FontWeight.BOLD),
                            ft.Text("Home  ·  About  ·  Public Documents", size=12, color="#ffffff"),
                            ft.Text("Announcements  ·  Contact", size=12, color="#ffffff"),
                        ],
                        spacing=8,
                    ),
                    col={"xs": 12, "md": 3},
                ),
                ft.Container(
                    content=ft.Text("© Municipality of Tolosa. All rights reserved.", size=11, color="#c5d9d7"),
                    padding=ft.Padding(0, 16, 0, 0),
                    border=ft.border.only(top=ft.border.all(1, "#315463")),
                    col={"xs": 12, "md": 12},
                ),
            ],
            spacing=28,
            run_spacing=24,
        ),
        bgcolor=navy,
        padding=ft.Padding(38, 38, 30, 24),
        key="contact-section",
    )

    homepage_content = ft.Column(
        [
            hero,
            system_intro,
            records_promo,
            announcements,
            footer,
        ],
        spacing=0,
    )

    content_scroll = ft.Column(
        [utility_bar, homepage_content],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    return ft.Column(
        [navigation, content_scroll],
        spacing=0,
        expand=True,
    )
