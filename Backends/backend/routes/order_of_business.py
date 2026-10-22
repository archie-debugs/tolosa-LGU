"""A session's order of business: its items, their outcomes and the votes on them (GLOSSARY.md).

Until the session is Held, items are added, removed and reordered, and outcomes and votes are
changed in place. Marking it Held enters each measure's stages from its outcome, linked to the
session. After that, outcomes and votes are corrected with a reason, and a corrected outcome
corrects the stages it entered (docs/adr/0003). The rules live in Backends/backend/business.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import business, models, stages
from ..authentication import get_current_user
from ..core import record_audit_log, require_permission
from ..database import get_db
from .council_sessions import HELD, MANAGE, _session, members_in_office, session_title
from .measure_stages import _committee_for, _set_enacted_number, add_stage_change

router = APIRouter(prefix="/council/sessions", tags=["order-of-business"])


class ItemCreate(BaseModel):
    section: str
    document_id: int | None = None
    title: str | None = Field(default=None, max_length=500, description="For an item without a document")


class ItemOrder(BaseModel):
    section: str
    item_ids: list[int]


class OutcomeSet(BaseModel):
    outcome: str | None = Field(default=None, description="None clears it (before the session is Held)")
    note: str | None = Field(default=None, max_length=2000)
    committee_id: int | None = None
    document_number: str | None = Field(default=None, max_length=40)
    series_year: int | None = None


class OutcomeCorrection(BaseModel):
    outcome: str
    reason: str = Field(..., min_length=1, max_length=2000)
    committee_id: int | None = None
    document_number: str | None = Field(default=None, max_length=40)
    series_year: int | None = None


class MemberVote(BaseModel):
    member_id: int
    vote: str


class VoteSet(BaseModel):
    method: str | None = Field(default=None, description="None clears it (before the session is Held)")
    yes: int = Field(default=0, ge=0)
    no: int = Field(default=0, ge=0)
    abstain: int = Field(default=0, ge=0)
    result: str | None = None
    members: list[MemberVote] = []
    note: str | None = Field(default=None, max_length=1000)


class VoteCorrection(VoteSet):
    reason: str = Field(..., min_length=1, max_length=1000)


# ----- reading -----

def _items(db, session):
    return (db.query(models.SessionItem).filter(models.SessionItem.session_id == session.id)
            .order_by(models.SessionItem.position.asc(), models.SessionItem.id.asc()).all())


def _outcomes(db, item):
    return (db.query(models.SessionItemOutcome).filter(models.SessionItemOutcome.item_id == item.id)
            .order_by(models.SessionItemOutcome.id.asc()).all())


def _votes(db, item):
    return (db.query(models.SessionItemVote).filter(models.SessionItemVote.item_id == item.id)
            .order_by(models.SessionItemVote.id.asc()).all())


def _kind(item):
    return stages.measure_kind(item.document.document_type) if item.document else None


def _recorded(entry):
    return {"is_correction": bool(entry.is_correction), "recorded_by": entry.recorded_by,
            "recorded_at": entry.created_at.isoformat() if entry.created_at else None}


def _outcome_json(entry):
    return {"outcome": entry.outcome, "note": entry.note, "committee": entry.committee.name if entry.committee else None,
            "stages": [stage for stage in (entry.applied_stages or "").split(",") if stage], **_recorded(entry)}


def _vote_json(entry):
    return {"method": entry.method, "yes": entry.yes, "no": entry.no, "abstain": entry.abstain, "result": entry.result,
            "note": entry.note, "members": [{"member_id": row.member_id, "full_name": row.member.full_name, "vote": row.vote}
                                            for row in entry.member_votes], **_recorded(entry)}


def _document_json(doc):
    if doc is None:
        return None
    return {"id": doc.id, "tracking_number": doc.tracking_number, "title": doc.title, "document_type": doc.document_type,
            "stage": doc.stage, "is_measure": stages.measure_kind(doc.document_type) is not None,
            "has_number": bool(doc.document_number and doc.series_year)}


def _item_json(db, item):
    kind = _kind(item)
    outcomes, votes = _outcomes(db, item), _votes(db, item)
    choices = business.outcome_choices(kind)
    return {
        "id": item.id,
        "section": item.section,
        "title": item.title,
        "document": _document_json(item.document),
        "outcome": _outcome_json(outcomes[-1]) if outcomes else None,
        "outcome_history": [_outcome_json(entry) for entry in reversed(outcomes)],
        "vote": _vote_json(votes[-1]) if votes else None,
        "vote_history": [_vote_json(entry) for entry in reversed(votes)],
        "outcome_choices": [{"outcome": name, "committee": business.needs_committee(kind, name),
                             "number": business.needs_number(kind, name)} for name in choices],
    }


def _business(db, session):
    items = _items(db, session)
    return {
        "session_id": session.id,
        "editable": session.status != HELD,
        "sections": [{"key": key, "label": label, "items": [_item_json(db, item) for item in items if item.section == key]}
                     for key, label in business.SECTIONS],
        "without_outcome": sum(1 for item in items if item.document_id and not _outcomes(db, item)),
    }


def _item(db, session, item_id):
    item = db.query(models.SessionItem).filter(models.SessionItem.id == item_id, models.SessionItem.session_id == session.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in this session")
    return item


def _not_held(session, what):
    if session.status == HELD:
        raise HTTPException(status_code=409, detail=f"The session is held; {what}")


def _held(session, what):
    if session.status != HELD:
        raise HTTPException(status_code=409, detail=f"The session isn't held yet; {what}")


def _check_section(section):
    if section not in business.SECTION_LABELS:
        raise HTTPException(status_code=400, detail="Unknown section of the order of business")


def _label(session):
    return f"{session_title(session)} of {session.held_on}"


def _audit(db, user, action, session, details):
    record_audit_log(db, actor=user.username, action=action, target_type="Session", target_id=str(session.id),
                     details=f"{_label(session)}: {details}")


@router.get("/{session_id}/business")
def get_business(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, "view_documents")
    return _business(db, _session(db, session_id))


@router.get("/{session_id}/business/suggestions")
def suggestions(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Measures ready for this session, by stage, plus unfinished business from the term's earlier held sessions."""
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    taken = {item.document_id for item in _items(db, session) if item.document_id}
    found, seen = [], set(taken)

    def offer(doc, section, reason):
        if doc.id in seen or doc.archived or stages.measure_kind(doc.document_type) is None:
            return
        seen.add(doc.id)
        found.append({"section": section, "section_label": business.SECTION_LABELS[section], "reason": reason, "document": _document_json(doc)})

    earlier = (db.query(models.SessionItem).join(models.CouncilSession, models.SessionItem.session_id == models.CouncilSession.id)
               .filter(models.CouncilSession.term_id == session.term_id, models.CouncilSession.status == HELD,
                       models.CouncilSession.held_on <= session.held_on, models.CouncilSession.id != session.id,
                       models.SessionItem.document_id.isnot(None))
               .order_by(models.CouncilSession.held_on.desc(), models.CouncilSession.id.desc()).all())
    latest = {}
    for item in earlier:
        latest.setdefault(item.document_id, item)
    for item in latest.values():
        outcomes = _outcomes(db, item)
        if not outcomes or outcomes[-1].outcome == business.DEFERRED:
            offer(item.document, "unfinished", f"{'Deferred' if outcomes else 'No outcome'} at the {_label(item.council_session)}")
    for section, wanted in business.SUGGESTED_BY_STAGE.items():
        for doc in (db.query(models.Document).filter(models.Document.stage.in_(wanted), models.Document.archived.is_(False))
                    .order_by(models.Document.id.asc()).all()):
            offer(doc, section, f"At {doc.stage}")
    return found


