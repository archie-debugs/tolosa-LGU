from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr, Field
import re
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from ..database import get_db
from .. import models
from ..core import get_password_hash, record_audit_log

router = APIRouter()


class RegistrationCreate(BaseModel):
    first_name: constr(min_length=1)
    middle_name: str | None = None
    last_name: constr(min_length=1)
    suffix: str | None = None

    contact_number: str | None = None
    email: str
    username: constr(min_length=3)
    password: constr(min_length=8)

    office: str | None = None
    position: str | None = None
    requested_access: str | None = None

    id_type: str | None = None
    id_number: str | None = None
    id_file_path: str | None = None

    notes: str | None = None


class ApproveRequest(BaseModel):
    final_role: constr(min_length=1)


class RejectRequest(BaseModel):
    reason: constr(min_length=1)


def _generate_registration_reference(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"REG-{year}-"
    # Simple sequence: count existing for year + 1
    like_pattern = f"{prefix}%"
    # Fetch max existing numeric suffix
    rows = db.execute(
        "SELECT registration_reference FROM registration_requests WHERE registration_reference LIKE :pat",
        {"pat": like_pattern},
    ).fetchall()
    existing = [r[0] for r in rows]
    seq = 1
    if existing:
        nums = []
        for ref in existing:
            try:
                parts = ref.split("-")
                nums.append(int(parts[-1]))
            except Exception:
                pass
        if nums:
            seq = max(nums) + 1
    return f"{prefix}{seq:04d}"


@router.post("/registration/requests", status_code=status.HTTP_201_CREATED)
def create_registration(request: RegistrationCreate, db: Session = Depends(get_db)):
    # Validate email format
    if not re.match(r"[^@]+@[^@]+\.[^@]+", request.email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    # Validate username uniqueness in users
    existing_user = db.query(models.User).filter(models.User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    # Check for existing pending registration with same username or email
    dup = (
        db.query(models.RegistrationRequest)
        .filter(models.RegistrationRequest.status == "Pending")
        .filter((models.RegistrationRequest.username == request.username) | (models.RegistrationRequest.email == str(request.email)))
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail="A pending registration for this username or email already exists")

    # Create hashed password
    hashed = get_password_hash(request.password)

    # Generate unique registration reference
    reg_ref = _generate_registration_reference(db)

    reg = models.RegistrationRequest(
        registration_reference=reg_ref,
        first_name=request.first_name,
        middle_name=request.middle_name,
        last_name=request.last_name,
        suffix=request.suffix,
        contact_number=request.contact_number,
        email=str(request.email),
        username=request.username,
        office=request.office,
        position=request.position,
        requested_access=request.requested_access,
        id_type=request.id_type,
        id_number=request.id_number,
        id_file_path=request.id_file_path,
        hashed_password=hashed,
        status="Pending",
        notes=request.notes,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)

    record_audit_log(db, actor=reg.username, action="REGISTRATION_SUBMITTED", target_type="RegistrationRequest", target_id=reg.registration_reference, details="Public registration submitted")

    return {"message": "Registration request submitted successfully", "registration_reference": reg.registration_reference, "status": reg.status}


@router.get("/registration/requests")
def list_registration_requests(db: Session = Depends(get_db)):
    rows = db.query(models.RegistrationRequest).order_by(models.RegistrationRequest.created_at.desc()).all()
    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "registration_reference": r.registration_reference,
                "applicant_name": f"{r.first_name} {r.last_name}",
                "username": r.username,
                "email": r.email,
                "office": r.office,
                "position": r.position,
                "requested_access": r.requested_access,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            }
        )
    return {"items": items}


@router.get("/registration/requests/{request_id}")
def get_registration_request(request_id: int, db: Session = Depends(get_db)):
    r = db.query(models.RegistrationRequest).filter(models.RegistrationRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Registration request not found")
    return {
        "id": r.id,
        "registration_reference": r.registration_reference,
        "first_name": r.first_name,
        "middle_name": r.middle_name,
        "last_name": r.last_name,
        "suffix": r.suffix,
        "contact_number": r.contact_number,
        "email": r.email,
        "username": r.username,
        "office": r.office,
        "position": r.position,
        "requested_access": r.requested_access,
        "id_type": r.id_type,
        "id_number": r.id_number,
        "id_file_path": r.id_file_path,
        "status": r.status,
        "rejection_reason": r.rejection_reason,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.put("/registration/requests/{request_id}/approve")
def approve_registration_request(request_id: int, payload: ApproveRequest, db: Session = Depends(get_db)):
    allowed_roles = {"Admin", "Staff", "Secretary / Vice Mayor"}
    final_role = payload.final_role.strip()
    if final_role not in allowed_roles:
        raise HTTPException(status_code=400, detail="Invalid final role")

    reg = db.query(models.RegistrationRequest).filter(models.RegistrationRequest.id == request_id).with_for_update().first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration request not found")
    if reg.status != "Pending":
        raise HTTPException(status_code=400, detail="Registration request has already been processed")

    # Check username still not taken
    existing_user = db.query(models.User).filter(models.User.username == reg.username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    # Transactional create user + update registration
    try:
        user = models.User(username=reg.username, hashed_password=reg.hashed_password, role=final_role)
        db.add(user)
        reg.status = "Approved"
        reg.reviewed_by = "system"
        reg.reviewed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        db.refresh(reg)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Approval failed: {exc}") from exc

    record_audit_log(db, actor="system", action="REGISTRATION_APPROVED", target_type="RegistrationRequest", target_id=reg.registration_reference, details=f"Approved and created user {user.username} with role {final_role}")

    return {"message": "Registration approved and user created", "username": user.username, "role": user.role}


@router.put("/registration/requests/{request_id}/reject")
def reject_registration_request(request_id: int, payload: RejectRequest, db: Session = Depends(get_db)):
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")

    reg = db.query(models.RegistrationRequest).filter(models.RegistrationRequest.id == request_id).with_for_update().first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration request not found")
    if reg.status != "Pending":
        raise HTTPException(status_code=400, detail="Registration request has already been processed")

    try:
        reg.status = "Rejected"
        reg.rejection_reason = reason
        reg.reviewed_by = "system"
        reg.reviewed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(reg)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Rejection failed: {exc}") from exc

    record_audit_log(db, actor="system", action="REGISTRATION_REJECTED", target_type="RegistrationRequest", target_id=reg.registration_reference, details=f"Rejected registration {reg.registration_reference}: {reason}")

    return {"message": "Registration rejected", "registration_reference": reg.registration_reference}
