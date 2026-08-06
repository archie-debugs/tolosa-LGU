from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models

router = APIRouter()


@router.get("/auth/users")
def list_users(db: Session = Depends(get_db)):
    rows = db.query(models.User).order_by(models.User.id.asc()).all()
    items = []
    for user in rows:
        items.append(
            {
                "id": user.id,
                "username": user.username,
                "role": user.role or "Admin",
                "full_name": user.username,
                "status": "Active",
                "created_at": None,
            }
        )
    return {"items": items}


@router.put("/auth/users/{username}/role")
def update_user_role(username: str, role: str, db: Session = Depends(get_db)):
    allowed_roles = {"Admin", "Secretary / Vice Mayor", "Staff"}
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


@router.delete("/auth/users/{username}")
def delete_user(username: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return {"message": "User deleted", "username": username}
