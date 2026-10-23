import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from .. import models
from ..core import LGU_TIMEZONE, lgu_today
from ..database import get_db
from .measure_stages import stage_summary


def _as_lgu(value):
    """A stored time in LGU local time; naive values are UTC (SQLite)."""
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(LGU_TIMEZONE)


router = APIRouter(prefix="/public/documents", tags=["public"])
# Public figures that are not about one document, such as the homepage counts.
stats_router = APIRouter(prefix="/public", tags=["public"])


def _tracking_value(value: str | None) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r"(?i)(?:doc[-\s]*)?0*([0-9]+)", value.strip())
    return f"DOC-{int(match.group(1))}" if match else None


@router.get("")
def list_public_documents(
    search: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    year: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(models.Document).filter(
        models.Document.archived.is_(False),
        models.Document.is_public.is_(True),
    )

    if search and search.strip():
        tracking_value = _tracking_value(search)
        like = f"%{search.strip().lower()}%"
        search_conditions = [
            models.Document.tracking_number.ilike(like),
            models.Document.document_number.ilike(like),
            cast(models.Document.series_year, String).ilike(like),
            models.Document.title.ilike(like),
            models.Document.description.ilike(like),
            models.Document.document_type.ilike(like),
            models.Document.category.ilike(like),
            models.Document.current_office.ilike(like),
            models.Document.status.ilike(like),
            models.Document.remarks.ilike(like),
            models.Document.author.ilike(like),
            models.Document.session.ilike(like),
        ]
        if tracking_value:
            tracking_number = int(tracking_value.removeprefix("DOC-"))
            search_conditions.extend([
                models.Document.tracking_number == tracking_value,
                models.Document.tracking_number == f"DOC-{tracking_number:06d}",
            ])
        query = query.filter(or_(*search_conditions))
    if document_type and document_type != "All Types":
        query = query.filter(models.Document.document_type == document_type)
    if year and year != "All Years" and year.isdigit() and len(year) == 4:
        query = query.filter(
            or_(
                models.Document.series_year == int(year),
                models.Document.series_year.is_(None)
                & (models.Document.created_at >= f"{year}-01-01")
                & (models.Document.created_at < f"{int(year) + 1}-01-01"),
            )
        )

    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    documents = (
        query.order_by(models.Document.created_at.desc(), models.Document.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
        {
            "id": document.id,
            "number": document.tracking_number,
            "tracking_number": document.tracking_number,
            "document_number": document.document_number,
            "series_year": document.series_year,
            "title": document.title,
            "type": document.document_type or "Document",
            "document_type": document.document_type,
            "date": document.date_registered or (_as_lgu(document.created_at).strftime("%B %d, %Y") if document.created_at else ""),
            "category": document.category,
            "description": document.description,
            "stage": stage_summary(db, document),
        }
        for document in documents
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@stats_router.get("/stats")
def public_stats(db: Session = Depends(get_db)):
    """The homepage counts. Only what the public can already see: public, unarchived documents,
    active committees, and sessions held (not drafts or scheduled ones) this year in LGU time."""
    today = lgu_today()
    month_start = datetime(today.year, today.month, 1, tzinfo=LGU_TIMEZONE)
    public_documents = db.query(models.Document).filter(
        models.Document.archived.is_(False),
        models.Document.is_public.is_(True),
    )
    return {
        "public_documents": public_documents.count(),
        "public_documents_this_month": public_documents.filter(models.Document.created_at >= month_start).count(),
        "active_committees": db.query(models.Committee).filter(models.Committee.is_active.is_(True)).count(),
        "sessions_held_this_year": db.query(models.CouncilSession).filter(
            models.CouncilSession.status == "Held",
            models.CouncilSession.held_on >= date(today.year, 1, 1),
            models.CouncilSession.held_on <= today,
        ).count(),
        "year": today.year,
    }
