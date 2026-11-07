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


FOOTER_TEXT = "#c9d3dd"


def _stage_date(value) -> str:
    try:
        return date.fromisoformat(value).strftime("%b %d, %Y")
    except (TypeError, ValueError):
        return ""


def _status(document, muted="#5d6b7a") -> ft.Control:
    """A measure shows its stage and the day it got there; other documents are just public."""
    stage = (document or {}).get("stage") or {}
    since = _stage_date(stage.get("entered_on"))
    lines = [ft.Text(stage.get("stage") or "Public", size=13, weight=ft.FontWeight.BOLD, color="#1f6b3a")]
    if since:
        lines.append(ft.Text(f"since {since}", size=12, color=muted, no_wrap=True))
    return ft.Container(
        content=ft.Column(lines, spacing=1, tight=True),
        tooltip="\n".join(f"{item['stage']}: {_stage_date(item['date'])}" for item in stage.get("dates") or []) or None,
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
    header_row = "#e9eef4" if not is_dark else theme.NIGHT_BLUE
    stripe = "#fafbfc" if not is_dark else None
    side = 16 if narrow else 56

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

    def outlined_button(label, icon, on_click, height=40):
        return ft.OutlinedButton(
            label,
            icon=icon,
            on_click=on_click,
            height=height,
            style=ft.ButtonStyle(
                color=navy,
                bgcolor=surface,
                side=ft.BorderSide(1, navy),
                shape=ft.RoundedRectangleBorder(radius=2),
                padding=ft.Padding(14, 0, 14, 0),
            ),
        )

    def view_button(document):
        """Opens the document's PDF straight in the browser; nothing to open without one."""
        if not (document.get("has_pdf") and document.get("id")):
            return ft.Text("No PDF on file", size=12, color=muted, italic=True, no_wrap=True)
        return outlined_button(
            "View PDF", None,
            lambda _, document_id=document["id"]: page.launch_url(public_pdf_url(document_id)) if page is not None else None,
            height=34,
        )

    def footer_link(label, on_click):
        # A plain clickable text: a TextButton centres short labels in its minimum width.
        return ft.Container(ft.Text(label, size=13, color=FOOTER_TEXT), on_click=on_click, padding=ft.Padding(0, 3, 0, 3))

    def gov_link(label, url):
        return footer_link(label, lambda _: page.launch_url(url) if page is not None else None)

    # The GOVPH-style strip over every government site.
    gov_bar = ft.Container(
        content=ft.Row(
            [ft.Text("GOVPH", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE, style=ft.TextStyle(letter_spacing=1))]
            + [ft.Text(label, size=12, color="#dddddd") for label in ("Republic of the Philippines", "Province of Leyte", "Municipality of Tolosa")],
            spacing=18,
            wrap=True,
        ),
        bgcolor="#1b1b1b",
        padding=ft.Padding(side, 6, side, 6),
    )

    masthead = ft.Container(
        content=ft.Row(
            [
                theme.seal(60 if narrow else 78),
                ft.Column(
                    [
                        ft.Text("REPUBLIC OF THE PHILIPPINES  ·  PROVINCE OF LEYTE", size=11, color=muted, style=ft.TextStyle(letter_spacing=2)),
                        ft.Text("Sangguniang Bayan of Tolosa", size=22 if narrow else 28, weight=ft.FontWeight.BOLD, color=navy),
                        ft.Text("Office of the Municipal Legislative Council", size=14, color=muted),
                    ],
                    spacing=2,
                    tight=True,
                    expand=True,
                ),
            ],
            spacing=18,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=surface,
        padding=ft.Padding(side, 18, side, 18),
        border=ft.border.only(bottom=ft.BorderSide(4, theme.ACCENT)),
    )

    def nav_item(label, on_click=None, active=False, visible=True):
        return ft.Container(
            content=ft.Text(label.upper(), size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE, style=ft.TextStyle(letter_spacing=0.5)),
            padding=ft.Padding(18, 13, 18, 13),
            bgcolor=theme.PRIMARY if active else None,
            border=ft.border.only(bottom=ft.BorderSide(3, theme.ACCENT)) if active else None,
            on_click=on_click,
            ink=True,
            visible=visible,
        )

    navigation = ft.Container(
        content=ft.Row(
            [
                ft.Row(
                    [
                        nav_item("Home", go_home),
                        # On a phone, Home reaches the homepage's other sections.
                        nav_item("About", to_section("about-section"), visible=not narrow),
                        nav_item("Public Documents", active=True),
                        nav_item("Announcements", to_section("announcements-section"), visible=not narrow),
                        nav_item("Contact", to_section("contact-section"), visible=not narrow),
                    ],
                    spacing=0,
                    wrap=True,
                    expand=True,
                ),
                ft.IconButton(
                    icon=(ft.Icons.LIGHT_MODE if is_dark else ft.Icons.DARK_MODE),
                    icon_color=ft.Colors.WHITE,
                    tooltip=("Switch to light mode" if is_dark else "Switch to night mode"),
                    on_click=toggle_night_mode,
                ),
                nav_item("Login", open_login),
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=theme.NAVY if not is_dark else theme.NIGHT_BLUE,
        padding=ft.Padding(max(side - 18, 0), 0, max(side - 18, 0), 0),
    )

    def labelled(label, control):
        return ft.Column([ft.Text(label.upper(), size=12, weight=ft.FontWeight.BOLD, color=muted), control], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    field_style = dict(border_color="#9aa7b5" if not is_dark else line, border_radius=2, bgcolor=surface, filled=True)
    search_field = ft.TextField(hint_text="e.g. ORD-000007, market", content_padding=ft.Padding(10, 10, 10, 10), focused_border_color=navy, **field_style)
    dropdown_style = dict(field_style, filled=False)  # a filled Dropdown is grey on Flet 0.28
    type_filter = ft.Dropdown(value="All Types", options=[_option("All Types"), _option("Ordinance"), _option("Resolution")], **dropdown_style)
    year_filter = ft.Dropdown(value="All Years", options=[_option("All Years"), _option("2026"), _option("2025")], **dropdown_style)
    search_button = ft.FilledButton(
        "Search", height=40,
        style=ft.ButtonStyle(bgcolor=theme.NAVY, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=2)),
    )
    clear_button = outlined_button("Clear filters", None, None)

    def boxed(title, content):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        ft.Text(title.upper(), size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE, style=ft.TextStyle(letter_spacing=0.5)),
                        bgcolor=theme.NAVY if not is_dark else theme.NIGHT_BLUE,
                        padding=ft.Padding(14, 10, 14, 10),
                    ),
                    ft.Container(content, padding=14),
                ],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            bgcolor=surface,
            border=ft.border.all(1, line),
        )

    search_panel = boxed(
        "Search records",
        ft.Column(
            [labelled("Keyword or number", search_field), labelled("Document type", type_filter), labelled("Series year", year_filter), search_button, clear_button],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )

    result_count = ft.Text(size=13, color=muted)
    data_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text(label, size=12, weight=ft.FontWeight.BOLD, color=ink, style=ft.TextStyle(letter_spacing=0.4)))
            for label in ("DOCUMENT NO.", "TITLE", "TYPE", "DATE", "STATUS", "")
        ],
        column_spacing=20, horizontal_margin=12, heading_row_height=46, data_row_min_height=64, data_row_max_height=96,
        heading_row_color=header_row,
        border=ft.border.only(top=ft.BorderSide(1, line)),
        horizontal_lines=ft.border.BorderSide(1, line),
    )
    page_size = 10
    current_page = 1
    page_indicator = ft.Text(size=13, color=navy)
    previous_button = outlined_button("‹ Previous", None, None, height=34)
    next_button = outlined_button("Next ›", None, None, height=34)

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
            ft.DataRow(
                color=stripe if index % 2 else None,
                cells=[
                    ft.DataCell(ft.Column(
                        [
                            ft.Text(document.get("tracking_number") or document.get("number") or "-", size=13, weight=ft.FontWeight.BOLD, color=navy, no_wrap=True),
                            ft.Text(f"No. {document.get('document_number') or '-'}, s. {document.get('series_year') or '-'}", size=11, color=muted),
                        ],
                        spacing=2,
                        tight=True,
                    )),
                    ft.DataCell(ft.Container(
                        ft.Text(document["title"], size=14, color=ink, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
                        width=330,
                        tooltip=document["title"],
                    )),
                    ft.DataCell(ft.Text(document["type"], size=14, color=ink)),
                    ft.DataCell(ft.Text(document["date"], size=14, color=ink, no_wrap=True)),
                    ft.DataCell(_status(document, muted)),
                    ft.DataCell(view_button(document)),
                ],
            )
            for index, document in enumerate(visible_documents)
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

    register = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    ft.Row([result_count, ft.Text("Newest first", size=13, color=muted)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.Padding(14, 10, 14, 10),
                ),
                ft.Row([ft.Container(content=data_table, width=900)], scroll=ft.ScrollMode.AUTO),
                ft.Container(
                    ft.Row([previous_button, page_indicator, next_button], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                    padding=12,
                ),
            ],
            spacing=0,
        ),
        bgcolor=surface,
        border=ft.border.all(1, line),
    )

    breadcrumb = ft.Row(
        [
            ft.TextButton("Home", on_click=go_home, style=ft.ButtonStyle(color=label_blue, padding=ft.Padding(0, 0, 0, 0))),
            ft.Text("›  Public Documents", size=13, color=muted),
        ],
        spacing=4,
    )

    body = ft.Container(
        content=ft.Column(
            [
                breadcrumb,
                ft.Container(
                    ft.Text("Public Documents", size=26, weight=ft.FontWeight.BOLD, color=navy),
                    border=ft.border.only(bottom=ft.BorderSide(2, navy)),
                    padding=ft.Padding(0, 0, 0, 8),
                ),
                ft.Container(height=8),
                ft.ResponsiveRow(
                    [
                        ft.Container(search_panel, col={"xs": 12, "md": 4, "lg": 3}),
                        ft.Container(register, col={"xs": 12, "md": 8, "lg": 9}),
                    ],
                    spacing=24,
                    run_spacing=20,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=6,
        ),
        bgcolor=canvas,
        padding=ft.Padding(side, 12, side, 40),
    )

    def footer_heading(text):
        return ft.Text(text.upper(), size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE, style=ft.TextStyle(letter_spacing=1))

    footer = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    ft.Row(
                        [
                            theme.seal(52),
                            ft.Column(
                                [
                                    footer_heading("Sangguniang Bayan of Tolosa"),
                                    ft.Text("Municipal Hall, Tolosa, Leyte", size=13, color=FOOTER_TEXT),
                                    ft.Text("Legislative Document Tracking Management System", size=13, color=FOOTER_TEXT),
                                    ft.Container(height=6),
                                    ft.Text("All content is in the public domain unless otherwise stated.", size=12, color=FOOTER_TEXT),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    col={"xs": 12, "md": 6},
                ),
                ft.Container(
                    ft.Column(
                        [
                            footer_heading("About GOVPH"),
                            gov_link("The Republic of the Philippines", "https://www.gov.ph"),
                            gov_link("Open Data Portal", "https://data.gov.ph"),
                            gov_link("Official Gazette", "https://www.officialgazette.gov.ph"),
                        ],
                        spacing=2,
                    ),
                    col={"xs": 12, "sm": 6, "md": 3},
                ),
                ft.Container(
                    ft.Column(
                        [
                            footer_heading("This site"),
                            footer_link("Home", go_home),
                            footer_link("Public Documents", lambda _: content_scroll.scroll_to(offset=0, duration=400)),
                            footer_link("Announcements", to_section("announcements-section")),
                            footer_link("Contact", to_section("contact-section")),
                        ],
                        spacing=2,
                    ),
                    col={"xs": 12, "sm": 6, "md": 3},
                ),
            ],
            spacing=24,
            run_spacing=20,
        ),
        bgcolor="#1b2733",
        padding=ft.Padding(side, 28, side, 28),
    )

    content_scroll = ft.Column(
        [masthead, navigation, body, footer],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    return ft.Column(
        [gov_bar, content_scroll],
        spacing=0,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