@router.get("/{session_id}/business/documents")
def find_documents(session_id: int, search: str = Query(..., min_length=2), db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """Documents to add by hand, by tracking number or title."""
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    taken = {item.document_id for item in _items(db, session)}
    like = f"%{search.strip()}%"
    docs = (db.query(models.Document).filter(models.Document.archived.is_(False),
                                             or_(models.Document.tracking_number.ilike(like), models.Document.title.ilike(like)))
            .order_by(models.Document.id.desc()).limit(20).all())
    return [_document_json(doc) for doc in docs if doc.id not in taken]


# ----- items -----

@router.post("/{session_id}/business/items")
def add_item(session_id: int, payload: ItemCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    _not_held(session, "its order of business is fixed")
    _check_section(payload.section)
    doc = None
    if payload.document_id is not None:
        doc = db.query(models.Document).filter(models.Document.id == payload.document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if any(item.document_id == doc.id for item in _items(db, session)):
            raise HTTPException(status_code=409, detail=f"{doc.tracking_number} is already in this session's order of business")
        title = doc.title
    else:
        title = (payload.title or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="Choose a document or give the item a title")
    position = max([item.position for item in _items(db, session) if item.section == payload.section], default=0) + 1
    item = models.SessionItem(session_id=session.id, section=payload.section, position=position, document_id=doc.id if doc else None,
                              title=title, added_by=current_user.username)
    db.add(item)
    db.commit()
    what = f"{doc.tracking_number} {title}" if doc else title
    _audit(db, current_user, "AGENDA_ITEM_ADDED", session, f"added {what} under {business.SECTION_LABELS[payload.section]}")
    return _business(db, session)


@router.delete("/{session_id}/business/items/{item_id}")
def remove_item(session_id: int, item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    _not_held(session, "its order of business is fixed")
    item = _item(db, session, item_id)
    _delete_items(db, [item])
    db.commit()
    _audit(db, current_user, "AGENDA_ITEM_REMOVED", session, f"removed {item.title}")
    return _business(db, session)


@router.put("/{session_id}/business/order")
def reorder(session_id: int, payload: ItemOrder, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Put the given items, in this order, in the section; items from another section move into it."""
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    _not_held(session, "its order of business is fixed")
    _check_section(payload.section)
    items = {item.id: item for item in _items(db, session)}
    if len(set(payload.item_ids)) != len(payload.item_ids) or any(item_id not in items for item_id in payload.item_ids):
        raise HTTPException(status_code=400, detail="List each item of this session once")
    staying = [item.id for item in items.values() if item.section == payload.section and item.id not in payload.item_ids]
    for position, item_id in enumerate(payload.item_ids + staying, start=1):
        items[item_id].section, items[item_id].position = payload.section, position
    db.commit()
    _audit(db, current_user, "AGENDA_REORDERED", session, f"reordered {business.SECTION_LABELS[payload.section]}")
    return _business(db, session)


def _delete_items(db, items):
    """Remove items with their outcomes and votes (only before the session is Held)."""
    for item in items:
        for vote in _votes(db, item):
            db.delete(vote)
        for outcome in _outcomes(db, item):
            db.delete(outcome)
        db.delete(item)


def delete_business(db, session):
    """Called when a Draft session is deleted (the caller commits)."""
    _delete_items(db, _items(db, session))


# ----- outcomes -----

def _check_outcome(db, item, outcome, committee_id, number):
    """Validate an outcome against the item as it is now; returns the committee, if any."""
    kind = _kind(item)
    if outcome not in business.outcome_choices(kind):
        allowed = ", ".join(business.outcome_choices(kind))
        raise HTTPException(status_code=400, detail=f"The outcome for this item is one of: {allowed}")
    committee = None
    if business.needs_committee(kind, outcome):
        committee = _committee_for(db, stages.IN_COMMITTEE, committee_id)
    if business.needs_number(kind, outcome) and not (item.document.document_number and item.document.series_year) and not (number or "").strip():
        raise HTTPException(status_code=400, detail=f"Enter the {kind} number given when it was {stages.ENACTED[kind].lower()}.")
    return committee


@router.put("/{session_id}/business/items/{item_id}/outcome")
def set_outcome(session_id: int, item_id: int, payload: OutcomeSet, db: Session = Depends(get_db),
                current_user: models.User = Depends(get_current_user)):
    """Record an item's outcome before the session is Held; its stages are entered when the session is."""
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    _not_held(session, "correct the outcome with a reason instead")
    item = _item(db, session, item_id)
    current = (_outcomes(db, item) or [None])[-1]
    if payload.outcome is None:
        if current:
            db.delete(current)
            db.commit()
            _audit(db, current_user, "OUTCOME_RECORDED", session, f"{item.title}: outcome cleared")
        return _business(db, session)
    note = (payload.note or "").strip() or None
    committee = _check_outcome(db, item, payload.outcome, payload.committee_id, payload.document_number)
    kind = _kind(item)
    if kind:
        try:
            business.plan(kind, item.document.stage, payload.outcome, note)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    entry = current or models.SessionItemOutcome(item_id=item.id)
    entry.outcome, entry.note, entry.committee_id = payload.outcome, note, committee.id if committee else None
    entry.document_number = (payload.document_number or "").strip() or None
    entry.series_year = payload.series_year
    entry.recorded_by_id, entry.recorded_by = current_user.id, current_user.username
    db.add(entry)
    db.commit()
    _audit(db, current_user, "OUTCOME_RECORDED", session, f"{item.title}: {payload.outcome}")
    return _business(db, session)


def _enter_stages(db, session, item, entry, user, *, correction_reason=None, start=None):
    """Enter the stages of `entry` for a measure item, linked to the session; returns them. Raises ValueError."""
    doc, kind = item.document, _kind(item)
    if doc.archived:
        raise ValueError("restore the document first")
    start = doc.stage if start is None else start
    planned = business.plan(kind, start, entry.outcome, entry.note) if entry.outcome in business.MEASURE_OUTCOMES else []
    latest = (db.query(models.DocumentStageChange).filter(models.DocumentStageChange.document_id == doc.id)
              .order_by(models.DocumentStageChange.id.desc()).first())
    if correction_reason is None and latest and latest.effective_on > session.held_on:
        raise ValueError(f"its stage history already has an entry on {latest.effective_on}, after this session")
    if any(stages.is_enacted(kind, stage) for stage in planned):
        try:
            _set_enacted_number(db, doc, kind, planned[-1], entry.document_number, entry.series_year, session.held_on)
        except HTTPException as exc:
            raise ValueError(exc.detail)
    targets = planned or ([start] if correction_reason and doc.stage != start else [])
    for stage in targets:
        add_stage_change(db, doc, stage, user=user, effective_on=session.held_on,
                         note=correction_reason or entry.note,
                         committee_id=entry.committee_id if stage == stages.IN_COMMITTEE else None,
                         is_correction=correction_reason is not None, session_id=session.id)
    entry.stage_before, entry.applied_stages = start, ",".join(planned) or None
    return targets


def apply_outcomes(db, session, user):
    """Enter every measure item's stages as the session becomes Held (the caller commits).

    Raises HTTPException listing every item that can't move, and changes nothing then.
    """
    problems, moved = [], []
    for item in _items(db, session):
        outcomes = _outcomes(db, item)
        if not outcomes or not item.document or _kind(item) is None:
            continue
        try:
            entered = _enter_stages(db, session, item, outcomes[-1], user)
        except ValueError as exc:
            problems.append(f"{item.document.tracking_number}: {exc}")
            continue
        if entered:
            moved.append(f"{item.document.tracking_number} -> {entered[-1]}")
    if problems:
        db.rollback()
        raise HTTPException(status_code=400, detail="Fix these outcomes first. " + " ".join(problems))
    return moved


@router.post("/{session_id}/business/items/{item_id}/outcome/corrections")
def correct_outcome(session_id: int, item_id: int, payload: OutcomeCorrection, db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    """Fix a held session's outcome. A measure's stages are corrected to match; the earlier entries stay."""
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    _held(session, "change the outcome directly")
    item = _item(db, session, item_id)
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Say why the outcome is being corrected")
    committee = _check_outcome(db, item, payload.outcome, payload.committee_id, payload.document_number)
    previous = (_outcomes(db, item) or [None])[-1]
    entry = models.SessionItemOutcome(item_id=item.id, outcome=payload.outcome, note=reason, committee_id=committee.id if committee else None,
                                      document_number=(payload.document_number or "").strip() or None, series_year=payload.series_year,
                                      is_correction=True, recorded_by_id=current_user.id, recorded_by=current_user.username)
    entered = []
    if _kind(item):
        doc = item.document
        start = previous.stage_before if previous and previous.stage_before is not None else doc.stage
        applied = [stage for stage in ((previous.applied_stages or "") if previous else "").split(",") if stage]
        if doc.stage != (applied[-1] if applied else start):
            raise HTTPException(status_code=409, detail=(
                f"{doc.tracking_number} has moved on to {doc.stage} since this session; correct its stage directly"))
        try:
            entered = _enter_stages(db, session, item, entry, current_user, correction_reason=reason, start=start)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))
    db.add(entry)
    db.commit()
    stage_text = f"; stage -> {entered[-1]}" if entered else ""
    _audit(db, current_user, "OUTCOME_CORRECTED", session,
           f"{item.title}: {previous.outcome if previous else 'none'} -> {payload.outcome}{stage_text}. Reason: {reason}")
    return _business(db, session)


# ----- votes -----

def _vote_values(db, session, payload):
    """(yes, no, abstain, member votes) checked against the session's members; a nominal tally is counted."""
    if payload.method not in business.VOTE_METHODS:
        raise HTTPException(status_code=400, detail="A vote is Voice or Nominal")
    if payload.result not in business.RESULTS:
        raise HTTPException(status_code=400, detail="The result is Carried or Lost")
    if payload.method == "Voice":
        if payload.members:
            raise HTTPException(status_code=400, detail="Only a nominal vote records each member's vote")
        if payload.yes + payload.no + payload.abstain == 0:
            raise HTTPException(status_code=400, detail="Enter the tally")
        return payload.yes, payload.no, payload.abstain, []
    in_office = {member.id for member in members_in_office(db, session)}
    seen = set()
    for row in payload.members:
        if row.member_id not in in_office or row.member_id in seen:
            raise HTTPException(status_code=400, detail="List each member in office once")
        if row.vote not in business.VOTES:
            raise HTTPException(status_code=400, detail="A member votes Yes, No or Abstain")
        seen.add(row.member_id)
    if not payload.members:
        raise HTTPException(status_code=400, detail="A nominal vote needs each member's vote")
    count = lambda value: sum(1 for row in payload.members if row.vote == value)
    return count("Yes"), count("No"), count("Abstain"), payload.members


def _vote_text(entry):
    return f"{entry.method} vote {entry.yes}-{entry.no}-{entry.abstain}, {entry.result}"


def _fill_vote(entry, values, payload, note, user):
    entry.method, entry.result, entry.note = payload.method, payload.result, note
    entry.yes, entry.no, entry.abstain, members = values
    entry.member_votes = [models.SessionMemberVote(member_id=row.member_id, vote=row.vote) for row in members]
    entry.recorded_by_id, entry.recorded_by = user.id, user.username


@router.put("/{session_id}/business/items/{item_id}/vote")
def set_vote(session_id: int, item_id: int, payload: VoteSet, db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    _not_held(session, "correct the vote with a reason instead")
    item = _item(db, session, item_id)
    current = (_votes(db, item) or [None])[-1]
    if payload.method is None:
        if current:
            db.delete(current)
            db.commit()
            _audit(db, current_user, "VOTE_RECORDED", session, f"{item.title}: vote cleared")
        return _business(db, session)
    values = _vote_values(db, session, payload)
    entry = current or models.SessionItemVote(item_id=item.id)
    _fill_vote(entry, values, payload, (payload.note or "").strip() or None, current_user)
    db.add(entry)
    db.commit()
    _audit(db, current_user, "VOTE_RECORDED", session, f"{item.title}: {_vote_text(entry)}")
    return _business(db, session)


@router.post("/{session_id}/business/items/{item_id}/vote/corrections")
def correct_vote(session_id: int, item_id: int, payload: VoteCorrection, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    _held(session, "change the vote directly")
    item = _item(db, session, item_id)
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Say why the vote is being corrected")
    values = _vote_values(db, session, payload)
    previous = (_votes(db, item) or [None])[-1]
    entry = models.SessionItemVote(item_id=item.id, is_correction=True)
    _fill_vote(entry, values, payload, reason, current_user)
    db.add(entry)
    db.commit()
    _audit(db, current_user, "VOTE_CORRECTED", session,
           f"{item.title}: {_vote_text(previous) if previous else 'no vote'} -> {_vote_text(entry)}. Reason: {reason}")
    return _business(db, session)
