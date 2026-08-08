from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..core import get_password_hash, verify_password, record_audit_log
from ..auth_jwt import create_access_token

router = APIRouter()


@router.post("/auth/register")
def register_user(username: str, password: str, role: str = "Admin", db: Session = Depends(get_db)):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    try:
        new_user = models.User(
            username=username,
            hashed_password=get_password_hash(password),
            role=(role or "Admin").strip() or "Admin",
            status="Active",
            is_active=True,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {exc}") from exc

    record_audit_log(
        db,
        actor=new_user.username,
        action="USER_REGISTERED",
        target_type="User",
        target_id=str(new_user.id),
        details=f"Created admin account for {new_user.username}",
    )

    return {"message": "User registered successfully", "username": new_user.username}


@router.post("/auth/login")
def login_user(username: str, password: str, db: Session = Depends(get_db)):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if getattr(user, "status", "Active") == "Pending":
        raise HTTPException(status_code=403, detail="Your account is awaiting administrator approval.")
    if getattr(user, "status", "Active") == "Rejected":
        raise HTTPException(status_code=403, detail="Your registration request has been rejected. Please contact the system administrator.")
    if getattr(user, "status", "Active") == "Inactive" or not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Your account has been deactivated.")

    record_audit_log(
        db,
        actor=user.username,
        action="USER_LOGIN",
        target_type="Auth",
        target_id=user.username,
        details="Successful login",
    )

    # create JWT access token (subject=username)
    token = create_access_token({"sub": user.username})

    return {"message": "Login successful", "username": user.username, "role": user.role or "Admin", "access_token": token, "token_type": "bearer"}
