from pathlib import Path
from datetime import date
import re
import os

import requests

import flet as ft

from frontend import theme
from frontend.responsive import redraw_on_resize

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


def public_pdf_url(document_id, download=False):
    """The backend address the visitor's browser reaches (read at call time: the LAN IP is detected at startup).
    With `download`, the browser saves the file instead of opening it."""
    base = (os.getenv("PUBLIC_BASE_URL") or BACKEND_URL).strip().rstrip("/")
    return f"{base}/public/documents/{document_id}/pdf" + ("?download=1" if download else "")

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



def _display_date(value) -> str:
    """An ISO date as "Nov 06, 2026"; anything else (already formatted, or empty) as given."""
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%b %d, %Y")
    except (TypeError, ValueError):
        return str(value or "-")


def _stage_date(value) -> str:
    try:
        return date.fromisoformat(value).strftime("%b %d, %Y")
    except (TypeError, ValueError):
        return ""


def _status(document, muted="#5d6b7a") -> ft.Control:
    """A measure shows its stage and the day it got there; other documents are just public."""
    stage = (document or {}).get("stage") or {}
    since = _stage_date(stage.get("entered_on"))
    green = "#1f8a4c"
    lines = [
        ft.Container(
            ft.Text(stage.get("stage") or "Public", size=12, weight=ft.FontWeight.BOLD, color=green),
            bgcolor=ft.Colors.with_opacity(0.12, green),
            border_radius=20,
            padding=ft.Padding(10, 3, 10, 3),
        )
    ]
    if since:
        lines.append(ft.Text(f"since {since}", size=11, color=muted, no_wrap=True))
    return ft.Container(
        content=ft.Column(lines, spacing=4, tight=True),
        tooltip="\n".join(f"{item['stage']}: {_stage_date(item['date'])}" for item in stage.get("dates") or []) or None,
    )


