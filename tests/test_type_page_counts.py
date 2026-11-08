from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.database import SessionLocal
from tests.test_settings_pages import add_user, headers_for, reset_db

# (type, status, category, public, archived)
DOCUMENTS = [
    ("Resolution", "Pending", "Finance", True, False),
    ("Resolution", "Approved", "Finance", False, False),
    ("Letter Request", "Received", "Roads", False, False),
    ("Letter Request", "Received", "Roads", False, True),
]


def listing(client, headers, **params):
    response = client.get("/documents", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_each_type_page_counts_only_its_own_documents():
    reset_db()
    add_user("admin", "Super Administrator", ["*"])
    with SessionLocal() as db:
        for n, (kind, status, category, public, archived) in enumerate(DOCUMENTS, start=1):
            db.add(models.Document(tracking_number=f"T-{n}", title=f"Doc {n}", document_type=kind, status=status,
                                   category=category, is_public=public, archived=archived))
        db.commit()
    client = TestClient(main.app)
    headers = headers_for(client, "admin")

    ordinances = listing(client, headers, page_type="Ordinance")
    assert ordinances["total"] == 0 and ordinances["summary"]["total"] == 0 and ordinances["summary"]["public"] == 0
    assert ordinances["available_statuses"] == [] and ordinances["available_categories"] == []

    resolutions = listing(client, headers, page_type="Resolution")
    assert resolutions["summary"] == {"total": 2, "in_transit": 0, "public": 1, "without_attachment": 2}
    assert resolutions["available_statuses"] == ["Approved", "Pending"] and resolutions["available_categories"] == ["Finance"]

    letters = listing(client, headers, page_type="Letter Request")
    assert letters["summary"]["total"] == 1 and letters["available_statuses"] == ["Received"]
    archived_letters = listing(client, headers, page_type="Letter Request", archived="true")
    assert archived_letters["summary"]["total"] == 1 and archived_letters["total"] == 1
    assert listing(client, headers, page_type="Resolution", archived="true")["summary"]["total"] == 0

    # The main Documents page still counts everything, even with its Type filter set.
    everything = listing(client, headers, document_type="Resolution")
    assert everything["summary"]["total"] == 3 and everything["total"] == 2
