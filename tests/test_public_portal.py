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
