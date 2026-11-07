from datetime import date
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from Backends.backend import main, models
from Backends.backend.database import SessionLocal
from tests.test_auth_user_flows import bearer_headers, reset_db


def add_doc(db, number, document_type, title, *, stage=None, approved_on=None, registered="2026-01-05", author=None):
    doc = models.Document(tracking_number=number, title=title, document_type=document_type, stage=stage,
                          document_number=number[-2:], series_year=2026, date_registered=registered, author=author)
    db.add(doc)
    db.flush()
    if approved_on:
        db.add(models.DocumentStageChange(document_id=doc.id, stage=stage, effective_on=approved_on))


def open_list(client, headers, **options):
    link = client.post("/print-list/link", headers=headers, json=options)
    assert link.status_code == 200, link.text
    url = urlparse(link.json()["url"])
    page = client.get(f"{url.path}?{url.query}")
    assert page.status_code == 200, page.text
    return page.text


def test_print_list_groups_by_type_and_month_and_filters_a_month():
    reset_db()
    client = TestClient(main.app)
    headers = bearer_headers(client, "superuser", "pw123")
    with SessionLocal() as db:
        add_doc(db, "ORD-000001", "Ordinance", "Budget <Ordinance>", stage="Approved", approved_on=date(2026, 3, 16), author="Hon. A; Hon. B")
        add_doc(db, "ORD-000002", "Ordinance", "Pending Ordinance", stage="Second Reading")
        add_doc(db, "RES-000001", "Resolution", "Old Resolution", stage="Adopted", approved_on=date(2025, 6, 1))
        add_doc(db, "LTR-000001", "Letter Request", "Gym Request", registered="2026-02-03")
        db.commit()

    page = open_list(client, headers, year=2026)
    assert "Budget &lt;Ordinance&gt;" in page and "<Ordinance>" not in page
    assert "March 2026" in page and "March 16, 2026" in page and "Hon. A<br>Hon. B" in page
    assert "Not yet approved" in page and "Pending Ordinance" in page
    assert "Old Resolution" not in page  # adopted in 2025
    assert "Gym Request" in page and "February 3, 2026" in page

    march = open_list(client, headers, year=2026, month=3)
    assert "Budget &lt;Ordinance&gt;" in march and "March 2026" in march
    assert "Pending Ordinance" not in march and "Gym Request" not in march

    letters = open_list(client, headers, year=2026, types=["Letter Request"])
    assert "Gym Request" in letters and "Budget" not in letters


def test_print_list_link_needs_print_permission_and_a_type():
    reset_db()
    client = TestClient(main.app)
    headers = bearer_headers(client, "superuser", "pw123")
    assert client.post("/print-list/link", headers=headers, json={"year": 2026, "types": []}).status_code == 400
    assert client.get("/print-list/page", params={"download_token": "bad"}).status_code in (401, 403)
