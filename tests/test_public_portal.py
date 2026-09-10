from frontend.frontend_public.public_portal import build_public_portal, load_public_documents


def test_public_portal_builds_without_page():
    portal = build_public_portal(None)
    assert portal is not None
    assert hasattr(portal, "controls")


def test_public_documents_loader_returns_list():
    docs = load_public_documents()
    assert isinstance(docs, list)
