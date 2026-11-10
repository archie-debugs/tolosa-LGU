from frontend.frontend_public.public_portal import build_public_portal, document_matches_search_term, load_public_documents


def test_public_portal_builds_without_page():
    portal = build_public_portal(None)
    assert portal is not None
    assert hasattr(portal, "controls")


def test_public_documents_loader_returns_paginated_payload():
    docs = load_public_documents()
    assert isinstance(docs, dict)
    assert isinstance(docs.get("items"), list)
    assert "total_pages" in docs


def test_public_numeric_search_matches_system_id_and_legislative_metadata():
    document = {
        "tracking_number": "DOC-000506",
        "document_number": "04",
        "series_year": 1994,
    }
    assert document_matches_search_term(document, "DOC-000506")
    assert document_matches_search_term(document, "04")
    assert document_matches_search_term(document, "1994")


def test_a_long_title_shows_one_line_and_show_full_title_opens_it_whole(monkeypatch):
    import flet as ft
    import frontend.frontend_public.public_portal as portal
    from tests.test_todays_documents import _walk

    long_title = "An Ordinance Providing for the Establishment of a Public Service and Infrastructure Development Fund"
    monkeypatch.setattr(portal, "load_public_documents", lambda **kwargs: {
        "items": [{"tracking_number": "ORD-000001", "title": long_title, "type": "Ordinance", "date": "2026-08-10"},
                  {"tracking_number": "ORD-000002", "title": "Annual Budget", "type": "Ordinance", "date": "2026-08-11"}],
        "total": 2, "total_pages": 1})
    controls = list(_walk(build_public_portal(None)))
    text = next(c for c in controls if isinstance(c, ft.Container) and c.tooltip == long_title).content
    assert text.value == long_title and text.max_lines == 1 and text.overflow == ft.TextOverflow.ELLIPSIS
    toggle = next(c for c in controls if isinstance(c, ft.TextButton) and c.text == "Show full title")
    text.update = toggle.update = lambda: None  # off a page
    toggle.on_click(None)
    assert not text.max_lines and toggle.text == "Show less"  # no line limit
    toggle.on_click(None)
    assert text.max_lines == 1 and toggle.text == "Show full title"
    # A short title has no link.
    assert sum(isinstance(c, ft.TextButton) and c.text == "Show full title" for c in controls) == 1
