"""Today's Documents: employees set the documents SB Members need on a given day.

SB Members read the list through the SB Member service (Backends/SBmem_backend).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .. import models
from ..authentication import get_current_user
from ..core import lgu_today, record_audit_log, require_permission
from ..database import get_db

router = APIRouter(prefix="/todays-documents", tags=["todays-documents"])


class TodaysDocumentCreate(BaseModel):
    scheduled_for: date
    document_id: int = Field(..., gt=0)
    note: str | None = Field(default=None, max_length=500)
    # Where to insert it, e.g. to undo a removal; the end of the list when omitted.
    position: int | None = Field(default=None, ge=0)


class TodaysDocumentNote(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class TodaysDocumentOrder(BaseModel):
    scheduled_for: date
    entry_ids: list[int]


def serialize_entry(entry: models.TodaysDocument, db: Session) -> dict:
    doc = entry.document
    added_by = entry.added_by
    has_attachment = db.query(models.Attachment.id).filter(models.Attachment.document_id == doc.id).first() is not None
    return {
        "id": entry.id,
        "scheduled_for": entry.scheduled_for.isoformat(),
        "position": entry.position,
        "note": entry.note,
        "added_by": (added_by.full_name or added_by.username) if added_by else None,
        "document": {
            "id": doc.id,
            "tracking_number": doc.tracking_number,
            "document_number": doc.document_number,
            "series_year": doc.series_year,
            "title": doc.title,
            "document_type": doc.document_type,
            "status": doc.status,
            "archived": bool(doc.archived),
            "has_attachment": has_attachment,
        },
    }


def entries_for(db: Session, scheduled_for: date):
    return (
        db.query(models.TodaysDocument)
        .filter(models.TodaysDocument.scheduled_for == scheduled_for)
        .order_by(models.TodaysDocument.position.asc(), models.TodaysDocument.id.asc())
        .all()
    )


@router.get("")
def list_todays_documents(
    scheduled_for: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_permission(current_user, "set_documents_for_sb_members")
    day = scheduled_for or lgu_today()
    return {"date": day.isoformat(), "today": lgu_today().isoformat(), "items": [serialize_entry(entry, db) for entry in entries_for(db, day)]}


@router.get("/upcoming")
def upcoming_todays_documents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Today and later dates that have a list, with how many entries members cannot see (archived)."""
    require_permission(current_user, "set_documents_for_sb_members")
    rows = (
        db.query(
            models.TodaysDocument.scheduled_for,
            func.count(models.TodaysDocument.id),
            func.sum(case((models.Document.archived.is_(True), 1), else_=0)),
        )
        .join(models.Document, models.Document.id == models.TodaysDocument.document_id)
        .filter(models.TodaysDocument.scheduled_for >= lgu_today())
        .group_by(models.TodaysDocument.scheduled_for)
        .order_by(models.TodaysDocument.scheduled_for.asc())
        .limit(30)
        .all()
    )
    return {"items": [{"date": day.isoformat(), "count": count, "hidden": int(hidden or 0)} for day, count, hidden in rows]}


@router.post("")
def add_todays_document(
    payload: TodaysDocumentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_permission(current_user, "set_documents_for_sb_members")
    if payload.scheduled_for < lgu_today():
        raise HTTPException(status_code=400, detail="Documents can only be set for today or a later date")
    doc = db.query(models.Document).filter(models.Document.id == payload.document_id).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.archived:
        raise HTTPException(status_code=400, detail="Archived documents cannot be set for SB Members")
    existing = db.query(models.TodaysDocument.id).filter(
        models.TodaysDocument.scheduled_for == payload.scheduled_for,
        models.TodaysDocument.document_id == payload.document_id,
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="This document is already set for that date")

    siblings = entries_for(db, payload.scheduled_for)
    position = len(siblings) if payload.position is None else min(payload.position, len(siblings))
    for index, sibling in enumerate(siblings):
        sibling.position = index + 1 if index >= position else index
    entry = models.TodaysDocument(
        scheduled_for=payload.scheduled_for,
        document_id=doc.id,
        position=position,
        note=(payload.note or "").strip() or None,
        added_by_id=current_user.id,
    )
    db.add(entry)
    db.flush()
    record_audit_log(
        db,
        actor=current_user.username,
        action="TODAYS_DOCUMENT_ADDED",
        target_type="Document",
        target_id=str(doc.id),
        details=f"{doc.tracking_number} set for SB Members on {payload.scheduled_for.isoformat()}",
        commit=False,
    )
    db.commit()
    db.refresh(entry)
    return serialize_entry(entry, db)


@router.patch("/{entry_id}")
def change_todays_document_note(
    entry_id: int,
    payload: TodaysDocumentNote,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_permission(current_user, "set_documents_for_sb_members")
    entry = db.query(models.TodaysDocument).filter(models.TodaysDocument.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.scheduled_for < lgu_today():
        raise HTTPException(status_code=400, detail="Notes can only be changed for today or a later date")
    entry.note = (payload.note or "").strip() or None
    record_audit_log(
        db,
        actor=current_user.username,
        action="TODAYS_DOCUMENT_NOTE_CHANGED",
        target_type="Document",
        target_id=str(entry.document_id),
        details=f"Note for {entry.document.tracking_number} on {entry.scheduled_for.isoformat()} changed",
        commit=False,
    )
    db.commit()
    db.refresh(entry)
    return serialize_entry(entry, db)


@router.delete("/{entry_id}")
def remove_todays_document(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_permission(current_user, "set_documents_for_sb_members")
    entry = db.query(models.TodaysDocument).filter(models.TodaysDocument.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    details = f"{entry.document.tracking_number} removed from SB Members' list for {entry.scheduled_for.isoformat()}"
    document_id = entry.document_id
    db.delete(entry)
    record_audit_log(
        db,
        actor=current_user.username,
        action="TODAYS_DOCUMENT_REMOVED",
        target_type="Document",
        target_id=str(document_id),
        details=details,
        commit=False,
    )
    db.commit()
    return {"message": "Removed", "id": entry_id}


@router.put("/order")
def reorder_todays_documents(
    payload: TodaysDocumentOrder,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_permission(current_user, "set_documents_for_sb_members")
    entries = {entry.id: entry for entry in entries_for(db, payload.scheduled_for)}
    if sorted(payload.entry_ids) != sorted(entries):
        raise HTTPException(status_code=400, detail="The order must list every entry for that date exactly once")
    for position, entry_id in enumerate(payload.entry_ids):
        entries[entry_id].position = position
    db.commit()
    return {"date": payload.scheduled_for.isoformat(), "items": [serialize_entry(entry, db) for entry in entries_for(db, payload.scheduled_for)]}
