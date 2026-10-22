import os

import flet as ft
import requests
from frontend.admin.app import main as admin_main
from frontend import theme

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")

# Shown when the backend cannot be reached; matches the backend's defaults.
DEFAULT_ANNOUNCEMENTS = [
    {"category": "PUBLIC NOTICE", "title": "Public sessions and notices", "date": "", "details": ""},
    {"category": "LEGISLATIVE UPDATE", "title": "Official records and updates", "date": "", "details": ""},
]

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


def load_homepage_announcements():
    """The announcements a Super Administrator set in Settings, or the defaults if the backend is unreachable."""
    try:
        response = requests.get(f"{BACKEND_URL}/public/announcements", timeout=5)
        response.raise_for_status()
        announcements = response.json().get("announcements")
        if isinstance(announcements, list):
            return [item for item in announcements if isinstance(item, dict)]
    except (requests.RequestException, ValueError, AttributeError):
        pass
    return DEFAULT_ANNOUNCEMENTS


def build_homepage_view(page=None):
    is_dark = False
    if page is not None:
        try:
            is_dark = bool(page.client_storage.get("sb_night_mode"))
            page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        except Exception:
            pass

    # The login page's and admin workspace's colours (frontend/theme.py).
    navy = theme.NAVY
    label_blue = theme.PRIMARY if not is_dark else "#8cb8f0"
    ink = theme.INK if not is_dark else theme.NIGHT_INK
    muted = theme.MUTED if not is_dark else theme.NIGHT_MUTED
    line = theme.BORDER if not is_dark else theme.NIGHT_BORDER
    surface = "#ffffff" if not is_dark else theme.NIGHT_SURFACE
    canvas = theme.CANVAS if not is_dark else theme.NIGHT_CANVAS
    hero_photo = "sb_tolosa_homepage.jpg"

    night_mode_button = None

    def visual_link(label, color=ink, on_click=None):
        return ft.TextButton(
            text=label,
            on_click=on_click,
            style=ft.ButtonStyle(color=color, padding=ft.Padding(8, 8, 8, 8)),
        )

    def open_login(_):
        if page is not None:
            admin_main(page)

    def open_public_documents(_):
        if page is not None:
            try:
                from frontend.frontend_public.public_portal import build_public_portal
                page.clean()
                page.add(build_public_portal(page))
                page.update()
            except Exception:
                pass

    def toggle_night_mode(_):
        nonlocal is_dark
        is_dark = not is_dark
        if page is not None:
            page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
            page.bgcolor = theme.NIGHT_CANVAS if is_dark else theme.CANVAS
            try:
                page.client_storage.set("sb_night_mode", is_dark)
            except Exception:
                pass
            page.clean()
            page.add(build_homepage_view(page))
            page.update()

    night_mode_button = ft.IconButton(
        icon=(ft.Icons.LIGHT_MODE if is_dark else ft.Icons.DARK_MODE),
        tooltip=("Switch to light mode" if is_dark else "Switch to night mode"),
        on_click=toggle_night_mode,
    )

    utility_bar = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Text(
                        "Republic of the Philippines  •  Province of Leyte  •  Municipality of Tolosa",
                        size=11,
                        color=theme.ON_BLUE_MUTED,
                    ),
                    col={"xs": 12, "md": 8},
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text("Accessibility", size=11, color=theme.ON_BLUE_MUTED),
                            ft.Text("Contact", size=11, color=theme.ON_BLUE_MUTED),
                            ft.Text("Help", size=11, color=theme.ON_BLUE_MUTED),
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

    brand = theme.brand(on_blue=is_dark)

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
                            night_mode_button,
                            visual_link("Login", label_blue, on_click=open_login),
                            theme.primary_button("Public Documents", on_click=open_public_documents, height=42),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                    ),
                    col={"xs": 12, "lg": 3},
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=surface,
        padding=ft.Padding(28, 12, 28, 12),
        shadow=ft.BoxShadow(blur_radius=12, color=ft.Colors.with_opacity(0.08, "#0c4279"), offset=ft.Offset(0, 3)),
    )

    hero_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("SANGGUNIANG BAYAN OF TOLOSA", size=12, color=label_blue, weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=2)),
                theme.accent_bar(),
                ft.Text(
                    "Legislative Documents, Made Accessible.",
                    size=34,
                    color=navy if not is_dark else ink,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Access legislative information, official documents, and public records of the Sangguniang Bayan of Tolosa through one centralized digital platform.",
                    size=15,
                    color=muted,
                ),
                ft.Row(
                    [theme.primary_button("Explore Public Documents", on_click=open_public_documents, icon=ft.Icons.ARROW_FORWARD)],
                    spacing=8,
                    wrap=True,
                ),
            ],
            spacing=18,
        ),
        bgcolor=surface,
        border_radius=24,
        padding=ft.Padding(32, 34, 32, 34),
        shadow=ft.BoxShadow(blur_radius=40, offset=ft.Offset(0, 16), color=ft.Colors.with_opacity(0.12, "#0c4279")),
        col={"xs": 12, "md": 5},
    )

    # The town hall under the login page's blue wash.
    hero_image = ft.Container(
        content=ft.Stack(
            [
                ft.Image(src=hero_photo, fit=ft.ImageFit.COVER, expand=True),
                ft.Container(
                    expand=True,
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment(0, -1),
                        end=ft.Alignment(0, 1),
                        colors=[ft.Colors.with_opacity(0.15, "#044184"), ft.Colors.with_opacity(0.55, "#03346f")],
                    ),
                ),
            ],
            expand=True,
        ),
        aspect_ratio=1.55,
        col={"xs": 12, "md": 7},
        border_radius=24,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        shadow=ft.BoxShadow(blur_radius=40, offset=ft.Offset(0, 16), color=ft.Colors.with_opacity(0.12, "#0c4279")),
    )

    hero = ft.Container(
        content=ft.ResponsiveRow([hero_content, hero_image], spacing=34, run_spacing=24, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=canvas,
        padding=ft.Padding(34, 46, 34, 54),
    )

    def access_item(icon, title, description):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, color=label_blue, size=24),
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
        bgcolor=surface,
        padding=ft.Padding(30, 22, 30, 22),
        border=ft.Border(top=ft.BorderSide(1, line), bottom=ft.BorderSide(1, line)),
    )

    system_intro = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("ABOUT THE SYSTEM", size=12, color=label_blue, weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=2)),
                            ft.Text("A clearer way to follow local legislation", size=28, color=ink, weight=ft.FontWeight.BOLD),
                            theme.accent_bar(),
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
                                    ft.Icon(ft.Icons.VERIFIED_OUTLINED, color=label_blue, size=20),
                                    ft.Text("Designed to support transparent public service", size=13, color=label_blue, weight=ft.FontWeight.BOLD),
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
        bgcolor=surface,
        border=ft.Border(top=ft.BorderSide(1, line), bottom=ft.BorderSide(1, line)),
        padding=ft.Padding(44, 42, 44, 42),
        key="about-section",
    )

    records_promo = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("PUBLIC RECORDS", size=12, color=theme.ACCENT, weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=2)),
                            ft.Text("Explore Public Legislative Records", size=27, color=theme.ON_BLUE, weight=ft.FontWeight.BOLD),
                            ft.Text("Find publicly available ordinances, resolutions, and other legislative documents of the Sangguniang Bayan of Tolosa.", size=14, color=theme.ON_BLUE_MUTED),
                        ],
                        spacing=12,
                    ),
                    col={"xs": 12, "md": 8},
                ),
                ft.Container(
                    content=ft.ElevatedButton(
                        "View Public Documents",
                        icon=ft.Icons.ARROW_FORWARD,
                        color=navy,
                        bgcolor=ft.Colors.WHITE,
                        style=ft.ButtonStyle(padding=ft.Padding(22, 16, 22, 16), shape=ft.RoundedRectangleBorder(radius=13)),
                        on_click=open_public_documents,
                    ),
                    alignment=ft.Alignment.CENTER_RIGHT,
                    col={"xs": 12, "md": 4},
                ),
            ],
            spacing=20,
            run_spacing=18,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        gradient=theme.blue_band_gradient(),
        padding=ft.Padding(42, 34, 42, 34),
        key="records-section",
    )

    def announcement_row(item, first, last):
        heading = [
            ft.Text((item.get("category") or "").upper(), size=11, color=label_blue, weight=ft.FontWeight.BOLD),
            ft.Text(item.get("title") or "", size=14, color=ink, weight=ft.FontWeight.BOLD),
        ]
        if item.get("details"):
            heading.append(ft.Text(item["details"], size=12, color=muted))
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(heading, spacing=5, expand=True),
                    ft.Text(item.get("date") or "", size=10, color=muted),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding(0, 0 if first else 14, 0, 0 if last else 14),
            border=None if last else ft.Border(bottom=ft.BorderSide(1, line)),
        )

    announcement_items = load_homepage_announcements()
    announcement_rows = [
        announcement_row(item, index == 0, index == len(announcement_items) - 1)
        for index, item in enumerate(announcement_items)
    ] or [ft.Text("There are no announcements right now.", size=14, color=muted)]

    announcements = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("ANNOUNCEMENTS", size=12, color=label_blue, weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=2)),
                            ft.Text("What is happening in Tolosa", size=27, color=ink, weight=ft.FontWeight.BOLD),
                            theme.accent_bar(),
                            ft.Text("Public notices and legislative updates from the Sangguniang Bayan.", size=14, color=muted),
                        ],
                        spacing=12,
                    ),
                    col={"xs": 12, "md": 4},
                ),
                ft.Container(
                    content=ft.Column(announcement_rows, spacing=0),
                    bgcolor=surface,
                    border=ft.border.all(1, line),
                    border_radius=18,
                    padding=24,
                    shadow=ft.BoxShadow(blur_radius=10, offset=ft.Offset(0, 2), color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK)),
                    col={"xs": 12, "md": 8},
                ),
            ],
            spacing=36,
            run_spacing=24,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=canvas,
        padding=ft.Padding(44, 46, 44, 46),
        key="announcements-section",
    )

    civic_message = ft.Container(
        content=ft.Column(
            [
                ft.Text("Information for the Community", size=24, color=ink, weight=ft.FontWeight.BOLD),
                ft.Text("Providing accessible legislative information helps promote transparency, accountability, and informed participation in the community.", size=14, color=muted, text_align=ft.TextAlign.CENTER),
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=surface,
        padding=ft.Padding(40, 44, 40, 44),
    )

    footer = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            theme.brand(subtitle="Municipality of Tolosa", on_blue=True),
                            ft.Text("Legislative Document Tracking Management System", size=12, color=theme.ON_BLUE_MUTED),
                        ],
                        spacing=10,
                    ),
                    col={"xs": 12, "md": 5},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("CONTACT", size=11, color=theme.ACCENT, weight=ft.FontWeight.BOLD),
                            ft.Text("Municipal Hall, Tolosa, Leyte", size=12, color=theme.ON_BLUE),
                            ft.Text("For public information and legislative concerns, visit the Municipal Hall.", size=12, color=theme.ON_BLUE_MUTED),
                        ],
                        spacing=8,
                    ),
                    col={"xs": 12, "md": 4},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("EXPLORE", size=11, color=theme.ACCENT, weight=ft.FontWeight.BOLD),
                            ft.Text("Home  ·  About  ·  Public Documents", size=12, color=theme.ON_BLUE),
                            ft.Text("Announcements  ·  Contact", size=12, color=theme.ON_BLUE),
                        ],
                        spacing=8,
                    ),
                    col={"xs": 12, "md": 3},
                ),
                ft.Container(
                    content=ft.Text("© Municipality of Tolosa. All rights reserved.", size=11, color=theme.ON_BLUE_MUTED),
                    padding=ft.Padding(0, 16, 0, 0),
                    border=ft.Border(top=ft.BorderSide(1, ft.Colors.with_opacity(0.2, ft.Colors.WHITE))),
                    col={"xs": 12, "md": 12},
                ),
            ],
            spacing=28,
            run_spacing=24,
        ),
        gradient=theme.blue_band_gradient(),
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