def _reference(document) -> str:
    """ "No. 5, s. 2026", leaving out whichever part the document lacks."""
    parts = []
    if document.get("document_number"):
        parts.append(f"No. {document['document_number']}")
    if document.get("series_year"):
        parts.append(f"s. {document['series_year']}")
    return ", ".join(parts)


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

    # The homepage's colours and shapes (frontend/Frontend_Homepage/page.py), so the two pages read as one site.
    navy = theme.NAVY if not is_dark else theme.NIGHT_INK
    label_blue = theme.PRIMARY if not is_dark else "#8cb8f0"
    ink = theme.INK if not is_dark else theme.NIGHT_INK
    muted = theme.MUTED if not is_dark else theme.NIGHT_MUTED
    line = theme.BORDER if not is_dark else theme.NIGHT_BORDER
    surface = "#ffffff" if not is_dark else theme.NIGHT_SURFACE
    canvas = theme.CANVAS if not is_dark else theme.NIGHT_CANVAS
    tint = ft.Colors.with_opacity(0.06 if not is_dark else 0.16, theme.PRIMARY)
    soft_shadow = ft.BoxShadow(blur_radius=18, offset=ft.Offset(0, 6), color=ft.Colors.with_opacity(0.08 if not is_dark else 0.3, "#0c4279"))
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
                color=label_blue,
                bgcolor=surface,
                side=ft.BorderSide(1, line),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding(14, 0, 14, 0),
            ),
        )

    def view_button(document):
        """View PDF opens it straight in the browser, Download saves it; nothing to open without one."""
        if not (document.get("has_pdf") and document.get("id")):
            return ft.Text("No PDF on file", size=12, color=muted, italic=True, no_wrap=True)
        return ft.Row(
            [
                outlined_button(
                    "View PDF", ft.Icons.PICTURE_AS_PDF_OUTLINED,
                    lambda _, document_id=document["id"]: page.launch_url(public_pdf_url(document_id)) if page is not None else None,
                    height=36,
                ),
                outlined_button(
                    "Download", ft.Icons.DOWNLOAD_OUTLINED,
                    lambda _, document_id=document["id"]: page.launch_url(public_pdf_url(document_id, download=True)) if page is not None else None,
                    height=36,
                ),
            ],
            spacing=8,
            tight=True,
            alignment=ft.MainAxisAlignment.END,
        )

    def card(content, padding=0):
        return ft.Container(
            content=content,
            bgcolor=surface,
            border=ft.border.all(1, line),
            border_radius=14,
            shadow=soft_shadow,
            padding=padding,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

    def icon_badge(icon, size=40):
        return ft.Container(
            content=ft.Icon(icon, color=label_blue, size=size * 0.5),
            width=size, height=size, border_radius=size / 2,
            alignment=ft.Alignment(0, 0),
            bgcolor=ft.Colors.with_opacity(0.12, theme.PRIMARY),
        )

    def eyebrow(text):
        return ft.Text(text, size=11, color=label_blue, weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=1.5))

    # The homepage's white navigation bar, with Public Records marked as the current page.
    def visual_link(label, on_click=None, active=False):
        return ft.Column(
            [
                ft.TextButton(text=label, on_click=on_click, style=ft.ButtonStyle(color=navy if active else ink, padding=ft.Padding(12, 8, 12, 8))),
                ft.Container(width=22, height=3, border_radius=2, bgcolor=label_blue if active else None),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        )

    navigation = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(content=ft.Container(theme.brand(on_blue=is_dark), on_click=go_home), col={"xs": 12, "lg": 3}),
                ft.Container(
                    content=ft.Row(
                        [
                            visual_link("Home", go_home),
                            visual_link("About", to_section("about-section")),
                            visual_link("Public Records", active=True),
                            visual_link("Announcements", to_section("announcements-section")),
                            visual_link("Contact", to_section("contact-section")),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                        wrap=True,
                    ),
                    col={"xs": 12, "lg": 6},
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
                            ft.TextButton("Home", on_click=go_home, visible=narrow, style=ft.ButtonStyle(color=label_blue, padding=ft.Padding(12, 8, 12, 8))),
                            ft.TextButton("Login", on_click=open_login, style=ft.ButtonStyle(color=label_blue, padding=ft.Padding(12, 8, 12, 8))),
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
        padding=ft.Padding(16 if narrow else 40, 10, 16 if narrow else 40, 10),
        shadow=ft.BoxShadow(blur_radius=12, color=ft.Colors.with_opacity(0.08, "#0c4279"), offset=ft.Offset(0, 3)),
    )

    # A short version of the homepage's hero: the same gradient, eyebrow and heading styles.
    header = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.TextButton("Home", on_click=go_home, style=ft.ButtonStyle(color=label_blue, padding=ft.Padding(0, 0, 0, 0))),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=muted),
                        ft.Text("Public Documents", size=13, color=muted),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                eyebrow("PUBLIC RECORDS"),
                ft.Text("Public Documents", size=28 if narrow else 34, weight=ft.FontWeight.BOLD, color=navy),
                ft.Container(
                    ft.Text(
                        "Browse and search the ordinances, resolutions and other records the Sangguniang Bayan of Tolosa has made public.",
                        size=15,
                        color=muted,
                    ),
                    width=640,
                ),
                theme.accent_bar(),
            ],
            spacing=8,
        ),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=["#F8FBFF", "#E4EEFB"] if not is_dark else [theme.NIGHT_CANVAS, theme.NIGHT_BLUE],
        ),
        padding=ft.Padding(side, 24, side, 32),
    )

    def labelled(label, control):
        return ft.Column([ft.Text(label, size=12, weight=ft.FontWeight.W_600, color=ink), control], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    field_style = dict(border_color=line, focused_border_color=label_blue, border_radius=10, text_size=14)
    search_field = ft.TextField(
        hint_text="e.g. RES-000002, market",
        prefix_icon=ft.Icons.SEARCH,
        content_padding=ft.Padding(12, 12, 12, 12),
        bgcolor=surface,
        filled=True,
        **field_style,
    )
    # A filled Dropdown is grey on Flet 0.28.
    type_filter = ft.Dropdown(value="All Types", options=[_option("All Types"), _option("Ordinance"), _option("Resolution")], **field_style)
    year_filter = ft.Dropdown(value="All Years", options=[_option("All Years"), _option("2026"), _option("2025")], **field_style)
    search_button = theme.primary_button("Search", icon=ft.Icons.SEARCH, height=44)
    clear_button = outlined_button("Clear filters", ft.Icons.FILTER_ALT_OFF_OUTLINED, None, height=44)

    search_panel = card(
        ft.Column(
            [
                ft.Row(
                    [
                        icon_badge(ft.Icons.MANAGE_SEARCH),
                        ft.Column(
                            [
                                ft.Text("Search records", size=16, weight=ft.FontWeight.BOLD, color=navy),
                                ft.Text("Narrow the list by keyword, type or year.", size=12, color=muted),
                            ],
                            spacing=1,
                            tight=True,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(height=8, color=line),
                labelled("Keyword or number", search_field),
                labelled("Document type", type_filter),
                labelled("Series year", year_filter),
                ft.Container(height=2),
                search_button,
                clear_button,
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        padding=20,
    )

    result_count = ft.Text(size=13, color=muted)

    # Rows rather than a DataTable: a DataTable only grows as wide as its columns, so its lines
    # stopped short of the card's right edge. Every column but the title has a fixed width.
    column_widths = {"number": 150, "type": 110, "date": 120, "status": 140, "action": 250}
    min_table_width = 1030

    def table_row(number, title, kind, when, status, action, bgcolor=None, height=None, last=False):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(number, width=column_widths["number"]),
                    ft.Container(title, expand=True),
                    ft.Container(kind, width=column_widths["type"]),
                    ft.Container(when, width=column_widths["date"]),
                    ft.Container(status, width=column_widths["status"]),
                    ft.Container(action, width=column_widths["action"], alignment=ft.Alignment.CENTER_RIGHT),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=bgcolor,
            height=height,
            padding=ft.Padding(20, 14, 20, 14) if height is None else ft.Padding(20, 0, 20, 0),
            border=None if last else ft.border.only(bottom=ft.BorderSide(1, line)),
        )

    def heading(label):
        return ft.Text(label, size=11, weight=ft.FontWeight.BOLD, color=muted, style=ft.TextStyle(letter_spacing=1))

    table_header = table_row(
        heading("DOCUMENT NO."), heading("TITLE"), heading("TYPE"), heading("DATE"), heading("STATUS"), heading(""),
        bgcolor=tint, height=44,
    )
    table_rows = ft.Column(spacing=0)

    def type_chip(kind):
        return ft.Container(
            ft.Text(kind or "-", size=12, weight=ft.FontWeight.W_600, color=label_blue),
            bgcolor=ft.Colors.with_opacity(0.10, theme.PRIMARY),
            border_radius=20,
            padding=ft.Padding(10, 3, 10, 3),
        )

    def document_row(document, last):
        number_lines = [ft.Text(document.get("tracking_number") or document.get("number") or "-", size=13, weight=ft.FontWeight.BOLD, color=label_blue, no_wrap=True)]
        if _reference(document):
            number_lines.append(ft.Text(_reference(document), size=11, color=muted))
        return table_row(
            ft.Column(number_lines, spacing=2, tight=True),
            ft.Container(
                ft.Text(document.get("title") or "-", size=14, weight=ft.FontWeight.W_500, color=ink, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
                tooltip=document.get("title"),
            ),
            ft.Row([type_chip(document.get("type"))], tight=True),
            ft.Text(_display_date(document.get("date")), size=13, color=ink, no_wrap=True),
            _status(document, muted),
            view_button(document),
            last=last,
        )

    def empty_state():
        return ft.Container(
            content=ft.Column(
                [
                    icon_badge(ft.Icons.FOLDER_OPEN_OUTLINED, size=56),
                    ft.Text("No documents found", size=16, weight=ft.FontWeight.BOLD, color=navy),
                    ft.Text("Try a different keyword, or clear the filters to see every public document.", size=13, color=muted, text_align=ft.TextAlign.CENTER),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
            padding=ft.Padding(16, 48, 16, 48),
            alignment=ft.Alignment.CENTER,
        )

    page_size = 10
    current_page = 1
    page_indicator = ft.Text(size=13, color=muted)
    previous_button = outlined_button("Previous", ft.Icons.CHEVRON_LEFT, None, height=36)
    next_button = outlined_button("Next", ft.Icons.CHEVRON_RIGHT, None, height=36)
    pagination = ft.Container(
        ft.Row([previous_button, page_indicator, next_button], alignment=ft.MainAxisAlignment.CENTER, spacing=12),
        padding=14,
        border=ft.border.only(top=ft.BorderSide(1, line)),
    )

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
        table_rows.controls = [
            document_row(document, last=index == len(visible_documents) - 1)
            for index, document in enumerate(visible_documents)
        ] or [empty_state()]
        table_header.visible = bool(visible_documents)
        last_document = min(first_document + len(visible_documents) - 1, total_documents) if total_documents else 0
        result_count.value = (
            f"Showing {first_document}–{last_document} of {total_documents} document{'s' if total_documents != 1 else ''}"
            if total_documents else "No matching documents"
        )
        page_indicator.value = f"Page {current_page} of {total_pages}"
        previous_button.disabled = current_page <= 1
        next_button.disabled = current_page >= total_pages
        # One page needs no paging controls.
        pagination.visible = total_pages > 1
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

    # The results card's rough width (ResponsiveRow: 9/12 from 992px, 8/12 from 768px, full below).
    panel_share = 9 / 12 if width >= 992 else 8 / 12 if width >= 768 else 1
    panel_width = (width - 2 * side) * panel_share - 24
    table = ft.Column([table_header, table_rows], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    if panel_width >= min_table_width:
        table_area = table  # wide enough: the table fills the card
    else:
        table.width = min_table_width  # too narrow: keep the columns readable and scroll sideways
        table_area = ft.Row([table], scroll=ft.ScrollMode.AUTO)

    register = card(
        ft.Column(
            [
                ft.Container(
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    icon_badge(ft.Icons.DESCRIPTION_OUTLINED),
                                    ft.Column(
                                        [ft.Text("Documents", size=16, weight=ft.FontWeight.BOLD, color=navy), result_count],
                                        spacing=1,
                                        tight=True,
                                    ),
                                ],
                                spacing=12,
                                tight=True,
                            ),
                            ft.Row(
                                [ft.Icon(ft.Icons.SORT, size=16, color=muted), ft.Text("Newest first", size=13, color=muted)],
                                spacing=4,
                                tight=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                    ),
                    padding=ft.Padding(20, 16, 20, 16),
                    border=ft.border.only(bottom=ft.BorderSide(1, line)),
                ),
                table_area,
                pagination,
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )

    body = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(search_panel, col={"xs": 12, "md": 4, "lg": 3}),
                ft.Container(register, col={"xs": 12, "md": 8, "lg": 9}),
            ],
            spacing=24,
            run_spacing=20,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        bgcolor=canvas,
        padding=ft.Padding(side, 28, side, 48),
    )

    # The homepage's footer.
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
        padding=ft.Padding(side, 28, side, 28),
    )

    content_scroll = ft.Column(
        [header, body, footer],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    view = ft.Column(
        [navigation, content_scroll],
        spacing=0,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    redraw_on_resize(page, view, lambda: build_public_portal(page, search=search))
    return view
