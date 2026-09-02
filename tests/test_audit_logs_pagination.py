import os
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend import models
from backend.core import get_password_hash
from backend.database import SessionLocal, engine
from backend.main import app


os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_audit_logs_pagination.sqlite")


models.Base.metadata.create_all(bind=engine)


def seed_data():
    db = SessionLocal()
    try:
        db.query(models.User).delete()
        db.query(models.AuditLog).delete()

        admin = models.User(
            username="adminuser",
            hashed_password=get_password_hash("adminpass"),
            role="Super Administrator",
            permissions="['*']",
            status="Active",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        now = datetime.utcnow()
        for idx in range(5):
            created = now - timedelta(days=idx)
            db.add(
                models.AuditLog(
                    actor="alice" if idx % 2 == 0 else "bob",
                    action="DOCUMENT_CREATE" if idx % 2 == 0 else "DOCUMENT_UPDATE",
                    target_type="Documents" if idx % 2 == 0 else "Archives",
                    target_id=f"DOC-{100 + idx}",
                    details=f"Document {idx} processed for audit logs.",
                    created_at=created,
                )
            )
        db.commit()
    finally:
        db.close()


def test_audit_logs_support_pagination_and_summary_data():
    seed_data()
    client = TestClient(app)

    login = client.post("/auth/login", data={"username": "adminuser", "password": "adminpass"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    response = client.get(
        "/audit/logs",
        headers={"Authorization": f"Bearer {token}"},
        params={"page": 1, "limit": 2, "search": "DOC", "date_range": "all_time"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["page"] == 1
    assert payload["limit"] == 2
    assert payload["total"] >= 3
    assert payload["pages"] >= 1
    assert len(payload["items"]) <= 2
    assert "summary" in payload
    assert "filters" in payload
    assert "items" in payload
