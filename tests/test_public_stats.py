from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.database import SessionLocal, engine
from Backends.backend.routes import public_documents
from tests.test_settings_pages import reset_db

models.Base.metadata.create_all(bind=engine)

TODAY = date(2026, 10, 22)


def seed():
    reset_db()
    with SessionLocal() as db:
        def document(number, created_at, is_public=True, archived=False):
            db.add(models.Document(tracking_number=f"DOC-{number}", title=f"Document {number}", is_public=is_public,
                                   archived=archived, created_at=created_at))

        document(1, datetime(2026, 10, 5, tzinfo=timezone.utc))
        document(2, datetime(2026, 3, 1, tzinfo=timezone.utc))
        document(3, datetime(2026, 10, 6, tzinfo=timezone.utc), is_public=False)
        document(4, datetime(2026, 10, 7, tzinfo=timezone.utc), archived=True)
        db.add_all([models.Committee(name="Finance"), models.Committee(name="Health"), models.Committee(name="Old", is_active=False)])
        term = models.CouncilTerm(name="13th Sangguniang Bayan", starts_on=date(2025, 7, 1), ends_on=date(2028, 6, 30))
        db.add(term)
        db.flush()
        for number, held_on, status in [(1, date(2025, 12, 1), "Held"), (2, date(2026, 2, 2), "Held"), (3, date(2026, 10, 20), "Held"),
                                        (4, date(2026, 10, 21), "Draft"), (5, date(2026, 10, 27), "Scheduled")]:
            db.add(models.CouncilSession(term_id=term.id, kind="Regular", number=number, held_on=held_on, status=status))
        db.commit()


def test_public_stats_count_only_what_the_public_can_see(monkeypatch):
    seed()
    monkeypatch.setattr(public_documents, "lgu_today", lambda: TODAY)

    response = TestClient(main.app).get("/public/stats")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "public_documents": 2,
        "public_documents_this_month": 1,
        "active_committees": 2,
        "sessions_held_this_year": 2,
        "year": 2026,
    }
