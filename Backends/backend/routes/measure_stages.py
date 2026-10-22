"""A measure's stage: reading it, changing it, correcting it, and setting it at registration.

The rules for which moves are allowed live in Backends/backend/stages.py; this module records
them. Every change is a new DocumentStageChange row and an audit log entry (docs/adr/0003).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models, stages
from ..authentication import get_current_user
from ..core import lgu_today, record_audit_log, require_permission
from ..database import get_db

router = APIRouter(prefix="/documents", tags=["measure-stages"])

CHANGE = "change_measure_stage"


class StageChange(BaseModel):
    stage: str
    effective_on: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    committee_id: int | None = None
    document_number: str | None = Field(default=None, max_length=40)
    series_year: int | None = None


class StageCorrection(BaseModel):
    stage: str
    effective_on: date | None = None
    reason: str = Field(..., min_length=1, max_length=2000)
    committee_id: int | None = None
    document_number: str | None = Field(default=None, max_length=40)
    series_year: int | None = None


def registration_stage(document_type: str | None, requested: str | None, number: str | None, number_was_typed: bool):
    """(stage, number) for a document being registered; stage is None for documents that aren't measures.

    With no stage requested (bulk import), a measure with a number is taken to be enacted already.
    A number is only kept once the measure is enacted; one guessed from the title is dropped before that.
    """
    kind = stages.measure_kind(document_type)
    if kind is None:
        return None, number
    requested = (requested or "").strip() or None
    if requested is None:
        stage = stages.ENACTED[kind] if number else stages.FILED
    elif requested not in stages.registration_stages(kind):
        raise HTTPException(status_code=400, detail=f"A {kind} can be registered at: {', '.join(stages.registration_stages(kind))}.")
    else:
        stage = requested
    if number and not stages.is_enacted(kind, stage):
        if number_was_typed:
            raise HTTPException(status_code=400, detail=(
                f"A {kind} gets its number when it is {stages.ENACTED[kind].lower()}. "
                f"Leave the number blank, or register it at {stages.ENACTED[kind]} or later."))
        number = None
    return stage, number


def add_stage_change(db: Session, doc: models.Document, stage: str, *, user, effective_on: date, note=None,
                     committee_id=None, is_correction=False) -> models.DocumentStageChange:
    """Record a stage on a document (the caller commits)."""
    change = models.DocumentStageChange(
        document_id=doc.id, stage=stage, previous_stage=doc.stage, effective_on=effective_on, committee_id=committee_id,
        note=(note or "").strip() or None, is_correction=is_correction,
        changed_by_id=getattr(user, "id", None), changed_by=getattr(user, "username", None),
    )
    db.add(change)
    doc.stage = stage
    return change


def stage_summary(db: Session, doc: models.Document) -> dict | None:
    """The stage and the date each stage was last entered, for lists and the public lookup."""
    kind = stages.measure_kind(doc.document_type)
    if kind is None or not doc.stage:
        return None
    entered = {}
    for change in _changes(db, doc):
        entered[change.stage] = change.effective_on.isoformat()
    return {"stage": doc.stage, "entered_on": entered.get(doc.stage),
            "dates": [{"stage": stage, "date": entered[stage]} for stage in stages.all_stages(kind) if stage in entered]}


def _changes(db, doc):
    return (db.query(models.DocumentStageChange)
            .filter(models.DocumentStageChange.document_id == doc.id)
            .order_by(models.DocumentStageChange.id.asc()).all())


def _document(db, document_id):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _kind(doc):
    kind = stages.measure_kind(doc.document_type)
    if kind is None:
        raise HTTPException(status_code=400, detail="Only ordinances and resolutions have a stage.")
    return kind


def _effective_on(value: date | None) -> date:
    today = lgu_today()
    if value is not None and value > today:
        raise HTTPException(status_code=400, detail="The date can't be in the future.")
    return value or today


def _committee_for(db, stage, committee_id):
    if stage != stages.IN_COMMITTEE:
        return None
    if committee_id is None:
        raise HTTPException(status_code=400, detail="Choose the committee the measure is referred to.")
    committee = db.query(models.Committee).filter(models.Committee.id == committee_id).first()
    if not committee or not committee.is_active:
        raise HTTPException(status_code=400, detail="Choose an active committee.")
    return committee


def _set_enacted_number(db, doc, kind, stage, number, year, effective_on):
    """The enacted number is required the first time a measure reaches Approved/Adopted or later."""
    if not stages.is_enacted(kind, stage) or (doc.document_number and doc.series_year):
        return
    number = (number or "").strip()
    if not number:
        raise HTTPException(status_code=400, detail=f"Enter the {kind} number given when it was {stages.ENACTED[kind].lower()}.")
    year = year or effective_on.year
    from .documents import _documents_with_number  # documents.py imports this module at registration
    clash = [other for other in _documents_with_number(db, doc.document_type, number, year) if other.id != doc.id]
    if clash:
        raise HTTPException(status_code=409, detail=f"{doc.document_type} No. {number}, s. {year} is already {clash[0].tracking_number}.")
    doc.document_number, doc.series_year = number, year


def _payload(db, doc):
    kind = stages.measure_kind(doc.document_type)
    if kind is None:
        return {"is_measure": False, "stage": None, "allowed": [], "stages": [], "history": []}
    return {
        "is_measure": True,
        "kind": kind,
        "stage": doc.stage,
        "allowed": stages.allowed_next(kind, doc.stage),
        "stages": stages.all_stages(kind),
        "enacted_stage": stages.ENACTED[kind],
        "document_number": doc.document_number,
        "series_year": doc.series_year,
        "history": [{
            "id": change.id,
            "stage": change.stage,
            "previous_stage": change.previous_stage,
            "effective_on": change.effective_on.isoformat(),
            "committee": change.committee.name if change.committee else None,
            "note": change.note,
            "is_correction": bool(change.is_correction),
            "changed_by": change.changed_by,
            "recorded_at": change.created_at.isoformat() if change.created_at else None,
        } for change in reversed(_changes(db, doc))],
    }


@router.get("/{document_id:int}/stage")
def get_stage(document_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, "view_document_details")
    return _payload(db, _document(db, document_id))


@router.post("/{document_id:int}/stage")
def change_stage(document_id: int, payload: StageChange, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, CHANGE)
    doc = _document(db, document_id)
    kind = _kind(doc)
    if doc.archived:
        raise HTTPException(status_code=409, detail="Restore the document before changing its stage.")
    allowed = stages.allowed_next(kind, doc.stage)
    if payload.stage not in allowed:
        detail = f"From {doc.stage} it can move to: {', '.join(allowed)}." if allowed else f"{doc.stage} is final."
        raise HTTPException(status_code=400, detail=f"{detail} Use a correction to fix a mistake.")
    effective_on = _effective_on(payload.effective_on)
    history = _changes(db, doc)
    if history and effective_on < history[-1].effective_on:
        latest = history[-1]
        raise HTTPException(status_code=400, detail=f"The date can't be before {latest.effective_on.isoformat()}, when it became {latest.stage}.")
    if stages.is_referral_back(kind, doc.stage, payload.stage) and not (payload.note or "").strip():
        raise HTTPException(status_code=400, detail="Add a note saying why it was referred back to committee.")
    committee = _committee_for(db, payload.stage, payload.committee_id)
    _set_enacted_number(db, doc, kind, payload.stage, payload.document_number, payload.series_year, effective_on)
    previous = doc.stage
    add_stage_change(db, doc, payload.stage, user=current_user, effective_on=effective_on, note=payload.note,
                     committee_id=committee.id if committee else None)
    db.commit()
    where = f" ({committee.name})" if committee else ""
    record_audit_log(db, actor=current_user.username, action="STAGE_CHANGED", target_type="Document", target_id=doc.tracking_number,
                     details=f"{doc.tracking_number}: {previous or 'none'} -> {payload.stage}{where} on {effective_on.isoformat()}")
    db.refresh(doc)
    return _payload(db, doc)


@router.post("/{document_id:int}/stage/corrections")
def correct_stage(document_id: int, payload: StageCorrection, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Fix a wrong stage or date. Any stage is allowed; the reason is kept with the entry."""
    require_permission(current_user, CHANGE)
    doc = _document(db, document_id)
    kind = _kind(doc)
    if payload.stage not in stages.all_stages(kind):
        raise HTTPException(status_code=400, detail=f"A {kind}'s stages are: {', '.join(stages.all_stages(kind))}.")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Say why the stage is being corrected.")
    effective_on = _effective_on(payload.effective_on)
    committee = _committee_for(db, payload.stage, payload.committee_id)
    _set_enacted_number(db, doc, kind, payload.stage, payload.document_number, payload.series_year, effective_on)
    previous = doc.stage
    add_stage_change(db, doc, payload.stage, user=current_user, effective_on=effective_on, note=reason,
                     committee_id=committee.id if committee else None, is_correction=True)
    db.commit()
    record_audit_log(db, actor=current_user.username, action="STAGE_CORRECTED", target_type="Document", target_id=doc.tracking_number,
                     details=f"{doc.tracking_number}: {previous or 'none'} -> {payload.stage} on {effective_on.isoformat()}. Reason: {reason}")
    db.refresh(doc)
    return _payload(db, doc)
