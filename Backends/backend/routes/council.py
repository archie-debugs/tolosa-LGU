"""SB terms, the member roster and committees (GLOSSARY.md: Term, Member, Committee).

Nothing here is ever deleted: members are given a left_on date and committees are deactivated,
because sessions, votes and referrals keep pointing at them (docs/adr/0002).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..authentication import get_current_user
from ..core import lgu_today, normalize_user_role, record_audit_log, require_permission
from ..database import get_db

router = APIRouter(prefix="/council", tags=["council"])

POSITIONS = ("Vice Mayor", "Regular Member", "Liga ng mga Barangay President", "SK Federation President", "IPMR")
# Positions held by one member at a time within a term.
SINGLE_SEAT_POSITIONS = {"Vice Mayor", "Liga ng mga Barangay President", "SK Federation President", "IPMR"}
MANAGE = "manage_members_and_committees"


class TermPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    starts_on: date
    ends_on: date


class MemberCreate(BaseModel):
    term_id: int
    full_name: str = Field(..., min_length=1, max_length=160)
    position: str
    user_id: int | None = None


class MemberUpdate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=160)
    position: str
    user_id: int | None = None
    left_on: date | None = None


class CommitteePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    chair_member_id: int | None = None
    is_active: bool = True


def _is_current(term, today):
    return term.starts_on <= today <= term.ends_on


def _is_active_member(member, today):
    return member.left_on is None or member.left_on > today


def _term_json(term, today):
    return {"id": term.id, "name": term.name, "starts_on": term.starts_on.isoformat(),
            "ends_on": term.ends_on.isoformat(), "is_current": _is_current(term, today)}


def _member_json(member, today):
    return {
        "id": member.id,
        "term_id": member.term_id,
        "term_name": member.term.name if member.term else None,
        "full_name": member.full_name,
        "position": member.position,
        "user_id": member.user_id,
        "username": member.user.username if member.user else None,
        "left_on": member.left_on.isoformat() if member.left_on else None,
        "is_active": _is_active_member(member, today),
    }


def _committee_json(committee):
    return {
        "id": committee.id,
        "name": committee.name,
        "chair_member_id": committee.chair_member_id,
        "chair_name": committee.chair.full_name if committee.chair else None,
        "is_active": bool(committee.is_active),
    }


def _check_term_dates(db, payload, term_id=None):
    if payload.ends_on <= payload.starts_on:
        raise HTTPException(status_code=400, detail="A term must end after it starts")
    name = payload.name.strip()
    if db.query(models.CouncilTerm).filter(models.CouncilTerm.name.ilike(name), models.CouncilTerm.id != (term_id or 0)).first():
        raise HTTPException(status_code=409, detail="A term with this name already exists")
    overlapping = db.query(models.CouncilTerm).filter(
        models.CouncilTerm.id != (term_id or 0),
        models.CouncilTerm.starts_on <= payload.ends_on,
        models.CouncilTerm.ends_on >= payload.starts_on,
    ).first()
    if overlapping:
        raise HTTPException(status_code=409, detail=f"These dates overlap the {overlapping.name}")
    return name


def _check_member(db, term_id, position, user_id, today, member_id=None):
    if position not in POSITIONS:
        raise HTTPException(status_code=400, detail=f"Position must be one of: {', '.join(POSITIONS)}")
    others = [member for member in db.query(models.CouncilMember).filter(
        models.CouncilMember.term_id == term_id, models.CouncilMember.id != (member_id or 0),
    ).all() if _is_active_member(member, today)]
    if position in SINGLE_SEAT_POSITIONS and any(member.position == position for member in others):
        raise HTTPException(status_code=409, detail=f"This term already has a {position}")
    if user_id is not None:
        if not db.query(models.User.id).filter(models.User.id == user_id).first():
            raise HTTPException(status_code=404, detail="User account not found")
        if any(member.user_id == user_id for member in others):
            raise HTTPException(status_code=409, detail="That user account is already linked to another member of this term")


def _chair(db, chair_member_id, today):
    if chair_member_id is None:
        return None
    member = db.query(models.CouncilMember).filter(models.CouncilMember.id == chair_member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Chair not found")
    if not _is_active_member(member, today):
        raise HTTPException(status_code=400, detail="The chair must be a current member")
    return member


@router.get("/terms")
def list_terms(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, "view_documents")
    today = lgu_today()
    return [_term_json(term, today) for term in db.query(models.CouncilTerm).order_by(models.CouncilTerm.starts_on.desc()).all()]


@router.post("/terms")
def create_term(payload: TermPayload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    name = _check_term_dates(db, payload)
    term = models.CouncilTerm(name=name, starts_on=payload.starts_on, ends_on=payload.ends_on)
    db.add(term)
    db.commit()
    db.refresh(term)
    record_audit_log(db, actor=current_user.username, action="COUNCIL_TERM_CREATED", target_type="Council term",
                     target_id=str(term.id), details=f"Created {name} ({payload.starts_on} to {payload.ends_on})")
    return _term_json(term, lgu_today())


@router.put("/terms/{term_id}")
def update_term(term_id: int, payload: TermPayload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    term = db.query(models.CouncilTerm).filter(models.CouncilTerm.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="Term not found")
    name = _check_term_dates(db, payload, term_id)
    before = f"{term.name} ({term.starts_on} to {term.ends_on})"
    term.name, term.starts_on, term.ends_on = name, payload.starts_on, payload.ends_on
    db.commit()
    record_audit_log(db, actor=current_user.username, action="COUNCIL_TERM_UPDATED", target_type="Council term",
                     target_id=str(term.id), details=f"{before} -> {name} ({payload.starts_on} to {payload.ends_on})")
    return _term_json(term, lgu_today())


@router.get("/members")
def list_members(
    term_id: int | None = Query(default=None, description="Defaults to the current term"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_permission(current_user, "view_documents")
    today = lgu_today()
    if term_id is None:
        current = db.query(models.CouncilTerm).filter(
            models.CouncilTerm.starts_on <= today, models.CouncilTerm.ends_on >= today,
        ).first()
        if not current:
            return []
        term_id = current.id
    members = db.query(models.CouncilMember).filter(models.CouncilMember.term_id == term_id).all()
    order = {position: index for index, position in enumerate(POSITIONS)}
    members.sort(key=lambda member: (not _is_active_member(member, today), order.get(member.position, 99), member.full_name.lower()))
    return [_member_json(member, today) for member in members]


@router.get("/member-accounts")
def list_member_accounts(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Active SB Member accounts with their SB position, to pick from when adding a member to a term."""
    require_permission(current_user, MANAGE)
    users = [user for user in db.query(models.User).filter(models.User.is_active.is_(True)).all()
             if normalize_user_role(user.role) == "SB Member"]
    order = {position: index for index, position in enumerate(POSITIONS)}
    users.sort(key=lambda user: (order.get(user.sb_position, 99), (user.full_name or user.username).lower()))
    return [{"id": user.id, "full_name": user.full_name or user.username, "username": user.username,
             "sb_position": user.sb_position} for user in users]


