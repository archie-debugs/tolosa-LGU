"""SB sessions and attendance (GLOSSARY.md: Session, Attendance, Quorum).

A session goes Draft -> Scheduled -> Held. Until it is Held its details and attendance can be changed
freely; after that an attendance change is a correction with a reason, and the earlier entry stays
(docs/adr/0003). Quorum is shown, never enforced.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..authentication import get_current_user
from ..core import lgu_today, record_audit_log, require_permission
from ..database import get_db
from .council import POSITIONS

router = APIRouter(prefix="/council/sessions", tags=["council-sessions"])

MANAGE = "manage_sessions"
KINDS = ("Regular", "Special")
MARKS = ("Present", "Absent", "On leave", "Excused")
DRAFT, SCHEDULED, HELD = "Draft", "Scheduled", "Held"
# Held is final: after it, attendance is corrected, not edited.
NEXT_STATUSES = {DRAFT: [SCHEDULED, HELD], SCHEDULED: [DRAFT, HELD], HELD: []}


class SessionCreate(BaseModel):
    term_id: int
    kind: str
    number: int | None = Field(default=None, ge=1, description="Defaults to the next number for this kind in the term")
    held_on: date


class SessionUpdate(BaseModel):
    kind: str
    number: int = Field(..., ge=1)
    held_on: date


class StatusChange(BaseModel):
    status: str


class AttendanceMark(BaseModel):
    member_id: int
    mark: str | None = Field(default=None, description="None clears the mark (before the session is Held)")
    note: str | None = Field(default=None, max_length=1000)


class AttendancePayload(BaseModel):
    marks: list[AttendanceMark]


class AttendanceCorrection(BaseModel):
    member_id: int
    mark: str
    reason: str = Field(..., min_length=1, max_length=1000)


def ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def session_title(session) -> str:
    return f"{ordinal(session.number)} {session.kind} Session"


def members_in_office(db, session):
    """The term's members who had not left by the session date, presiding officer first."""
    members = [member for member in db.query(models.CouncilMember).filter(models.CouncilMember.term_id == session.term_id).all()
               if member.left_on is None or member.left_on > session.held_on]
    order = {position: index for index, position in enumerate(POSITIONS)}
    return sorted(members, key=lambda member: (order.get(member.position, 99), member.full_name.lower()))


def _entries(db, session):
    """Attendance entries per member id, oldest first."""
    entries = {}
    for entry in (db.query(models.SessionAttendance).filter(models.SessionAttendance.session_id == session.id)
                  .order_by(models.SessionAttendance.id.asc()).all()):
        entries.setdefault(entry.member_id, []).append(entry)
    return entries


def quorum(members, entries) -> dict:
    """A majority of all members in office (LGC Sec. 53) must be present."""
    present = sum(1 for member in members if entries.get(member.id) and entries[member.id][-1].mark == "Present")
    needed = len(members) // 2 + 1 if members else 0
    unmarked = sum(1 for member in members if not entries.get(member.id))
    return {"present": present, "in_office": len(members), "needed": needed,
            "has_quorum": bool(members) and present >= needed, "unmarked": unmarked}


def _summary(db, session) -> dict:
    return {
        "id": session.id,
        "term_id": session.term_id,
        "term_name": session.term.name if session.term else None,
        "kind": session.kind,
        "number": session.number,
        "title": session_title(session),
        "held_on": session.held_on.isoformat(),
        "status": session.status,
        "next_statuses": NEXT_STATUSES[session.status],
        "quorum": quorum(members_in_office(db, session), _entries(db, session)),
    }


def _entry_json(entry) -> dict:
    return {"mark": entry.mark, "note": entry.note, "is_correction": bool(entry.is_correction), "recorded_by": entry.recorded_by,
            "recorded_at": entry.created_at.isoformat() if entry.created_at else None}


def _detail(db, session) -> dict:
    entries = _entries(db, session)
    members = members_in_office(db, session)
    return {
        **_summary(db, session),
        "attendance": [{
            "member_id": member.id,
            "full_name": member.full_name,
            "position": member.position,
            "mark": entries[member.id][-1].mark if entries.get(member.id) else None,
            "note": entries[member.id][-1].note if entries.get(member.id) else None,
            "history": [_entry_json(entry) for entry in reversed(entries.get(member.id, []))],
        } for member in members],
    }


