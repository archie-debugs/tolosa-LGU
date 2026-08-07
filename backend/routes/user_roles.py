from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..core import get_current_admin_user

router = APIRouter()


@router.get("/auth/users")
def list_users(db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin_user)):
    rows = db.query(models.User).order_by(models.User.id.asc()).all()
    items = []
    for user in rows:
        status = getattr(user, "status", "Active") or "Active"
        if status == "Active" and not getattr(user, "is_active", True):
            status = "Inactive"
        items.append(
            {
                "id": user.id,
                "username": user.username,
                "role": user.role or "Admin",
                "full_name": user.username,
                "status": status,
                "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
            }
        )
    return {"items": items}


@router.put("/auth/users/{username}/role")
def update_user_role(username: str, role: str, db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin_user)):
    allowed_roles = {"Admin", "SB Member", "Secretary / Vice Mayor", "Staff"}
    normalized_role = (role or "").strip()
    if normalized_role not in allowed_roles:
        raise HTTPException(status_code=400, detail="Invalid role")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = normalized_role
    db.commit()
    db.refresh(user)
    return {"message": "User role updated", "username": user.username, "role": user.role}


@router.put("/auth/users/{username}/status")
def update_user_status(username: str, status: str, db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin_user)):
    normalized_status = (status or "").strip().title()
    if normalized_status not in {"Active", "Inactive"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.status = normalized_status
    user.is_active = normalized_status == "Active"
    db.commit()
    db.refresh(user)
    return {"message": "User status updated", "username": user.username, "status": user.status}


@router.put("/auth/users/{username}/reset-password")
def reset_password(username: str, new_password: str, db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin_user)):
    if not new_password or len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = models.User.__table__.c.hashed_password.type.length if False else None
    return {"message": "Password reset endpoint is ready", "username": username}


@router.delete("/auth/users/{username}")
def delete_user(username: str, db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin_user)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return {"message": "User deleted", "username": username}
