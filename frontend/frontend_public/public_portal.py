from pathlib import Path
from datetime import date
import re
import os

import requests

import flet as ft

from frontend import theme

if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors
if not hasattr(ft, "Icons") and hasattr(ft, "icons"):
    ft.Icons = ft.icons
if hasattr(ft, "Alignment") and hasattr(ft, "alignment"):
    for name, value in {
        "CENTER": getattr(ft.alignment, "center", None),
        "CENTER_LEFT": getattr(ft.alignment, "center_left", None),
        "CENTER_RIGHT": getattr(ft.alignment, "center_right", None),
    }.items():
        if value is not None and not hasattr(ft.Alignment, name):
            setattr(ft.Alignment, name, value)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")


def public_pdf_url(document_id):
    """The backend address the visitor's browser reaches (read at call time: the LAN IP is detected at startup)."""
    base = (os.getenv("PUBLIC_BASE_URL") or BACKEND_URL).strip().rstrip("/")
    return f"{base}/public/documents/{document_id}/pdf"

DOCUMENTS = [
    {"number": "DOC-22-2026", "title": "An Ordinance Providing for the Establishment of a Public Service and Infrastructure Development Fund", "type": "Ordinance", "date": "August 10, 2026"},
    {"number": "DOC-21-2026", "title": "A Resolution Adopting the Local Development Plan", "type": "Resolution", "date": "August 05, 2026"},
    {"number": "DOC-20-2026", "title": "An Ordinance Regulating the Use of Public Markets", "type": "Ordinance", "date": "July 28, 2026"},
    {"number": "DOC-19-2026", "title": "A Resolution Congratulating the Participants of the Local Festival", "type": "Resolution", "date": "July 20, 2026"},
    {"number": "DOC-18-2026", "title": "An Ordinance on the Management of Solid Waste", "type": "Ordinance", "date": "July 15, 2026"},
]


def load_public_documents(page=1, page_size=10, search="", document_type="All Types", year="All Years"):
    try:
        params = {"page": page, "page_size": page_size}
        if search:
            params["search"] = search
        if document_type and document_type != "All Types":
            params["document_type"] = document_type
        if year and year != "All Years":
            params["year"] = year
        response = requests.get(f"{BACKEND_URL}/public/documents", params=params, timeout=5)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload
    except requests.RequestException:
        pass
    return {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "total_pages": 1,
    }


def normalize_search_text(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().split()).lower()


def normalize_tracking_identifier(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text.lstrip("0") or "0")
    digits = re.findall(r"\d+", text)
    if not digits:
        return None
    return int(digits[-1].lstrip("0") or "0")


def looks_like_tracking_search(value):
    text = normalize_search_text(value)
    return bool(text) and any(character.isdigit() for character in text)


def document_matches_search_term(document, term):
    query = normalize_search_text(term)
    if not query:
        return True
    if looks_like_tracking_search(query):
        document_tracking = normalize_tracking_identifier(
            document.get("tracking_number") or document.get("number") or document.get("id")
        )
        search_tracking = normalize_tracking_identifier(query)
        if document_tracking is not None and document_tracking == search_tracking:
            return True

    fields = [
        document.get("title"), document.get("type"), document.get("document_type"),
        document.get("status"), document.get("date"), document.get("current_office"),
        document.get("originating_office"), document.get("category"), document.get("description"),
        document.get("remarks"), document.get("author"), document.get("session"),
        document.get("tracking_number"), document.get("number"),
        document.get("document_number"), document.get("series_year"),
    ]
    return any(query in normalize_search_text(field) for field in fields if field is not None)


def apply_public_document_search(documents, search_text=""):
    query = normalize_search_text(search_text)
    if not query:
        return list(documents)
    terms = [term for term in query.split() if term]
    return [document for document in documents if all(document_matches_search_term(document, term) for term in terms)]


def _option(label):
    return ft.dropdown.Option(label)


def _badge(label: str) -> ft.Container:
    ordinance = label == "Ordinance"
    return ft.Container(
        content=ft.Text(label, size=12, weight=ft.FontWeight.W_600, color="#175685" if ordinance else "#236447"),
        bgcolor="#e3f0fa" if ordinance else "#e3f3e8",
        border_radius=6,
        padding=ft.Padding(10, 5, 10, 5),
    )


def _stage_date(value) -> str:
    try:
        return date.fromisoformat(value).strftime("%b %d, %Y")
    except (TypeError, ValueError):
        return ""


