"""SB Members see, view and download the documents on upcoming sessions' order of business."""

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.SBmem_backend.main import app as sb_member_app
from Backends.backend import models
from Backends.backend.core import UPLOAD_DIR, get_password_hash, lgu_today
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


def setup():
    """Sessions: Scheduled in 3 days, Scheduled in 10 days, a Draft, a Held one in the past."""
    today = lgu_today()
    path = Path(UPLOAD_DIR) / "upcoming-test.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 test")
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.add_all([
            models.User(username="member", hashed_password=get_password_hash("pw123"), role="SB Member",
                        permissions="['view_documents', 'download_documents']", status="Active", is_active=True),
            models.User(username="viewer", hashed_password=get_password_hash("pw123"), role="SB Member",
                        permissions="['view_documents']", status="Active", is_active=True),
        ])
        term = models.CouncilTerm(name="13th Sangguniang Bayan", starts_on=date(2025, 7, 1), ends_on=date(2028, 6, 30))
        db.add(term)
        db.flush()
        docs = {title: models.Document(tracking_number=f"DOC-{n}", title=title, document_type="Ordinance", status="Approved", priority="Medium", qr_token=f"t{n}", archived=title == "Archived")
                for n, title in enumerate(["Tricycle ordinance", "Road resolution", "Draft only", "Held only", "Archived"])}
        db.add_all(docs.values())
        db.flush()
        attachment = models.Attachment(document_id=docs["Tricycle ordinance"].id, original_filename="tricycle.pdf", mime_type="application/pdf", size=13, stored_path=str(path.resolve()))
        db.add(attachment)
        sessions = [models.CouncilSession(term_id=term.id, kind="Regular", number=n, held_on=today + timedelta(days=days), status=status)
                    for n, (days, status) in enumerate([(10, "Scheduled"), (3, "Scheduled"), (5, "Draft"), (-4, "Held")], start=1)]
        db.add_all(sessions)
        db.flush()
        later, sooner, draft, held = sessions
        db.add_all([
            models.SessionItem(session_id=sooner.id, section="other", position=0, title="Road resolution", document_id=docs["Road resolution"].id),
            models.SessionItem(session_id=sooner.id, section="first_reading", position=1, title="Tricycle ordinance", document_id=docs["Tricycle ordinance"].id),
            models.SessionItem(session_id=sooner.id, section="other", position=2, title="Privilege speech"),
            models.SessionItem(session_id=later.id, section="unfinished", position=0, title="Archived", document_id=docs["Archived"].id),
            models.SessionItem(session_id=draft.id, section="other", position=0, title="Draft only", document_id=docs["Draft only"].id),
            models.SessionItem(session_id=held.id, section="other", position=0, title="Held only", document_id=docs["Held only"].id),
        ])
        db.commit()
        return {title: doc.id for title, doc in docs.items()}, attachment.id


def headers_for(username):
    response = TestClient(main.app).post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_members_see_scheduled_sessions_from_today_with_their_order_of_business():
    setup()
    response = TestClient(sb_member_app).get("/upcoming-documents", headers=headers_for("member"))

    assert response.status_code == 200, response.text
    sessions = response.json()["sessions"]
    assert [s["title"] for s in sessions] == ["2nd Regular Session", "1st Regular Session"]
    sooner = sessions[0]["sections"]
    assert [(sec["label"], [(i["title"], bool(i["document"])) for i in sec["items"]]) for sec in sooner] == [
        ("First reading and referral", [("Tricycle ordinance", True)]),
        ("Other matters and communications", [("Road resolution", True), ("Privilege speech", False)]),
    ]
    assert sooner[0]["items"][0]["document"]["attachments"][0]["filename"] == "tricycle.pdf"
    # An archived document stays on the agenda by title, without its file.
    assert sessions[1]["sections"][0]["items"] == [{"title": "Archived", "document": None}]


def test_members_can_view_and_download_an_upcoming_document_but_not_open_its_details():
    ids, attachment_id = setup()
    client = TestClient(sb_member_app)
    member = headers_for("member")
    base = f"/documents/{ids['Tricycle ordinance']}/attachments/{attachment_id}"

    view = client.post(f"{base}/download-token?inline=true", headers=member)
    assert view.status_code == 200, view.text
    shown = client.get(view.json()["download_url"].split("8002", 1)[-1])
    assert shown.status_code == 200 and shown.headers["content-disposition"].startswith("inline")

    download = client.post(f"{base}/download-token", headers=member).json()["download_url"]
    saved = client.get(download.split("8002", 1)[-1])
    assert saved.status_code == 200 and saved.headers["content-disposition"].startswith("attachment")

    assert client.get(f"/documents/{ids['Tricycle ordinance']}", headers=member).status_code == 403


def test_view_needs_only_view_permission_and_download_needs_download_permission():
    ids, attachment_id = setup()
    client = TestClient(sb_member_app)
    viewer = headers_for("viewer")
    base = f"/documents/{ids['Tricycle ordinance']}/attachments/{attachment_id}"
    assert client.post(f"{base}/download-token?inline=true", headers=viewer).status_code == 200
    assert client.post(f"{base}/download-token", headers=viewer).status_code == 403


def test_draft_and_held_sessions_do_not_open_files():
    ids, _ = setup()
    client = TestClient(sb_member_app)
    member = headers_for("member")
    for title in ("Draft only", "Held only"):
        with SessionLocal() as db:
            db.add(models.Attachment(document_id=ids[title], original_filename="x.pdf", mime_type="application/pdf", size=1, stored_path=str(Path(UPLOAD_DIR).resolve() / "upcoming-test.pdf")))
            db.commit()
            attachment_id = db.query(models.Attachment).filter_by(document_id=ids[title]).one().id
        assert client.post(f"/documents/{ids[title]}/attachments/{attachment_id}/download-token?inline=true", headers=member).status_code == 403
