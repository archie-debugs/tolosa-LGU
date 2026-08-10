import base64
import mimetypes
import os
import sys
from pathlib import Path
import flet as ft

ft.Colors = ft.colors

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.frontend_admin.app import main as admin_main

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOCAL_HERO_IMAGE_PATH = ASSETS_DIR / "sb_tolosa_homepage.jpg"
if not LOCAL_HERO_IMAGE_PATH.exists() and ASSETS_DIR.exists():
    LOCAL_HERO_IMAGE_PATH = next(
        (p for p in ASSETS_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}),
        LOCAL_HERO_IMAGE_PATH,
    )


def _local_image_data_uri(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type is None:
        mime_type = "image/jpeg"
    with path.open("rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"

if LOCAL_HERO_IMAGE_PATH.exists():
    HERO_IMAGE = _local_image_data_uri(LOCAL_HERO_IMAGE_PATH)
else:
    HERO_IMAGE = "https://images.unsplash.com/photo-1519125323398-675f0ddb6308?auto=format&fit=crop&w=1600&q=80"

CARD_IMAGES = {
    "Public Documents": "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?auto=format&fit=crop&w=800&q=80",
    "Document Records": "https://images.unsplash.com/photo-1496307042754-b4aa456c4a2d?auto=format&fit=crop&w=800&q=80",
    "Announcements": "https://images.unsplash.com/photo-1556761175-4b46a572b786?auto=format&fit=crop&w=800&q=80",
    "About the Sangguniang Bayan": "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=800&q=80",
}

RECENT_DOCUMENTS = [
    {
        "tracking_number": "DOC-001",
        "title": "Resolution No. 2026-001",
        "document_type": "Resolution",
        "date": "August 2026",
        "status": "Published",
    },
    {
        "tracking_number": "DOC-002",
        "title": "Ordinance No. 2026-004",
        "document_type": "Ordinance",
        "date": "July 2026",
        "status": "Published",
    },
    {
        "tracking_number": "DOC-003",
        "title": "Resolution No. 2026-007",
        "document_type": "Resolution",
        "date": "June 2026",
        "status": "Published",
    },
    {
        "tracking_number": "DOC-004",
        "title": "Ordinance No. 2025-022",
        "document_type": "Ordinance",
        "date": "December 2025",
        "status": "Published",
    },
]

ANNOUNCEMENTS = [
    {
        "date": "September 5, 2026",
        "title": "Public consultation schedule announced",
        "description": "The Sangguniang Bayan will host a public consultation on legislative transparency initiatives.",
    },
    {
        "date": "August 22, 2026",
        "title": "New open access document portal launched",
        "description": "Residents can now search published legislative documents with improved accessibility.",
    },
    {
        "date": "August 1, 2026",
        "title": "Municipal resolution archive updated",
        "description": "Recent resolutions and ordinances are now available in the public records section.",
    },
]

DOCUMENT_TYPES = ["All", "Resolution", "Ordinance", "Memorandum"]
DOCUMENT_YEARS = ["All", "2026", "2025", "2024"]


def build_top_bar():
    return ft.Container(
        bgcolor=ft.Colors.BLUE_GREY_900,
        padding=ft.Padding(8, 6, 8, 6),
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Text("Republic of the Philippines", size=11, color=ft.Colors.WHITE70),
                        ft.Container(width=1, height=14, bgcolor=ft.Colors.WHITE12),
                        ft.Text("Province of Leyte", size=11, color=ft.Colors.WHITE70),
                        ft.Container(width=1, height=14, bgcolor=ft.Colors.WHITE12),
                        ft.Text("Municipality of Tolosa", size=11, color=ft.Colors.WHITE70),
                    ], spacing=12,
                ),
                ft.Row(
                    [
                        ft.TextButton(content=ft.Text("Accessibility", size=11, color=ft.Colors.WHITE70)),
                        ft.TextButton(content=ft.Text("Contact", size=11, color=ft.Colors.WHITE70)),
                        ft.TextButton(content=ft.Text("Help", size=11, color=ft.Colors.WHITE70)),
                    ], spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def build_nav_bar(open_admin_login, focus_search):
    nav_items = ["Home", "About", "Documents", "Public Records", "Announcements", "Contact"]
    nav_buttons = [
        ft.TextButton(content=ft.Text(item, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_800))
        for item in nav_items
    ]

    return ft.Container(
        bgcolor=ft.Colors.WHITE,
        padding=ft.Padding(22, 18, 22, 18),
        border=ft.border.all(1, ft.Colors.BLUE_GREY_50),
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.icons.ACCOUNT_BALANCE, size=28, color=ft.Colors.BLUE_900),
                            padding=12,
                            bgcolor=ft.Colors.BLUE_GREY_50,
                            border_radius=14,
                        ),
                        ft.Column(
                            [
                                ft.Text("SANGGUNIANG BAYAN", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                                ft.Text("MUNICIPALITY OF TOLOSA", size=11, color=ft.Colors.BLUE_GREY_700),
                            ], spacing=2,
                        ),
                    ], spacing=14,
                ),
                ft.Row(nav_buttons, spacing=18, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row(
                    [
                        ft.TextButton(content=ft.Text("Staff Login", color=ft.Colors.BLUE_GREY_700), on_click=open_admin_login),
                        ft.ElevatedButton("Public Document Portal", on_click=lambda _: focus_search(), bgcolor=ft.Colors.BLUE_900, color=ft.Colors.WHITE),
                    ], spacing=12,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        ),
    )