def _session(db, session_id):
    session = db.query(models.CouncilSession).filter(models.CouncilSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _check_details(db, term, kind, number, held_on, session_id=None):
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="A session is Regular or Special")
    if not term.starts_on <= held_on <= term.ends_on:
        raise HTTPException(status_code=400, detail=f"The date must fall within the {term.name} ({term.starts_on} to {term.ends_on})")
    clash = db.query(models.CouncilSession.id).filter(
        models.CouncilSession.term_id == term.id, models.CouncilSession.kind == kind,
        models.CouncilSession.number == number, models.CouncilSession.id != (session_id or 0),
    ).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"The {term.name} already has a {ordinal(number)} {kind} Session")


def _next_number(db, term_id, kind) -> int:
    numbers = [row.number for row in db.query(models.CouncilSession.number).filter(
        models.CouncilSession.term_id == term_id, models.CouncilSession.kind == kind)]
    return max(numbers, default=0) + 1


def _member_in_office(session, members, member_id):
    member = next((member for member in members if member.id == member_id), None)
    if member is None:
        raise HTTPException(status_code=400, detail=f"Member {member_id} was not a member of the {session.term.name} on {session.held_on}")
    return member


def _check_mark(mark):
    if mark not in MARKS:
        raise HTTPException(status_code=400, detail=f"Attendance is one of: {', '.join(MARKS)}")


