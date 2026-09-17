from pathlib import Path
import re
import os

import requests

import flet as ft


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
BUILDING_IMAGE = "sb_tolosa_homepage.jpg"
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")

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
    total = len(DOCUMENTS)
    return {
        "items": list(DOCUMENTS[(page - 1) * page_size:page * page_size]),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
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
        return document_tracking is not None and document_tracking == search_tracking

    fields = [
        document.get("title"), document.get("type"), document.get("document_type"),
        document.get("status"), document.get("date"), document.get("current_office"),
        document.get("originating_office"), document.get("category"), document.get("description"),
        document.get("remarks"), document.get("author"), document.get("session"),
        document.get("tracking_number"), document.get("number"),
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


def _brand() -> ft.Row:
    return ft.Row(
        [
            ft.Container(
                content=ft.Text("SB", size=18, weight=ft.FontWeight.W_800, color="#092f55"),
                width=42,
                height=42,
                border_radius=21,
                bgcolor="#f2eee4",
                border=ft.border.all(2, "#d5b55d"),
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(
                [
                    ft.Text("SANGGUNIAN BAYAN", size=11, weight=ft.FontWeight.W_700, color="#dce9f4"),
                    ft.Text("OF TOLOSA", size=21, weight=ft.FontWeight.W_800, color="#ffffff"),
                ],
                spacing=0,
            ),
        ],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _badge(label: str) -> ft.Container:
    ordinance = label == "Ordinance"
    return ft.Container(
        content=ft.Text(label, size=12, weight=ft.FontWeight.W_600, color="#175685" if ordinance else "#236447"),
        bgcolor="#e3f0fa" if ordinance else "#e3f3e8",
        border_radius=6,
        padding=ft.Padding(10, 5, 10, 5),
    )


def _status() -> ft.Container:
    return ft.Container(
        content=ft.Row([ft.Container(width=7, height=7, border_radius=4, bgcolor="#2d9b61"), ft.Text("Public / Active", size=12, weight=ft.FontWeight.W_600, color="#246544")], spacing=6, tight=True),
        bgcolor="#e4f4e8",
        border_radius=6,
        padding=ft.Padding(9, 5, 9, 5),
    )


def _button(label: str, icon=None, outlined: bool = False):
    button_style = ft.ButtonStyle(
        color="#24435d" if outlined else "#ffffff",
        bgcolor=None if outlined else "#103f6d",
        side=ft.BorderSide(1, "#c5d0d8") if outlined else None,
        padding=ft.Padding(18, 12, 18, 12),
        shape=ft.RoundedRectangleBorder(radius=7),
    )
    if outlined:
        return ft.OutlinedButton(label, icon=icon, style=button_style)
    return ft.ElevatedButton(label, icon=icon, style=button_style)


def build_public_portal(page: ft.Page | None = None) -> ft.Column:
    navy = "#103f6d"
    ink = "#18344e"
    muted = "#647887"
    gold = "#d5ad50"
    border = "#dce5ea"

    def go_home(_=None):
        if page is None:
            return
        from frontend.Frontend_Homepage.page import build_homepage_view

        page.clean()
        page.add(build_homepage_view(page))
        page.update()

    header = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(content=_brand(), col={"xs": 12, "md": 5}),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.TextButton("Home", on_click=go_home, style=ft.ButtonStyle(color="#ffffff")),
                            ft.Column([ft.TextButton("Public Documents", style=ft.ButtonStyle(color="#ffffff")), ft.Container(height=3, width=118, bgcolor=gold)], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.TextButton("About", style=ft.ButtonStyle(color="#ffffff")),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                    ),
                    col={"xs": 12, "md": 7},
                ),
            ],
            run_spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=navy,
        padding=ft.Padding(32, 16, 32, 16),
    )

    hero = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("SANGGUNIAN BAYAN OF TOLOSA", size=12, weight=ft.FontWeight.W_700, color=navy),
                            ft.Text("Public Document Portal", size=38, weight=ft.FontWeight.W_800, color=ink),
                            ft.Container(width=68, height=4, bgcolor=gold),
                            ft.Text("Search and view legislative documents made available to the public by the Sangguniang Bayan of Tolosa.", size=16, color=muted, max_lines=3),
                        ],
                        spacing=14,
                    ),
                    col={"xs": 12, "md": 6},
                    padding=ft.Padding(8, 12, 24, 12),
                ),
                ft.Container(content=ft.Image(src=BUILDING_IMAGE, fit=ft.ImageFit.COVER), height=220, border_radius=10, clip_behavior=ft.ClipBehavior.HARD_EDGE, col={"xs": 12, "md": 6}),
            ],
            spacing=26,
            run_spacing=18,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(34, 30, 34, 28),
    )

    search_card = ft.Container(
        content=ft.Column(
            [
                ft.Text("Search Documents", size=20, weight=ft.FontWeight.W_700, color=ink),
                ft.ResponsiveRow(
                    [
                        ft.Container(content=ft.Column([ft.Text("Search by document number or title", size=12, color=muted), ft.TextField(hint_text="Enter search terms...", prefix_icon=ft.Icons.SEARCH, border_color="#c9d5dd", bgcolor="#ffffff")], spacing=6), col={"xs": 12, "md": 5}),
                        ft.Container(content=ft.Column([ft.Text("Document Type", size=12, color=muted), ft.Dropdown(value="All Types", options=[_option("All Types"), _option("Ordinance"), _option("Resolution")], border_color="#c9d5dd", bgcolor="#ffffff")], spacing=6), col={"xs": 12, "sm": 6, "md": 2}),
                        ft.Container(content=ft.Column([ft.Text("Year", size=12, color=muted), ft.Dropdown(value="All Years", options=[_option("All Years"), _option("2026"), _option("2025")], border_color="#c9d5dd", bgcolor="#ffffff")], spacing=6), col={"xs": 12, "sm": 6, "md": 2}),
                        ft.Container(content=ft.Row([_button("Search", ft.Icons.SEARCH), _button("Clear Filters", ft.Icons.REFRESH, outlined=True)], spacing=8, wrap=True), col={"xs": 12, "md": 3}, padding=ft.Padding(0, 24, 0, 0)),
                    ],
                    spacing=14,
                    run_spacing=10,
                ),
            ],
            spacing=14,
        ),
        bgcolor="#ffffff",
        border=ft.border.all(1, border),
        border_radius=10,
        padding=ft.Padding(22, 18, 22, 20),
    )

    search_field = search_card.content.controls[1].controls[0].content.controls[1]
    type_filter = search_card.content.controls[1].controls[1].content.controls[1]
    year_filter = search_card.content.controls[1].controls[2].content.controls[1]

    result_count = ft.Text(size=12, color=muted)
    data_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text(label, size=13, weight=ft.FontWeight.W_700, color=ink)) for label in ("Document No.", "Title", "Type", "Date", "Status", "Action")],
        column_spacing=24, horizontal_margin=12, heading_row_height=48, data_row_min_height=64,
        border=ft.border.all(1, border), vertical_lines=ft.border.BorderSide(1, "#edf1f4"),
        horizontal_lines=ft.border.BorderSide(1, "#edf1f4"),
    )
    page_size = 10
    current_page = 1
    page_indicator = ft.Text(size=12, color=navy)
    previous_button = ft.TextButton("Previous", style=ft.ButtonStyle(color=navy))
    next_button = ft.TextButton("Next", style=ft.ButtonStyle(color=navy))

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
                ft.DataCell(ft.Text(document["number"], size=13, weight=ft.FontWeight.W_700, color=navy)),
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
                ft.DataCell(_status()), ft.DataCell(_button("View", ft.Icons.VISIBILITY_OUTLINED, outlined=True)),
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

    previous_button.on_click = go_to_previous_page
    next_button.on_click = go_to_next_page
    search_field.on_change = lambda event: render_documents(event, reset_page=True)
    type_filter.on_change = lambda event: render_documents(event, reset_page=True)
    year_filter.on_change = lambda event: render_documents(event, reset_page=True)
    search_card.content.controls[1].controls[3].content.controls[0].on_click = lambda event: render_documents(event, reset_page=True)

    def clear_filters(_=None):
        search_field.value = ""
        type_filter.value = "All Types"
        year_filter.value = "All Years"
        render_documents(None, reset_page=True)

    search_card.content.controls[1].controls[3].content.controls[1].on_click = clear_filters
    render_documents(None, reset_page=True)

    table_card = ft.Container(
        content=ft.Column(
            [
                ft.Row([ft.Text("Available Public Documents", size=21, weight=ft.FontWeight.W_700, color=ink), ft.Container(expand=True), result_count], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([ft.Container(content=data_table, width=1180)], scroll=ft.ScrollMode.AUTO),
                ft.Row([previous_button, page_indicator, next_button], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            ],
            spacing=16,
        ),
        bgcolor="#ffffff",
        border=ft.border.all(1, border),
        border_radius=10,
        padding=ft.Padding(22, 18, 22, 16),
    )

    footer = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(content=_brand(), col={"xs": 12, "md": 5}),
                ft.Container(content=ft.Column([ft.Text("Official Public Portal", size=14, weight=ft.FontWeight.W_700, color="#ffffff"), ft.Text("Sangguniang Bayan of Tolosa", size=13, color="#d6e4ef"), ft.Text("Tolosa, Leyte, Philippines", size=13, color="#d6e4ef")], spacing=4), col={"xs": 12, "md": 4}),
                ft.Container(content=ft.Text("© 2026", size=13, color="#d6e4ef"), col={"xs": 12, "md": 3}),
            ],
            spacing=18,
            run_spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor="#092f55",
        padding=ft.Padding(32, 24, 32, 24),
    )

    return ft.Column(
        [
            header,
            ft.Container(
                content=ft.Column([hero, search_card, table_card], spacing=20),
                bgcolor="#f1f5f7",
                padding=ft.Padding(24, 20, 24, 30),
            ),
            footer,
        ],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