def build_hero_section(focus_search):
    return ft.Stack(
        [
            ft.Container(
                width="100%",
                height=520,
                image_src=HERO_IMAGE,
                image_fit=ft.ImageFit.COVER,
            ),
            ft.Container(
                width="100%",
                height=520,
                bgcolor="#C30A1836",
            ),
            ft.Container(
                width="100%",
                height=520,
                padding=ft.Padding(40, 40, 40, 40),
                content=ft.Column(
                    [
                        ft.Container(height=8),
                        ft.Text("Welcome to the Sangguniang Bayan of Tolosa", size=44, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE, font_family="Inter"),
                        ft.Container(height=16),
                        ft.Text("Legislative Document Tracking Management System", size=20, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE70),
                        ft.Container(height=18),
                        ft.Text(
                            "Access, search, and track publicly available legislative documents of the Sangguniang Bayan of Tolosa.",
                            size=15,
                            color=ft.Colors.WHITE70,
                            width=680,
                        ),
                        ft.Container(height=24),
                        ft.Row(
                            [
                                ft.ElevatedButton("Search Documents", on_click=lambda _: focus_search(), bgcolor=ft.Colors.GREY_50, color=ft.Colors.BLUE_900),
                                ft.ElevatedButton("Public Document Portal", on_click=lambda _: focus_search(), bgcolor="#FFB300", color=ft.Colors.WHITE),
                            ],
                            spacing=14,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    spacing=12,
                ),
                alignment=ft.alignment.center_left,
            ),
        ],
        width="100%",
    )


def build_card(title, description, image_url, on_click):
    return ft.Container(
        expand=True,
        height=240,
        border_radius=18,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        image_src=image_url,
        image_fit=ft.ImageFit.COVER,
        gradient=ft.LinearGradient(begin=ft.alignment.top_center, end=ft.alignment.bottom_center, colors=["#0014203d", "#C30A1228"]),
        content=ft.Container(
            padding=ft.Padding(18, 18, 18, 18),
            alignment=ft.Alignment.BOTTOM_LEFT,
            content=ft.Column(
                [
                    ft.Text(title, size=18, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE),
                    ft.Text(description, size=13, color=ft.Colors.WHITE70, width=320),
                ],
                alignment=ft.MainAxisAlignment.END,
                spacing=6,
            ),
        ),
        on_click=on_click,
        tooltip=title,
    )


def build_quick_access_cards(on_public_documents, on_document_records, on_announcements, on_about):
    return ft.Row(
        [
            build_card("Public Documents", "Search and view published legislative documents.", CARD_IMAGES["Public Documents"], on_public_documents),
            build_card("Document Records", "Browse ordinances, resolutions, and other legislative records.", CARD_IMAGES["Document Records"], on_document_records),
            build_card("Announcements", "View the latest announcements and legislative updates.", CARD_IMAGES["Announcements"], on_announcements),
            build_card("About the Sangguniang Bayan", "Learn about the Sangguniang Bayan of Tolosa and its functions.", CARD_IMAGES["About the Sangguniang Bayan"], on_about),
        ],
        spacing=18,
        expand=True,
        wrap=True,
    )


def build_search_section(search_input, type_dropdown, year_dropdown, search_button):
    return ft.Container(
        padding=ft.Padding(24, 24, 24, 24),
        border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
        border_radius=20,
        bgcolor=ft.Colors.WHITE,
        content=ft.Column(
            [
                ft.Text("Search Legislative Documents", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                ft.Text("Find published documents quickly by tracking number, title, or keyword.", size=13, color=ft.Colors.BLUE_GREY_600),
                ft.Container(height=18),
                ft.Row(
                    [
                        search_input,
                        type_dropdown,
                        year_dropdown,
                        search_button,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                    spacing=12,
                ),
            ],
            spacing=12,
        ),
        width="100%",
    )


def build_document_row(document):
    status_color = ft.Colors.GREEN_700 if document["status"] == "Published" else ft.Colors.BLUE_GREY_700
    return ft.Container(
        padding=ft.Padding(18, 14, 18, 14),
        border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.BLUE_GREY_50)),
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(document["tracking_number"], size=12, weight=ft.FontWeight.BOLD),
                        ft.Text(document["title"], size=14, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_900),
                    ], spacing=6, expand=True,
                ),
                ft.Text(document["document_type"], size=12, color=ft.Colors.BLUE_GREY_700),
                ft.Text(document["date"], size=12, color=ft.Colors.BLUE_GREY_700),
                ft.Container(
                    content=ft.Text(document["status"], size=12, color=ft.Colors.WHITE),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=12,
                    bgcolor=status_color,
                ),
            ],
            alignment=ft.CrossAxisAlignment.CENTER,
            spacing=18,
        ),
    )


