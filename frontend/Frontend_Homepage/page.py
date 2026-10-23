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

# Below this width the town hall photo is dropped from the hero, so the heading has room.
NARROW_WIDTH = 900

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


def load_homepage_stats():
    """GET /public/stats, or None if the backend is unreachable (the hero then shows no counts)."""
    try:
        response = requests.get(f"{BACKEND_URL}/public/stats", timeout=5)
        response.raise_for_status()
        stats = response.json()
        if isinstance(stats, dict):
            return stats
    except (requests.RequestException, ValueError):
        pass
    return None


def announcement_style(category):
    """(icon, colour) for an announcement, from words in its category."""
    text = (category or "").lower()
    if "session" in text:
        return ft.Icons.EVENT_OUTLINED, ft.Colors.DEEP_PURPLE_400
    if "document" in text or "update" in text or "record" in text:
        return ft.Icons.DESCRIPTION_OUTLINED, ft.Colors.GREEN_600
    if "notice" in text:
        return ft.Icons.CAMPAIGN_OUTLINED, ft.Colors.BLUE_600
    return ft.Icons.INFO_OUTLINE, ft.Colors.BLUE_GREY_400


def build_homepage_view(page=None):
    is_dark = False
    if page is not None:
        try:
            is_dark = bool(page.client_storage.get("sb_night_mode"))
            page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        except Exception:
            pass
    width = getattr(page, "width", None) or 1400
    narrow = width < NARROW_WIDTH

    # The login page's and admin workspace's colours (frontend/theme.py).
    navy = theme.NAVY if not is_dark else theme.NIGHT_INK
    label_blue = theme.PRIMARY if not is_dark else "#8cb8f0"
    ink = theme.INK if not is_dark else theme.NIGHT_INK
    muted = theme.MUTED if not is_dark else theme.NIGHT_MUTED
    line = theme.BORDER if not is_dark else theme.NIGHT_BORDER
    surface = "#ffffff" if not is_dark else theme.NIGHT_SURFACE
    canvas = theme.CANVAS if not is_dark else theme.NIGHT_CANVAS
    soft_shadow = ft.BoxShadow(blur_radius=18, offset=ft.Offset(0, 6), color=ft.Colors.with_opacity(0.08 if not is_dark else 0.3, "#0c4279"))
    hero_photo = "sb_tolosa_homepage.jpg"

    def visual_link(label, color=ink, on_click=None, active=False):
        button = ft.TextButton(
            text=label,
            on_click=on_click,
            style=ft.ButtonStyle(color=color, padding=ft.Padding(12, 8, 12, 8)),
        )
        return ft.Column(
            [button, ft.Container(width=22, height=3, border_radius=2, bgcolor=label_blue if active else None)],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        )

    def eyebrow(text, color=label_blue):
        return ft.Text(text, size=11, color=color, weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=1.5))

    def scroll_to(key):
        return lambda _: content_scroll.scroll_to(key=key, duration=400)

    def open_login(_):
        if page is not None:
            admin_main(page)

    def open_public_documents(_=None, search=""):
        if page is not None:
            try:
                from frontend.frontend_public.public_portal import build_public_portal
                page.clean()
                page.add(build_public_portal(page, search=search))
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
        icon_color=navy,
        tooltip=("Switch to light mode" if is_dark else "Switch to night mode"),
        on_click=toggle_night_mode,
    )

    navigation = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(content=theme.brand(on_blue=is_dark), col={"xs": 12, "lg": 3}),
                ft.Container(
                    content=ft.Row(
                        [
                            visual_link("Home", navy, on_click=lambda _: content_scroll.scroll_to(offset=0, duration=400), active=True),
                            visual_link("About", on_click=scroll_to("about-section")),
                            visual_link("Public Records", on_click=lambda _: open_public_documents()),
                            visual_link("Announcements", on_click=scroll_to("announcements-section")),
                            visual_link("Contact", on_click=scroll_to("contact-section")),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                        wrap=True,
                    ),
                    col={"xs": 12, "lg": 6},
                    # On a phone the hero's buttons reach the same places.
                    visible=not narrow,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            night_mode_button,
                            ft.TextButton("Login", on_click=open_login, style=ft.ButtonStyle(color=label_blue, padding=ft.Padding(12, 8, 12, 8))),
                            theme.primary_button("Public Documents", on_click=open_public_documents, icon=ft.Icons.DESCRIPTION_OUTLINED, height=42),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        wrap=True,
                    ),
                    col={"xs": 12, "lg": 3},
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=surface,
        padding=ft.Padding(40, 10, 40, 10),
        shadow=ft.BoxShadow(blur_radius=12, color=ft.Colors.with_opacity(0.08, "#0c4279"), offset=ft.Offset(0, 3)),
    )

    def stat_card(icon, value, label):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(icon, color=label_blue, size=24),
                        width=48, height=48, border_radius=24,
                        alignment=ft.Alignment(0, 0),
                        bgcolor=ft.Colors.with_opacity(0.12, theme.PRIMARY),
                    ),
                    ft.Column(
                        [
                            ft.Text(f"{int(value or 0):,}", size=22, weight=ft.FontWeight.BOLD, color=navy),
                            ft.Text(label, size=12, color=muted),
                        ],
                        spacing=0,
                        tight=True,
                    ),
                ],
                spacing=14,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(16, 14, 22, 14),
            bgcolor=ft.Colors.with_opacity(0.96, surface),
            border_radius=14,
            shadow=soft_shadow,
        )

    stats = load_homepage_stats()
    stat_row = ft.Row(
        [
            stat_card(ft.Icons.DESCRIPTION_OUTLINED, stats.get("public_documents"), "Public Documents"),
            stat_card(ft.Icons.EVENT_AVAILABLE_OUTLINED, stats.get("sessions_held_this_year"), f"Sessions Held in {stats.get('year') or 'this year'}"),
        ],
        spacing=14,
        run_spacing=14,
        wrap=True,
    ) if stats else None

    hero_text = ft.Column(
        [
            eyebrow("REPUBLIC OF THE PHILIPPINES  •  PROVINCE OF LEYTE  •  MUNICIPALITY OF TOLOSA"),
            ft.Column(
                [
                    ft.Text("Welcome to the", size=40, color=navy, weight=ft.FontWeight.BOLD),
                    ft.Text("Sangguniang Bayan of Tolosa", size=40, color=label_blue, weight=ft.FontWeight.BOLD),
                ],
                spacing=0,
            ),
            ft.Container(
                ft.Text(
                    "Your one-stop platform for accessing legislative documents, public records, and important updates "
                    "from the Municipal Government of Tolosa, Leyte.",
                    size=16,
                    color=muted,
                ),
                width=560,
            ),
            ft.Row(
                [
                    theme.primary_button("Explore Public Documents", on_click=open_public_documents, icon=ft.Icons.ARROW_FORWARD, height=50),
                    ft.OutlinedButton(
                        "Learn More About Us",
                        icon=ft.Icons.INFO_OUTLINE,
                        on_click=scroll_to("about-section"),
                        height=50,
                        style=ft.ButtonStyle(
                            color=label_blue,
                            bgcolor=surface,
                            side=ft.BorderSide(1, line),
                            shape=ft.RoundedRectangleBorder(radius=13),
                            padding=ft.Padding(22, 0, 22, 0),
                        ),
                    ),
                ],
                spacing=14,
                wrap=True,
            ),
            *([ft.Container(stat_row, padding=ft.Padding(0, 18, 0, 0))] if stat_row else []),
        ],
        spacing=20,
    )

    hero_background = ft.LinearGradient(
        begin=ft.Alignment(-1, -1),
        end=ft.Alignment(1, 1),
        colors=["#F8FBFF", "#E4EEFB"] if not is_dark else [theme.NIGHT_CANVAS, theme.NIGHT_BLUE],
    )
    hero_layers = []
    if not narrow:
        photo_width = int(width * 0.6)
        hero_layers += [
            ft.Container(
                content=ft.Image(src=hero_photo, fit=ft.ImageFit.COVER, error_content=ft.Container()),
                right=0, top=0, bottom=0, width=photo_width,
            ),
            # Fades the photo into the hero's background, so the heading sits on a plain colour.
            ft.Container(
                gradient=ft.LinearGradient(
                    begin=ft.Alignment(-1, 0),
                    end=ft.Alignment(1, 0),
                    colors=[canvas, ft.Colors.with_opacity(0.7, canvas), ft.Colors.with_opacity(0.0, canvas)],
                    stops=[0.0, 0.3, 0.65],
                ),
                right=0, top=0, bottom=0, width=photo_width,
            ),
        ]
    # The text is the one unpositioned layer, so it sets the hero's height and the photo fills in behind it.
    hero_layers.append(ft.Container(hero_text, width=width, padding=ft.Padding(24, 32, 24, 32) if narrow else ft.Padding(56, 52, 56, 48)))
    hero = ft.Container(content=ft.Stack(hero_layers), gradient=hero_background)

    def announcement_row(item):
        icon, color = announcement_style(item.get("category"))
        lines = [
            ft.Text((item.get("category") or "").upper(), size=10, color=label_blue, weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=1)),
            ft.Text(item.get("title") or "", size=14, color=ink, weight=ft.FontWeight.BOLD),
        ]
        if item.get("details"):
            lines.append(ft.Text(item["details"], size=12, color=muted))
        if item.get("date"):
            lines.append(ft.Text(item["date"], size=12, color=muted))
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(icon, color=color, size=22),
                        width=44, height=44, border_radius=22,
                        alignment=ft.Alignment(0, 0),
                        bgcolor=ft.Colors.with_opacity(0.14, color),
                    ),
                    ft.Column(lines, spacing=3, expand=True),
                ],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(16, 14, 14, 14),
            bgcolor=surface,
            border=ft.border.all(1, line),
            border_radius=14,
            shadow=soft_shadow,
        )

    announcement_items = load_homepage_announcements()
    announcement_rows = [announcement_row(item) for item in announcement_items] or [
        ft.Container(
            ft.Text("There are no announcements right now.", size=14, color=muted),
            padding=20,
            bgcolor=surface,
            border=ft.border.all(1, line),
            border_radius=14,
        )
    ]

    announcements = ft.Column(
        [
            eyebrow("LATEST UPDATES"),
            ft.Text("Announcements", size=24, weight=ft.FontWeight.BOLD, color=navy),
            ft.Container(height=4),
            ft.Column(announcement_rows, spacing=10),
        ],
        spacing=8,
        key="announcements-section",
    )

    information = ft.Container(
        content=announcements,
        bgcolor=canvas,
        padding=ft.Padding(56, 44, 56, 48),
    )

    def about_point(icon, title, description):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(icon, color=label_blue, size=22),
                        width=44, height=44, border_radius=12,
                        alignment=ft.Alignment(0, 0),
                        bgcolor=ft.Colors.with_opacity(0.12, theme.PRIMARY),
                    ),
                    ft.Column(
                        [
                            ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=ink),
                            ft.Text(description, size=13, color=muted),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                ],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            col={"xs": 12, "md": 4},
        )

    about = ft.Container(
        content=ft.Column(
            [
                eyebrow("ABOUT THE SYSTEM"),
                ft.Text("A clearer way to follow local legislation", size=24, weight=ft.FontWeight.BOLD, color=navy),
                ft.Text(
                    "The Legislative Document Tracking Management System brings the records of the Sangguniang Bayan of Tolosa "
                    "into one organized digital space.",
                    size=14,
                    color=muted,
                ),
                ft.Container(height=8),
                ft.ResponsiveRow(
                    [
                        about_point(ft.Icons.SEARCH, "Find records", "Look up ordinances, resolutions and other public documents by title, number or year."),
                        about_point(ft.Icons.TIMELINE, "Follow their progress", "See each measure's stage as it moves through the Sangguniang Bayan."),
                        about_point(ft.Icons.VERIFIED_OUTLINED, "Transparent public service", "Accessible legislative information supports informed participation."),
                    ],
                    spacing=28,
                    run_spacing=20,
                ),
            ],
            spacing=8,
        ),
        bgcolor=surface,
        border=ft.Border(top=ft.BorderSide(1, line), bottom=ft.BorderSide(1, line)),
        padding=ft.Padding(56, 40, 56, 44),
        key="about-section",
    )

    def footer_link(label, on_click):
        return ft.TextButton(label, on_click=on_click, style=ft.ButtonStyle(color=theme.ON_BLUE, padding=ft.Padding(6, 4, 6, 4)))

    footer = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            theme.brand(subtitle="Municipality of Tolosa", on_blue=True, seal_size=40),
                            ft.Text("Legislative Document Tracking Management System", size=12, color=theme.ON_BLUE_MUTED),
                        ],
                        spacing=10,
                    ),
                    col={"xs": 12, "md": 4},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [ft.Icon(ft.Icons.PLACE_OUTLINED, size=16, color=theme.ACCENT), ft.Text("Municipal Hall, Tolosa, Leyte", size=13, color=theme.ON_BLUE, weight=ft.FontWeight.W_600)],
                                spacing=6,
                            ),
                            ft.Text("For public information and legislative concerns, visit the Municipal Hall.", size=12, color=theme.ON_BLUE_MUTED),
                        ],
                        spacing=6,
                    ),
                    col={"xs": 12, "md": 4},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    footer_link("Home", lambda _: content_scroll.scroll_to(offset=0, duration=400)),
                                    footer_link("About", scroll_to("about-section")),
                                    footer_link("Public Documents", lambda _: open_public_documents()),
                                    footer_link("Announcements", scroll_to("announcements-section")),
                                ],
                                spacing=0,
                                wrap=True,
                                alignment=ft.MainAxisAlignment.END,
                            ),
                            ft.Text("© Municipality of Tolosa. All rights reserved.", size=11, color=theme.ON_BLUE_MUTED, text_align=ft.TextAlign.RIGHT),
                        ],
                        spacing=6,
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                    ),
                    col={"xs": 12, "md": 4},
                ),
            ],
            spacing=28,
            run_spacing=20,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        gradient=theme.blue_band_gradient(),
        padding=ft.Padding(56, 28, 56, 28),
        key="contact-section",
    )

    content_scroll = ft.Column(
        [hero, information, about, footer],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    return ft.Column(
        [navigation, content_scroll],
        spacing=0,
        expand=True,
    )
