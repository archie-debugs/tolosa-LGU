from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth_jwt import get_current_user
from ..core import normalize_user_role, record_audit_log, require_permission
from ..database import get_db

router = APIRouter(prefix="/offices", tags=["offices"])


def _require_super_admin(user):
    if normalize_user_role(getattr(user, "role", None)) != "Super Administrator":
        raise HTTPException(status_code=403, detail="Super Administrator access required")


def _serialize_office(office, user_count=0):
    return {
        "id": office.id,
        "name": office.name,
        "office_name": office.name,
        "office_code": office.office_code,
        "is_active": bool(office.is_active),
        "user_count": user_count,
        "created_at": office.created_at.isoformat() if office.created_at else None,
        "updated_at": office.updated_at.isoformat() if office.updated_at else None,
    }


def _normalized_values(payload):
    name = payload.name.strip()
    office_code = payload.office_code.strip().upper()
    if not name or not office_code:
        raise HTTPException(status_code=400, detail="Office name and office code are required")
    return name, office_code


def _ensure_unique(db, name, office_code, office_id=None):
    query = db.query(models.Office).filter(
        func.lower(models.Office.name) == name.lower(),
    )
    if office_id is not None:
        query = query.filter(models.Office.id != office_id)
    if query.first():
        raise HTTPException(status_code=409, detail="An office with this name already exists")

    query = db.query(models.Office).filter(
        func.lower(models.Office.office_code) == office_code.lower(),
    )
    if office_id is not None:
        query = query.filter(models.Office.id != office_id)
    if query.first():
        raise HTTPException(status_code=409, detail="Office code already exists")


def _find_office(db, office_id):
    office = db.query(models.Office).filter(models.Office.id == office_id).first()
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")
    return office


@router.get("/available-for-handoff")
def list_available_offices_for_handoff(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if getattr(current_user, "office_id", None) is None:
        raise HTTPException(status_code=403, detail="Office assignment required")
    require_permission(current_user, "pass_office_documents")
    if normalize_user_role(getattr(current_user, "role", None)) not in {"Employee", "Super Administrator"}:
        raise HTTPException(status_code=403, detail="Employee or Super Administrator access required")

    offices = (
        db.query(models.Office)
        .filter(models.Office.is_active.is_(True))
        .filter(models.Office.id != current_user.office_id)
        .order_by(models.Office.name.asc())
        .all()
    )
    return [{
        "id": office.id,
        "name": office.name,
        "office_code": office.office_code,
    } for office in offices]


@router.get("")
def list_offices(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    query = db.query(models.Office)
    if active_only:
        query = query.filter(models.Office.is_active.is_(True))
    offices = query.order_by(models.Office.name.asc()).all()
    counts = dict(
        db.query(models.User.office_id, func.count(models.User.id))
        .filter(models.User.office_id.isnot(None))
        .group_by(models.User.office_id)
        .all()
    )
    return [_serialize_office(office, counts.get(office.id, 0)) for office in offices]


@router.get("/{office_id}")
def get_office(
    office_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    office = _find_office(db, office_id)
    user_count = db.query(models.User).filter(models.User.office_id == office.id).count()
    return _serialize_office(office, user_count)


@router.get("/{office_id}/users")
def list_office_users(
    office_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    office = _find_office(db, office_id)
    users = (
        db.query(models.User)
        .filter(models.User.office_id == office.id)
        .order_by(models.User.username.asc())
        .all()
    )
    return [
        {
            "id": user.id,
            "full_name": user.full_name or user.username,
            "username": user.username,
            "email": user.email,
            "role": normalize_user_role(user.role),
            "status": user.status,
        }
        for user in users
    ]


@router.post("")
def create_office(
    payload: schemas.OfficeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    name, office_code = _normalized_values(payload)
    _ensure_unique(db, name, office_code)
    office = models.Office(name=name, office_code=office_code, is_active=payload.is_active)
    db.add(office)
    try:
        db.commit()
        db.refresh(office)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Office name or code already exists") from exc
    record_audit_log(
        db,
        actor=current_user.username,
        action="OFFICE_CREATED",
        target_type="Office",
        target_id=str(office.id),
        details=f"Created office {office.name} ({office.office_code})",
    )
    return _serialize_office(office)


@router.put("/{office_id}")
def update_office(
    office_id: int,
    payload: schemas.OfficeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    office = _find_office(db, office_id)
    name, office_code = _normalized_values(payload)
    _ensure_unique(db, name, office_code, office_id)
    previous = (office.name, office.office_code, bool(office.is_active))
    office.name = name
    office.office_code = office_code
    office.is_active = payload.is_active
    try:
        db.commit()
        db.refresh(office)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Office name or code already exists") from exc
    record_audit_log(
        db,
        actor=current_user.username,
        action="OFFICE_UPDATED",
        target_type="Office",
        target_id=str(office.id),
        details=(
            f"Updated office {office.id}: name={previous[0]}->{office.name}, "
            f"code={previous[1]}->{office.office_code}, active={previous[2]}->{bool(office.is_active)}"
        ),
    )
    user_count = db.query(models.User).filter(models.User.office_id == office.id).count()
    return _serialize_office(office, user_count)