def build_recent_documents_section(results_container):
    header = ft.Row(
        [
            ft.Text("Recent Legislative Documents", size=22, weight=ft.FontWeight.BOLD),
            ft.Text("Publicly available documents published by the Sangguniang Bayan of Tolosa.", size=13, color=ft.Colors.BLUE_GREY_600),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        wrap=True,
    )
    return ft.Container(
        padding=ft.Padding(24, 24, 24, 24),
        border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
        border_radius=20,
        bgcolor=ft.Colors.WHITE,
        content=ft.Column([header, ft.Container(height=14), results_container]),
    )


def build_announcements_section():
    cards = []
    for announcement in ANNOUNCEMENTS:
        cards.append(
            ft.Container(
                expand=True,
                padding=ft.Padding(18, 18, 18, 18),
                border_radius=18,
                bgcolor=ft.Colors.BLUE_GREY_900,
                content=ft.Column(
                    [
                        ft.Text(announcement["date"], size=11, color=ft.Colors.BLUE_GREY_200),
                        ft.Text(announcement["title"], size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        ft.Text(announcement["description"], size=13, color=ft.Colors.WHITE70, max_lines=3),
                        ft.Container(height=12),
                        ft.TextButton(content=ft.Text("Read More", color="#FBBF24")),
                    ],
                    spacing=10,
                ),
            )
        )
    return ft.Container(
        padding=ft.Padding(24, 24, 24, 24),
        border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
        border_radius=20,
        bgcolor=ft.Colors.WHITE,
        content=ft.Column(
            [
                ft.Text("Latest Announcements", size=22, weight=ft.FontWeight.BOLD),
                ft.Text("Read the latest news and policy updates from the Sangguniang Bayan.", size=13, color=ft.Colors.BLUE_GREY_600),
                ft.Container(height=18),
                ft.Row(cards, spacing=18, wrap=True),
            ],
            spacing=12,
        ),
    )


def build_about_section():
    return ft.Container(
        padding=ft.Padding(24, 24, 24, 24),
        bgcolor=ft.Colors.WHITE,
        border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
        border_radius=20,
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Legislative Document Tracking Management System", size=22, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "The system is designed to organize legislative documents, maintain document records, provide efficient retrieval, support transparency, and provide public access to published legislative documents.",
                            size=13,
                            color=ft.Colors.BLUE_GREY_700,
                        ),
                        ft.Container(height=16),
                        ft.Row(
                            [
                                ft.Column([
                                    ft.Text("• Organize legislative documents", size=13, color=ft.Colors.BLUE_GREY_800),
                                    ft.Text("• Maintain official document records", size=13, color=ft.Colors.BLUE_GREY_800),
                                    ft.Text("• Provide efficient retrieval", size=13, color=ft.Colors.BLUE_GREY_800),
                                ], spacing=10),
                                ft.Column([
                                    ft.Text("• Support transparency", size=13, color=ft.Colors.BLUE_GREY_800),
                                    ft.Text("• Enable public access", size=13, color=ft.Colors.BLUE_GREY_800),
                                ], spacing=10),
                            ],
                            spacing=48,
                            wrap=True,
                        ),
                    ],
                    expand=True,
                ),
                ft.Container(
                    width=280,
                    height=220,
                    image_src=CARD_IMAGES["About the Sangguniang Bayan"],
                    image_fit=ft.ImageFit.COVER,
                    border_radius=18,
                ),
            ],
            spacing=24,
            wrap=True,
        ),
    )


