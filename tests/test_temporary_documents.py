import os
from datetime import timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.SBmem_backend.main import app as sb_member_app
from Backends.backend import models
from Backends.backend.core import lgu_today
from Backends.backend.database import SessionLocal
from tests.test_todays_documents import headers_for, reset_db


def prepare():
    """reset_db's documents, typed: two ordinances, a resolution, and an archived document."""
    ids = reset_db()
    with SessionLocal() as db:
        for title, document_type in (("Budget ordinance", "Ordinance"), ("Market ordinance", "Ordinance"), ("Road resolution", "Resolution")):
            db.get(models.Document, ids[title]).document_type = document_type
        db.commit()
    return ids, TestClient(main.app), headers_for("secretariat")


def local(url):
    parsed = urlparse(url)
    return f"{parsed.path}?{parsed.query}"


def upload_moa(client, headers, day=None, name="MOA_health.pdf", title="MOA with the Health Office"):
    created = client.post("/documents/uploads/create_tmp_uploads", json={"files": [{"filename": name, "size": 9}]}, headers=headers)
    assert created.status_code == 200, created.text
    file = created.json()["files"][0]
    assert client.put(local(file["upload_url"]), content=b"%PDF-1.4\n").status_code == 200
    return client.post("/temporary-documents/moa", json={"scheduled_for": (day or lgu_today()).isoformat(), "tmp_name": file["tmp_name"], "title": title}, headers=headers)


def add_past(day, **fields):
    with SessionLocal() as db:
        entry = models.TemporaryDocument(scheduled_for=day, **fields)
        db.add(entry)
        db.commit()
        return entry.id


def test_only_ordinances_can_be_added_once_per_day_and_not_to_a_past_day():
    ids, client, employee = prepare()
    today = lgu_today().isoformat()
    added = client.post("/temporary-documents/ordinance", json={"scheduled_for": today, "document_id": ids["Budget ordinance"]}, headers=employee)
    assert added.status_code == 200, added.text
    assert added.json()["kind"] == "Ordinance" and added.json()["archived"] is False
    again = client.post("/temporary-documents/ordinance", json={"scheduled_for": today, "document_id": ids["Budget ordinance"]}, headers=employee)
    assert again.status_code == 409
    resolution = client.post("/temporary-documents/ordinance", json={"scheduled_for": today, "document_id": ids["Road resolution"]}, headers=employee)
    assert resolution.status_code == 400
    yesterday = (lgu_today() - timedelta(days=1)).isoformat()
    assert client.post("/temporary-documents/ordinance", json={"scheduled_for": yesterday, "document_id": ids["Market ordinance"]}, headers=employee).status_code == 400
    assert client.get("/temporary-documents", headers=headers_for("clerk")).status_code == 403


def test_an_uploaded_moa_is_stored_listed_downloadable_and_its_file_removed_with_it():
    _, client, employee = prepare()
    moa = upload_moa(client, employee)  # secretariat has set_documents_for_sb_members but not register_documents
    assert moa.status_code == 200, moa.text
    entry = moa.json()
    assert entry["kind"] == "MOA" and entry["filename"] == "MOA_health.pdf"
    listed = client.get("/temporary-documents", headers=employee).json()["items"]
    assert [item["title"] for item in listed] == ["MOA with the Health Office"]

    link = client.post(f"/temporary-documents/{entry['id']}/download-token", headers=employee).json()["download_url"]
    assert client.get(local(link)).content == b"%PDF-1.4\n"

    with SessionLocal() as db:
        stored = db.get(models.TemporaryDocument, entry["id"]).stored_path
    assert os.path.isfile(stored)
    assert client.delete(f"/temporary-documents/{entry['id']}", headers=employee).status_code == 200
    assert not os.path.exists(stored)


def test_past_entries_are_archived_due_30_days_later_and_can_be_kept_longer():
    ids, client, employee = prepare()
    today = lgu_today()
    old = add_past(today - timedelta(days=40), document_id=ids["Budget ordinance"])
    recent = add_past(today - timedelta(days=2), title="Road MOA", original_filename="road.pdf")
    archive = client.get("/temporary-documents/archive", headers=employee).json()["items"]
    assert [item["id"] for item in archive] == [old, recent]
    assert archive[0]["due_on"] == (today - timedelta(days=9)).isoformat() and archive[0]["days_left"] == -9
    assert archive[1]["days_left"] == 29

    kept = client.post(f"/temporary-documents/{old}/keep", headers=employee).json()
    assert kept["due_on"] == (today + timedelta(days=30)).isoformat()
    assert client.post(f"/temporary-documents/{recent}/keep", headers=employee).json()["due_on"] == (today + timedelta(days=59)).isoformat()
    assert client.delete(f"/temporary-documents/{old}", headers=employee).status_code == 200
    with SessionLocal() as db:
        assert db.get(models.Document, ids["Budget ordinance"]).archived is False  # the ordinance itself stays


