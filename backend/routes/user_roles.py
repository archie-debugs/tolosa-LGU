from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db

router = APIRouter()


@router.get("/auth/users")
def list_users(db: Session = Depends(get_db)):
    # Minimal stub: return empty list so frontend shows placeholder when backend has no users
    return {"items": []}


@router.put("/auth/users/{username}/role")
def update_user_role(username: str, role: str, db: Session = Depends(get_db)):
    # Not implemented in stub backend
    raise HTTPException(status_code=501, detail="User role updates are not available in this build")


@router.delete("/auth/users/{username}")
def delete_user(username: str, db: Session = Depends(get_db)):
    # Not implemented in stub backend
    raise HTTPException(status_code=501, detail="User deletion is not available in this build")
