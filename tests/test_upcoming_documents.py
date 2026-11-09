"""SB Members see, view and download the documents set for later days, before their day."""

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.SBmem_backend.main import app as sb_member_app
from Backends.backend import models
from Backends.backend.core import UPLOAD_DIR, get_password_hash, lgu_today
from Backends.backend.database import SessionLocal, engine
from Backends.backend.routes.temporary_documents import TEMPORARY_DIR

models.Base.metadata.create_all(bind=engine)


def setup():
    """Today: Budget. In 3 days: Tricycle (temporary) and a MOA. In 10 days: Road (day's list) and Archived. Yesterday: Old."""
    today = lgu_today()
    path = Path(UPLOAD_DIR) / "upcoming-test.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 test")
    moa = Path(TEMPORARY_DIR) / "upcoming-moa.pdf"
    moa.parent.mkdir(parents=True, exist_ok=True)
    moa.write_bytes(b"%PDF-1.4 moa")
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.add_all([
            models.User(username="member", hashed_password=get_password_hash("pw123"), role="SB Member",
                        permissions="['view_documents', 'download_documents']", status="Active", is_active=True),
            models.User(username="viewer", hashed_password=get_password_hash("pw123"), role="SB Member",
                        permissions="['view_documents']", status="Active", is_active=True),
        ])
        docs = {title: models.Document(tracking_number=f"DOC-{n}", title=title, document_type="Ordinance", qr_token=f"t{n}", archived=title == "Archived")
                for n, title in enumerate(["Budget", "Tricycle", "Road", "Archived", "Old"])}
        db.add_all(docs.values())
        db.flush()
        attachments = {title: models.Attachment(document_id=docs[title].id, original_filename=f"{title}.pdf", mime_type="application/pdf", size=13, stored_path=str(path.resolve()))
                       for title in ("Tricycle", "Old")}
        db.add_all(attachments.values())
        entry = models.TemporaryDocument(scheduled_for=today + timedelta(days=3), title="Health MOA", original_filename="moa.pdf",
                                         stored_path=str(moa.resolve()), mime_type="application/pdf", size=12)
        db.add_all([
            models.TemporaryDocument(scheduled_for=today, document_id=docs["Budget"].id),
            models.TemporaryDocument(scheduled_for=today + timedelta(days=3), document_id=docs["Tricycle"].id),
            entry,
            models.TodaysDocument(scheduled_for=today + timedelta(days=10), document_id=docs["Road"].id, position=0, note="For second reading"),
            models.TemporaryDocument(scheduled_for=today + timedelta(days=10), document_id=docs["Archived"].id),
            models.TemporaryDocument(scheduled_for=today - timedelta(days=1), document_id=docs["Old"].id),
        ])
        db.commit()
        return {title: doc.id for title, doc in docs.items()}, {title: a.id for title, a in attachments.items()}, entry.id


def headers_for(username):
    response = TestClient(main.app).post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def link(response):
    assert response.status_code == 200, response.text
    return response.json()["download_url"].split("8002", 1)[-1]


def test_members_see_each_later_day_with_its_documents_but_not_today_or_past_days():
    setup()
    response = TestClient(sb_member_app).get("/upcoming-documents", headers=headers_for("member"))

    assert response.status_code == 200, response.text
    days = response.json()["days"]
    today = lgu_today()
    assert [d["date"] for d in days] == [(today + timedelta(days=3)).isoformat(), (today + timedelta(days=10)).isoformat()]
    assert [(i["title"], i.get("kind")) for i in days[0]["items"]] == [("Tricycle", None), ("Health MOA", "MOA")]
    # The day's list and its note show too; an archived document does not.
    assert [(i["title"], i["note"]) for i in days[1]["items"]] == [("Road", "For second reading")]


def test_members_can_view_and_download_a_later_days_document_but_not_open_its_details():
    ids, attachments, _ = setup()
    client = TestClient(sb_member_app)
    member = headers_for("member")
    base = f"/documents/{ids['Tricycle']}/attachments/{attachments['Tricycle']}"

    shown = client.get(link(client.post(f"{base}/download-token?inline=true", headers=member)))
    assert shown.status_code == 200 and shown.headers["content-disposition"].startswith("inline")
    saved = client.get(link(client.post(f"{base}/download-token", headers=member)))
    assert saved.status_code == 200 and saved.headers["content-disposition"].startswith("attachment")

    assert client.get(f"/documents/{ids['Tricycle']}", headers=member).status_code == 403


def test_a_later_days_moa_opens_before_its_day():
    _, _, moa_id = setup()
    client = TestClient(sb_member_app)
    shown = client.get(link(client.post(f"/temporary-documents/{moa_id}/download-token?inline=true", headers=headers_for("viewer"))))
    assert shown.status_code == 200 and shown.headers["content-disposition"].startswith("inline")


def test_view_needs_only_view_permission_and_download_needs_download_permission():
    ids, attachments, _ = setup()
    client = TestClient(sb_member_app)
    viewer = headers_for("viewer")
    base = f"/documents/{ids['Tricycle']}/attachments/{attachments['Tricycle']}"
    assert client.post(f"{base}/download-token?inline=true", headers=viewer).status_code == 200
    assert client.post(f"{base}/download-token", headers=viewer).status_code == 403


def test_a_past_days_document_does_not_open():
    ids, attachments, _ = setup()
    client = TestClient(sb_member_app)
    response = client.post(f"/documents/{ids['Old']}/attachments/{attachments['Old']}/download-token?inline=true", headers=headers_for("member"))
    assert response.status_code == 403