def test_due_archived_entries_are_flagged_in_notifications():
    ids, client, employee = prepare()
    today = lgu_today()
    due = add_past(today - timedelta(days=31), document_id=ids["Budget ordinance"])
    soon = add_past(today - timedelta(days=26), title="Soon MOA", original_filename="soon.pdf")
    add_past(today - timedelta(days=2), title="Fresh MOA", original_filename="fresh.pdf")
    items = {item["id"]: item for item in client.get("/notifications", headers=employee).json()["items"]}
    assert items[f"temporary_due:{due}"]["priority"] is True
    assert items[f"temporary_soon:{soon}"]["title"] == "Soon MOA"
    assert len([key for key in items if key.startswith("temporary_")]) == 2


def test_members_see_todays_temporary_documents_in_todays_list_and_download_the_moa_on_or_before_its_day():
    ids, client, employee = prepare()
    today = lgu_today().isoformat()
    client.post("/temporary-documents/ordinance", json={"scheduled_for": today, "document_id": ids["Market ordinance"]}, headers=employee)
    moa = upload_moa(client, employee).json()
    later = upload_moa(client, employee, day=lgu_today() + timedelta(days=1), title="Tomorrow MOA").json()

    member_client = TestClient(sb_member_app)
    member = headers_for("member")
    items = member_client.get("/todays-documents", headers=member).json()["items"]
    assert [item["title"] for item in items] == ["Market ordinance", "MOA with the Health Office"]
    assert items[1]["kind"] == "MOA" and items[1]["temporary_id"] == moa["id"]

    with SessionLocal() as db:
        db.get(models.User, db.query(models.User.id).filter_by(username="member").scalar()).permissions = "['view_documents', 'download_documents']"
        db.commit()
    link = member_client.post(f"/temporary-documents/{moa['id']}/download-token", headers=member)
    assert link.status_code == 200, link.text
    assert member_client.get(local(link.json()["download_url"])).content == b"%PDF-1.4\n"
    # A later day's MOA opens ahead of its day (Upcoming Documents); once its day has passed it is archived and does not.
    assert member_client.post(f"/temporary-documents/{later['id']}/download-token", headers=member).status_code == 200
    with SessionLocal() as db:
        db.query(models.TemporaryDocument).filter_by(id=later["id"]).update({"scheduled_for": lgu_today() - timedelta(days=1)})
        db.commit()
    assert member_client.post(f"/temporary-documents/{later['id']}/download-token", headers=member).status_code == 404


def stage(client, headers, name, content):
    created = client.post("/documents/uploads/create_tmp_uploads", json={"files": [{"filename": name, "size": len(content)}]}, headers=headers)
    file = created.json()["files"][0]
    assert client.put(local(file["upload_url"]), content=content).status_code == 200
    return file["tmp_name"]


def test_photos_of_an_moa_s_pages_are_stored_as_one_pdf():
    from tests.test_register_images import photo

    _, client, employee = prepare()
    first, second = (stage(client, employee, f"MOA roads {n}.jpg", photo()) for n in (1, 2))
    moa = client.post("/temporary-documents/moa", json={
        "scheduled_for": lgu_today().isoformat(), "tmp_name": first, "page_tmp_names": [second], "title": "MOA on roads",
    }, headers=employee)
    assert moa.status_code == 200, moa.text
    assert moa.json()["filename"] == "MOA roads 1.pdf"
    with SessionLocal() as db:
        entry = db.get(models.TemporaryDocument, moa.json()["id"])
        assert entry.mime_type == "application/pdf" and entry.stored_path.endswith(".pdf")
        with open(entry.stored_path, "rb") as handle:
            assert handle.read().count(b"/Type /Page\n") == 2

    word = stage(client, employee, "MOA.docx", b"word file")
    page = stage(client, employee, "page.jpg", photo())
    mixed = client.post("/temporary-documents/moa", json={
        "scheduled_for": lgu_today().isoformat(), "tmp_name": word, "page_tmp_names": [page], "title": "Mixed",
    }, headers=employee)
    assert mixed.status_code == 400 and "Only photos or scans" in mixed.json()["detail"]
