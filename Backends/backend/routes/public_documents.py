import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db


router = APIRouter(prefix="/public/documents", tags=["public"])


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
    db: Session = Depends(get_db),
):
    query = db.query(models.Document).filter(models.Document.archived.is_(False))

    if search and search.strip():
        tracking_value = _tracking_value(search)
        if tracking_value:
            query = query.filter(models.Document.tracking_number == tracking_value)
        else:
            terms = [term for term in search.lower().split() if term]
            for term in terms:
                like = f"%{term}%"
                query = query.filter(
                    or_(
                        models.Document.tracking_number.ilike(like),
                        models.Document.title.ilike(like),
                        models.Document.description.ilike(like),
                        models.Document.document_type.ilike(like),
                        models.Document.category.ilike(like),
                        models.Document.originating_office.ilike(like),
                        models.Document.current_office.ilike(like),
                        models.Document.status.ilike(like),
                        models.Document.remarks.ilike(like),
                        models.Document.author.ilike(like),
                        models.Document.session.ilike(like),
                    )
                )
    if document_type and document_type != "All Types":
        query = query.filter(models.Document.document_type == document_type)
    if year and year != "All Years" and year.isdigit() and len(year) == 4:
        query = query.filter(models.Document.created_at >= f"{year}-01-01", models.Document.created_at < f"{int(year) + 1}-01-01")

    documents = query.order_by(models.Document.created_at.desc(), models.Document.id.desc()).all()
    return [
        {
            "id": document.id,
            "number": document.tracking_number,
            "tracking_number": document.tracking_number,
            "title": document.title,
            "type": document.document_type or "Document",
            "document_type": document.document_type,
            "date": document.date_registered or (document.created_at.strftime("%B %d, %Y") if document.created_at else ""),
            "status": document.status,
            "category": document.category,
            "description": document.description,
            "author": document.author,
            "session": document.session,
            "current_office": document.current_office,
            "originating_office": document.originating_office,
        }
        for document in documents
    ]