def build_footer():
    return ft.Container(
        padding=ft.Padding(28, 28, 28, 28),
        bgcolor=ft.Colors.BLUE_GREY_900,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Sangguniang Bayan of Tolosa", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                ft.Text("Municipality of Tolosa, Leyte, Philippines", size=12, color=ft.Colors.WHITE70),
                                ft.Container(height=12),
                                ft.Text("Office of the Municipal Legislators", size=12, color=ft.Colors.WHITE70),
                                ft.Text("Website: sbtolosa.gov.ph", size=12, color=ft.Colors.WHITE70),
                                ft.Text("Email: info@sbtolosa.gov.ph", size=12, color=ft.Colors.WHITE70),
                            ], spacing=6,
                        ),
                        ft.Column(
                            [
                                ft.Text("Quick Links", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                ft.TextButton(content=ft.Text("Public Document Portal", color="#FBBF24")),
                                ft.TextButton(content=ft.Text("Privacy Policy", color="#FBBF24")),
                                ft.TextButton(content=ft.Text("Terms / Policies", color="#FBBF24")),
                            ], spacing=6,
                        ),
                        ft.Column(
                            [
                                ft.Text("Office Hours", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                ft.Text("Mon - Fri | 8:00 AM - 5:00 PM", size=12, color=ft.Colors.WHITE70),
                                ft.Text("Closed on weekends and holidays", size=12, color=ft.Colors.WHITE70),
                            ], spacing=6,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True,
                ),
                ft.Divider(thickness=1, color=ft.Colors.WHITE12),
                ft.Row(
                    [
                        ft.Text("© 2026 Sangguniang Bayan of Tolosa. All Rights Reserved.", size=11, color=ft.Colors.WHITE70),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=18,
        ),
    )


def render_public_home(page: ft.Page):
    page.title = "Sangguniang Bayan of Tolosa | Public Legislative Portal"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.BLUE_GREY_50
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 0

    search_input = ft.TextField(
        label="Search by tracking number, title, or keyword",
        width=420,
        filled=True,
        border_radius=16,
        bgcolor=ft.Colors.WHITE,
    )
    type_dropdown = ft.Dropdown(
        label="Document Type",
        width=200,
        options=[ft.dropdown.Option(item) for item in DOCUMENT_TYPES],
        value="All",
    )
    year_dropdown = ft.Dropdown(
        label="Year",
        width=140,
        options=[ft.dropdown.Option(item) for item in DOCUMENT_YEARS],
        value="All",
    )
    results_container = ft.Column()

    def refresh_documents(_=None):
        query = (search_input.value or "").strip().lower()
        document_type = type_dropdown.value or "All"
        year_value = year_dropdown.value or "All"
        filtered = []
        for document in RECENT_DOCUMENTS:
            matches_query = (not query) or any(query in str(document[field]).lower() for field in ["tracking_number", "title", "document_type", "date"])
            matches_type = document_type == "All" or document["document_type"] == document_type
            matches_year = year_value == "All" or year_value in document["date"]
            if matches_query and matches_type and matches_year:
                filtered.append(document)
        if not filtered:
            results_container.controls = [
                ft.Container(
                    content=ft.Text("No documents match your search. Please try another keyword or filter.", color=ft.Colors.BLUE_GREY_700),
                    padding=ft.Padding(18, 18, 18, 18),
                )
            ]
        else:
            results_container.controls = [build_document_row(doc) for doc in filtered]
        page.update()

    def open_admin_login(_=None):
        page.clean()
        page.padding = 8
        admin_main(page)

    def focus_search():
        search_input.focus()
        page.update()

    build_hero = build_hero_section(focus_search)
    search_section = build_search_section(search_input, type_dropdown, year_dropdown, ft.ElevatedButton("Search", on_click=refresh_documents, bgcolor=ft.Colors.BLUE_900, color=ft.Colors.WHITE))
    quick_cards = build_quick_access_cards(
        lambda _: focus_search(),
        lambda _: focus_search(),
        lambda _: page.update(),
        lambda _: page.update(),
    )

    refresh_documents()

    page.add(
        ft.Column(
            [
                build_top_bar(),
                build_nav_bar(open_admin_login, focus_search),
                build_hero,
                ft.Container(height=24),
                ft.Container(
                    padding=ft.Padding(0, 0, 0, 0),
                    content=ft.Column(
                        [
                            quick_cards,
                            ft.Container(height=24),
                            search_section,
                            ft.Container(height=24),
                            build_recent_documents_section(results_container),
                            ft.Container(height=24),
                            build_announcements_section(),
                            ft.Container(height=24),
                            build_about_section(),
                            ft.Container(height=24),
                            build_footer(),
                        ],
                        spacing=24,
                    ),
                ),
            ],
            spacing=0,
            expand=True,
        )
    )


def main(page: ft.Page):
    render_public_home(page)


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