def _status(document=None) -> ft.Container:
    """A measure shows its stage and the day it got there; other documents are just public."""
    stage = (document or {}).get("stage") or {}
    label = stage.get("stage") or "Public / Active"
    since = _stage_date(stage.get("entered_on"))
    badge = ft.Container(
        content=ft.Row([ft.Container(width=7, height=7, border_radius=4, bgcolor="#2d9b61"), ft.Text(label, size=12, weight=ft.FontWeight.W_600, color="#246544")], spacing=6, tight=True),
        bgcolor="#e4f4e8",
        border_radius=6,
        padding=ft.Padding(9, 5, 9, 5),
    )
    if not since:
        return badge
    return ft.Container(
        content=ft.Column([badge, ft.Text(f"since {since}", size=10, color="#6b7b8c")], spacing=2, tight=True),
        tooltip="\n".join(f"{item['stage']}: {_stage_date(item['date'])}" for item in stage.get("dates") or []),
    )


def build_public_portal(page: ft.Page | None = None, search: str = "") -> ft.Column:
    """`search` fills the search box, for a search started on the homepage."""
    from frontend.Frontend_Homepage.page import NARROW_WIDTH

    is_dark = False
    if page is not None:
        try:
            is_dark = bool(page.client_storage.get("sb_night_mode"))
            page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        except Exception:
            pass
    width = getattr(page, "width", None) or 1400
    narrow = width < NARROW_WIDTH

    # The homepage's colours (frontend/Frontend_Homepage/page.py), so the two pages read as one site.
    navy = theme.NAVY if not is_dark else theme.NIGHT_INK
    label_blue = theme.PRIMARY if not is_dark else "#8cb8f0"
    ink = theme.INK if not is_dark else theme.NIGHT_INK
    muted = theme.MUTED if not is_dark else theme.NIGHT_MUTED
    line = theme.BORDER if not is_dark else theme.NIGHT_BORDER
    surface = "#ffffff" if not is_dark else theme.NIGHT_SURFACE
    canvas = theme.CANVAS if not is_dark else theme.NIGHT_CANVAS
    row_line = "#edf1f4" if not is_dark else theme.NIGHT_BORDER
    soft_shadow = ft.BoxShadow(blur_radius=18, offset=ft.Offset(0, 6), color=ft.Colors.with_opacity(0.08 if not is_dark else 0.3, "#0c4279"))
    hero_photo = "sb_tolosa_homepage.jpg"

    def go_home(_=None, section=None):
        """Back to the homepage, scrolled to `section` (one of its keys) when given."""
        if page is None:
            return
        from frontend.Frontend_Homepage.page import build_homepage_view

        homepage = build_homepage_view(page)
        page.clean()
        page.add(homepage)
        page.update()
        if section:
            # The homepage is its navigation bar above one scrolling column.
            homepage.controls[1].scroll_to(key=section, duration=400)

    def to_section(section):
        return lambda _: go_home(section=section)

    def open_login(_):
        if page is not None:
            from frontend.admin.app import main as admin_main

            admin_main(page)

    def toggle_night_mode(_):
        if page is None:
            return
        page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        page.bgcolor = theme.CANVAS if is_dark else theme.NIGHT_CANVAS
        try:
            page.client_storage.set("sb_night_mode", not is_dark)
        except Exception:
            pass
        page.clean()
        page.add(build_public_portal(page, search=search_field.value or ""))
        page.update()

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

    def outlined_button(label, icon, on_click, height=50):
        return ft.OutlinedButton(
            label,
            icon=icon,
            on_click=on_click,
            height=height,
            style=ft.ButtonStyle(
                color=label_blue,
                bgcolor=surface,
                side=ft.BorderSide(1, line),
                shape=ft.RoundedRectangleBorder(radius=13),
                padding=ft.Padding(22, 0, 22, 0),
            ),
        )

    def view_button(document):
        """Opens the document's PDF straight in the browser; nothing to open without one."""
        if not (document.get("has_pdf") and document.get("id")):
            return ft.Text("No PDF", size=12, color=muted)
        return outlined_button(
            "View", ft.Icons.PICTURE_AS_PDF_OUTLINED,
            lambda _, document_id=document["id"]: page.launch_url(public_pdf_url(document_id)) if page is not None else None,
            height=36,
        )

    def card(content):
        return ft.Container(
            content=content,
            bgcolor=surface,
            border=ft.border.all(1, line),
            border_radius=14,
            shadow=soft_shadow,
            padding=ft.Padding(24, 22, 24, 22),
        )

    navigation = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(content=theme.brand(subtitle="Public Document Portal", on_blue=is_dark), col={"xs": 12, "lg": 3}),
                ft.Container(
                    content=ft.Row(
                        [
                            visual_link("Home", on_click=go_home),
                            visual_link("About", on_click=to_section("about-section")),
                            visual_link("Public Records", navy, active=True),
                            visual_link("Announcements", on_click=to_section("announcements-section")),
                            visual_link("Contact", on_click=to_section("contact-section")),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                        wrap=True,
                    ),
                    col={"xs": 12, "lg": 6},
                    # On a phone the Home button reaches the homepage's sections.
                    visible=not narrow,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.IconButton(
                                icon=(ft.Icons.LIGHT_MODE if is_dark else ft.Icons.DARK_MODE),
                                icon_color=navy,
                                tooltip=("Switch to light mode" if is_dark else "Switch to night mode"),
                                on_click=toggle_night_mode,
                            ),
                            ft.TextButton("Login", on_click=open_login, style=ft.ButtonStyle(color=label_blue, padding=ft.Padding(12, 8, 12, 8))),
                            theme.primary_button("Home", on_click=go_home, icon=ft.Icons.HOME_OUTLINED, height=42),
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

    hero_text = ft.Column(
        [
            eyebrow("SANGGUNIANG BAYAN OF TOLOSA  •  PUBLIC RECORDS"),
            ft.Column(
                [
                    ft.Text("Public", size=40, color=navy, weight=ft.FontWeight.BOLD),
                    ft.Text("Document Portal", size=40, color=label_blue, weight=ft.FontWeight.BOLD),
                ],
                spacing=0,
            ),
            ft.Container(
                ft.Text(
                    "Search and view the ordinances, resolutions and other legislative documents "
                    "the Sangguniang Bayan of Tolosa has made available to the public.",
                    size=16,
                    color=muted,
                ),
                width=560,
            ),
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
    hero_layers.append(ft.Container(hero_text, width=width, padding=ft.Padding(24, 32, 24, 32) if narrow else ft.Padding(56, 48, 56, 48)))
    hero = ft.Container(content=ft.Stack(hero_layers), gradient=hero_background)

    def labelled(label, control):
        return ft.Column([ft.Text(label, size=12, color=muted), control], spacing=6)

    search_field = ft.TextField(
        hint_text="Search documents, tracking number, or title…",
        prefix_icon=ft.Icons.SEARCH,
        border_radius=14,
        border_color=line,
        focused_border_color=label_blue,
        bgcolor=surface,
        filled=True,
        content_padding=ft.Padding(16, 14, 16, 14),
    )
    type_filter = ft.Dropdown(value="All Types", options=[_option("All Types"), _option("Ordinance"), _option("Resolution")], border_color=line, border_radius=14, bgcolor=surface, filled=True)
    year_filter = ft.Dropdown(value="All Years", options=[_option("All Years"), _option("2026"), _option("2025")], border_color=line, border_radius=14, bgcolor=surface, filled=True)
    search_button = theme.primary_button("Search", icon=ft.Icons.SEARCH, height=50)
    clear_button = outlined_button("Clear Filters", ft.Icons.REFRESH, None)

    search_section = ft.Column(
        [
            eyebrow("FIND A RECORD"),
            ft.Text("Search Documents", size=24, weight=ft.FontWeight.BOLD, color=navy),
            ft.Text("Search by system ID, document number, year or title, or narrow the list by type and year.", size=14, color=muted),
            ft.Container(height=4),
            card(
                ft.ResponsiveRow(
                    [
                        ft.Container(labelled("Search", search_field), col={"xs": 12, "md": 5}),
                        ft.Container(labelled("Document Type", type_filter), col={"xs": 12, "sm": 6, "md": 2}),
                        ft.Container(labelled("Year", year_filter), col={"xs": 12, "sm": 6, "md": 2}),
                        ft.Container(
                            ft.Row([search_button, clear_button], spacing=10, wrap=True),
                            col={"xs": 12, "md": 3},
                            padding=ft.Padding(0, 24, 0, 0),
                        ),
                    ],
                    spacing=14,
                    run_spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ),
        ],
        spacing=8,
    )

    result_count = ft.Text(size=12, color=muted)
    data_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text(label, size=13, weight=ft.FontWeight.W_700, color=ink)) for label in ("System ID / Document No.", "Title", "Type", "Date", "Status", "Action")],
        column_spacing=24, horizontal_margin=12, heading_row_height=48, data_row_min_height=64,
        border=ft.border.all(1, line),
        vertical_lines=ft.border.BorderSide(1, row_line),
        horizontal_lines=ft.border.BorderSide(1, row_line),
    )
    page_size = 10
    current_page = 1
    page_indicator = ft.Text(size=12, color=navy)
    previous_button = ft.TextButton("Previous", icon=ft.Icons.CHEVRON_LEFT, style=ft.ButtonStyle(color=label_blue))
    next_button = ft.TextButton("Next", icon=ft.Icons.CHEVRON_RIGHT, style=ft.ButtonStyle(color=label_blue))

    def render_documents(_, reset_page=False):
        nonlocal current_page
        if reset_page:
            current_page = 1
        payload = load_public_documents(
            page=current_page,
            page_size=page_size,
            search=search_field.value or "",
            document_type=type_filter.value or "All Types",
            year=year_filter.value or "All Years",
        )
        visible_documents = payload.get("items", [])
        total_documents = payload.get("total", len(visible_documents))
        total_pages = max(1, payload.get("total_pages", 1))
        current_page = min(current_page, total_pages)
        first_document = ((current_page - 1) * page_size + 1) if total_documents else 0
        data_table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Column(
                    [
                        ft.Text(document.get("tracking_number") or document.get("number") or "-", size=13, weight=ft.FontWeight.W_700, color=navy),
                        ft.Text(
                            f"No. {document.get('document_number') or '-'} / Series {document.get('series_year') or '-'}",
                            size=10,
                            color=muted,
                        ),
                    ],
                    spacing=2,
                )),
                ft.DataCell(
                    ft.Tooltip(
                        message=document["title"],
                        content=ft.Container(
                            content=ft.Text(
                                document["title"],
                                size=13,
                                color=ink,
                                max_lines=1,
                                no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            width=340,
                        ),
                    )
                ),
                ft.DataCell(_badge(document["type"])), ft.DataCell(ft.Text(document["date"], size=13, color=muted)),
                ft.DataCell(_status(document)), ft.DataCell(view_button(document)),
            ]) for document in visible_documents
        ]
        last_document = min(first_document + len(visible_documents) - 1, total_documents) if total_documents else 0
        result_count.value = f"Showing {first_document}-{last_document} of {total_documents} documents"
        page_indicator.value = f"Page {current_page} of {total_pages}"
        previous_button.disabled = current_page <= 1
        next_button.disabled = current_page >= total_pages
        if page is not None:
            page.update()

    def go_to_previous_page(_=None):
        nonlocal current_page
        current_page = max(1, current_page - 1)
        render_documents(None)

    def go_to_next_page(_=None):
        nonlocal current_page
        current_page += 1
        render_documents(None)

    def clear_filters(_=None):
        search_field.value = ""
        type_filter.value = "All Types"
        year_filter.value = "All Years"
        render_documents(None, reset_page=True)

    previous_button.on_click = go_to_previous_page
    next_button.on_click = go_to_next_page
    search_field.on_change = lambda event: render_documents(event, reset_page=True)
    type_filter.on_change = lambda event: render_documents(event, reset_page=True)
    year_filter.on_change = lambda event: render_documents(event, reset_page=True)
    search_button.on_click = lambda event: render_documents(event, reset_page=True)
    clear_button.on_click = clear_filters
    search_field.value = search
    render_documents(None, reset_page=True)

    documents_section = ft.Column(
        [
            eyebrow("PUBLIC RECORDS"),
            ft.Row(
                [ft.Text("Available Public Documents", size=24, weight=ft.FontWeight.BOLD, color=navy), result_count],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            ft.Container(height=4),
            card(
                ft.Column(
                    [
                        ft.Row([ft.Container(content=data_table, width=1180)], scroll=ft.ScrollMode.AUTO),
                        ft.Row([previous_button, page_indicator, next_button], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                    ],
                    spacing=16,
                ),
            ),
        ],
        spacing=8,
    )

    information = ft.Container(
        content=ft.Column([search_section, documents_section], spacing=40),
        bgcolor=canvas,
        padding=ft.Padding(24, 32, 24, 40) if narrow else ft.Padding(56, 44, 56, 48),
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
                                    footer_link("Home", go_home),
                                    footer_link("About", to_section("about-section")),
                                    footer_link("Public Documents", lambda _: content_scroll.scroll_to(offset=0, duration=400)),
                                    footer_link("Announcements", to_section("announcements-section")),
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
    )

    content_scroll = ft.Column(
        [hero, information, footer],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    return ft.Column(
        [navigation, content_scroll],
        spacing=0,
        expand=True,
    )
