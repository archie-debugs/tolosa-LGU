"""
Backfill script: migrate `documents.routing_history` JSON into `document_history` rows.

Run with:
    .venv\Scripts\python.exe scripts\migrate_routing_history.py

This script expects the updated models to be present and the DB to have the
`document_history` table (created via migrations). It is idempotent for entries
that already exist with identical timestamps.
"""
import json
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend import models


def migrate():
    db: Session = SessionLocal()
    try:
        docs = db.query(models.Document).all()
        created = 0
        for d in docs:
            raw = d.routing_history or "[]"
            try:
                items = json.loads(raw)
            except Exception:
                items = []

            for item in items:
                # simple dedupe: check if a matching history row exists
                q = db.query(models.DocumentHistory).filter(
                    models.DocumentHistory.document_id == d.id,
                    models.DocumentHistory.action == item.get("action"),
                    models.DocumentHistory.actor == item.get("actor"),
                    models.DocumentHistory.created_at == item.get("created_at"),
                )
                if q.first():
                    continue

                row = models.DocumentHistory(
                    document_id=d.id,
                    action=item.get("action") or item.get("type") or "ROUTE",
                    actor=item.get("actor") or item.get("by"),
                    from_office=item.get("from"),
                    to_office=item.get("to"),
                    notes=item.get("notes") or item.get("remark"),
                    created_at=item.get("created_at"),
                )
                db.add(row)
                created += 1

        if created:
            db.commit()
        print(f"Migration complete. Created {created} history rows.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