@router.post("/members")
def add_member(payload: MemberCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    if not db.query(models.CouncilTerm.id).filter(models.CouncilTerm.id == payload.term_id).first():
        raise HTTPException(status_code=404, detail="Term not found")
    today = lgu_today()
    _check_member(db, payload.term_id, payload.position, payload.user_id, today)
    member = models.CouncilMember(term_id=payload.term_id, full_name=payload.full_name.strip(),
                                  position=payload.position, user_id=payload.user_id)
    db.add(member)
    db.commit()
    db.refresh(member)
    record_audit_log(db, actor=current_user.username, action="COUNCIL_MEMBER_ADDED", target_type="Council member",
                     target_id=str(member.id), details=f"Added {member.full_name} as {member.position} ({member.term.name})")
    return _member_json(member, today)


@router.put("/members/{member_id}")
def update_member(member_id: int, payload: MemberUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    member = db.query(models.CouncilMember).filter(models.CouncilMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    today = lgu_today()
    if payload.left_on is None or payload.left_on > today:
        _check_member(db, member.term_id, payload.position, payload.user_id, today, member_id)
    elif payload.position not in POSITIONS:
        raise HTTPException(status_code=400, detail=f"Position must be one of: {', '.join(POSITIONS)}")
    before = f"{member.full_name}, {member.position}, left {member.left_on or '-'}"
    member.full_name, member.position = payload.full_name.strip(), payload.position
    member.user_id, member.left_on = payload.user_id, payload.left_on
    db.commit()
    db.refresh(member)
    record_audit_log(db, actor=current_user.username, action="COUNCIL_MEMBER_UPDATED", target_type="Council member",
                     target_id=str(member.id), details=f"{before} -> {member.full_name}, {member.position}, left {member.left_on or '-'}")
    return _member_json(member, today)


@router.get("/committees")
def list_committees(active_only: bool = Query(False), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, "view_documents")
    query = db.query(models.Committee)
    if active_only:
        query = query.filter(models.Committee.is_active.is_(True))
    return [_committee_json(committee) for committee in query.order_by(models.Committee.name.asc()).all()]


@router.post("/committees")
def create_committee(payload: CommitteePayload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    name = payload.name.strip()
    if db.query(models.Committee.id).filter(models.Committee.name.ilike(name)).first():
        raise HTTPException(status_code=409, detail="A committee with this name already exists")
    chair = _chair(db, payload.chair_member_id, lgu_today())
    committee = models.Committee(name=name, chair_member_id=chair.id if chair else None, is_active=True)
    db.add(committee)
    db.commit()
    db.refresh(committee)
    record_audit_log(db, actor=current_user.username, action="COMMITTEE_CREATED", target_type="Committee",
                     target_id=str(committee.id), details=f"Created {name}; chair {chair.full_name if chair else 'none'}")
    return _committee_json(committee)


@router.put("/committees/{committee_id}")
def update_committee(committee_id: int, payload: CommitteePayload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, MANAGE)
    committee = db.query(models.Committee).filter(models.Committee.id == committee_id).first()
    if not committee:
        raise HTTPException(status_code=404, detail="Committee not found")
    name = payload.name.strip()
    if db.query(models.Committee.id).filter(models.Committee.name.ilike(name), models.Committee.id != committee_id).first():
        raise HTTPException(status_code=409, detail="A committee with this name already exists")
    # An inactive committee may keep a chair who has since left; only a newly chosen chair must be current.
    chair_changed = payload.chair_member_id != committee.chair_member_id
    chair = _chair(db, payload.chair_member_id, lgu_today()) if chair_changed else committee.chair
    before = f"{committee.name}; chair {committee.chair.full_name if committee.chair else 'none'}; active={bool(committee.is_active)}"
    committee.name, committee.chair_member_id, committee.is_active = name, chair.id if chair else None, payload.is_active
    db.commit()
    db.refresh(committee)
    record_audit_log(db, actor=current_user.username, action="COMMITTEE_UPDATED", target_type="Committee", target_id=str(committee.id),
                     details=f"{before} -> {name}; chair {chair.full_name if chair else 'none'}; active={bool(committee.is_active)}")
    return _committee_json(committee)