@router.get("")
def list_sessions(
    term_id: int | None = Query(default=None, description="Defaults to the current term"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_permission(current_user, "view_documents")
    if term_id is None:
        today = lgu_today()
        current = db.query(models.CouncilTerm).filter(models.CouncilTerm.starts_on <= today, models.CouncilTerm.ends_on >= today).first()
        if not current:
            return {"sessions": [], "next_numbers": {}}
        term_id = current.id
    sessions = (db.query(models.CouncilSession).filter(models.CouncilSession.term_id == term_id)
                .order_by(models.CouncilSession.held_on.desc(), models.CouncilSession.id.desc()).all())
    return {"sessions": [_summary(db, session) for session in sessions],
            "next_numbers": {kind: _next_number(db, term_id, kind) for kind in KINDS}}


@router.post("")
def create_session(payload: SessionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    term = db.query(models.CouncilTerm).filter(models.CouncilTerm.id == payload.term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="Term not found")
    number = payload.number or _next_number(db, term.id, payload.kind)
    _check_details(db, term, payload.kind, number, payload.held_on)
    session = models.CouncilSession(term_id=term.id, kind=payload.kind, number=number, held_on=payload.held_on,
                                    status=DRAFT, created_by=current_user.username)
    db.add(session)
    db.commit()
    db.refresh(session)
    record_audit_log(db, actor=current_user.username, action="SESSION_CREATED", target_type="Session", target_id=str(session.id),
                     details=f"Created the {session_title(session)} of the {term.name} on {session.held_on}")
    return _detail(db, session)


@router.get("/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, "view_documents")
    return _detail(db, _session(db, session_id))


@router.put("/{session_id}")
def update_session(session_id: int, payload: SessionUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    if session.status == HELD:
        raise HTTPException(status_code=409, detail="A held session's number and date can't be changed")
    _check_details(db, session.term, payload.kind, payload.number, payload.held_on, session.id)
    before = f"{session_title(session)} on {session.held_on}"
    session.kind, session.number, session.held_on = payload.kind, payload.number, payload.held_on
    # Members who were no longer in office on the new date lose their mark.
    in_office = {member.id for member in members_in_office(db, session)}
    for entries in _entries(db, session).values():
        for entry in entries:
            if entry.member_id not in in_office:
                db.delete(entry)
    db.commit()
    record_audit_log(db, actor=current_user.username, action="SESSION_UPDATED", target_type="Session", target_id=str(session.id),
                     details=f"{before} -> {session_title(session)} on {session.held_on}")
    return _detail(db, session)


@router.post("/{session_id}/status")
def change_status(session_id: int, payload: StatusChange, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    if payload.status not in NEXT_STATUSES[session.status]:
        allowed = ", ".join(NEXT_STATUSES[session.status]) or "nothing; it is final"
        raise HTTPException(status_code=400, detail=f"A {session.status} session can only become {allowed}")
    if payload.status == HELD and session.held_on > lgu_today():
        raise HTTPException(status_code=400, detail=f"The session is on {session.held_on}; it can be marked held on or after that day")
    moved = []
    if payload.status == HELD:
        from .order_of_business import apply_outcomes  # it imports this module
        moved = apply_outcomes(db, session, current_user)
    previous, session.status = session.status, payload.status
    db.commit()
    summary = quorum(members_in_office(db, session), _entries(db, session))
    extra = f"; {summary['present']} of {summary['in_office']} present" if payload.status == HELD else ""
    if moved:
        extra += "; stages: " + ", ".join(moved)
    record_audit_log(db, actor=current_user.username, action="SESSION_STATUS_CHANGED", target_type="Session", target_id=str(session.id),
                     details=f"{session_title(session)} of {session.held_on}: {previous} -> {payload.status}{extra}")
    return _detail(db, session)


@router.delete("/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Only a Draft session, which is not yet part of the record, can be deleted."""
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    if session.status != DRAFT:
        raise HTTPException(status_code=409, detail="Only a Draft session can be deleted")
    title = f"{session_title(session)} of {session.held_on}"
    db.query(models.SessionAttendance).filter(models.SessionAttendance.session_id == session.id).delete()
    from .order_of_business import delete_business  # it imports this module
    delete_business(db, session)
    db.delete(session)
    db.commit()
    record_audit_log(db, actor=current_user.username, action="SESSION_DELETED", target_type="Session", target_id=str(session_id),
                     details=f"Deleted the Draft {title}")
    return {"deleted": session_id}


@router.put("/{session_id}/attendance")
def record_attendance(session_id: int, payload: AttendancePayload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Set attendance before the session is Held; each member's entry is replaced."""
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    if session.status == HELD:
        raise HTTPException(status_code=409, detail="The session is held; correct attendance with a reason instead")
    members = members_in_office(db, session)
    entries = _entries(db, session)
    changes = []
    for item in payload.marks:
        member = _member_in_office(session, members, item.member_id)
        current = (entries.get(member.id) or [None])[-1]
        note = (item.note or "").strip() or None
        if item.mark is None:
            if current:
                db.delete(current)
                changes.append(f"{member.full_name}: cleared")
            continue
        _check_mark(item.mark)
        if current and (current.mark, current.note) == (item.mark, note):
            continue
        if current:
            current.mark, current.note = item.mark, note
            current.recorded_by_id, current.recorded_by = current_user.id, current_user.username
        else:
            db.add(models.SessionAttendance(session_id=session.id, member_id=member.id, mark=item.mark, note=note,
                                            recorded_by_id=current_user.id, recorded_by=current_user.username))
        changes.append(f"{member.full_name}: {item.mark}")
    db.commit()
    if changes:
        record_audit_log(db, actor=current_user.username, action="ATTENDANCE_RECORDED", target_type="Session", target_id=str(session.id),
                         details=f"{session_title(session)} of {session.held_on}: " + "; ".join(changes))
    return _detail(db, session)


@router.post("/{session_id}/attendance/corrections")
def correct_attendance(session_id: int, payload: AttendanceCorrection, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Fix a held session's attendance. The reason is kept with the new entry; the old one stays."""
    require_permission(current_user, MANAGE)
    session = _session(db, session_id)
    if session.status != HELD:
        raise HTTPException(status_code=409, detail="The session isn't held yet; change the attendance directly")
    member = _member_in_office(session, members_in_office(db, session), payload.member_id)
    _check_mark(payload.mark)
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Say why the attendance is being corrected")
    previous = (_entries(db, session).get(member.id) or [None])[-1]
    db.add(models.SessionAttendance(session_id=session.id, member_id=member.id, mark=payload.mark, note=reason, is_correction=True,
                                    recorded_by_id=current_user.id, recorded_by=current_user.username))
    db.commit()
    record_audit_log(db, actor=current_user.username, action="ATTENDANCE_CORRECTED", target_type="Session", target_id=str(session.id),
                     details=f"{session_title(session)} of {session.held_on}: {member.full_name} "
                             f"{previous.mark if previous else 'unmarked'} -> {payload.mark}. Reason: {reason}")
    return _detail(db, session)
