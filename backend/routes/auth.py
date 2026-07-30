from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..core import get_password_hash, verify_password, record_audit_log, create_scanner_session

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
            role=role.strip() or "Admin",
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


@router.get("/auth/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.id.asc()).all()
    return {
        "items": [
            {
                "id": user.id,
                "username": user.username,
                "role": user.role or "Admin",
            }
            for user in users
        ]
    }


@router.put("/auth/users/{username}/role")
def update_user_role(username: str, role: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role.strip() or "Admin"
    db.commit()
    db.refresh(user)

    record_audit_log(
        db,
        actor="system",
        action="USER_ROLE_UPDATED",
        target_type="User",
        target_id=str(user.id),
        details=f"Updated {user.username} role to {user.role}",
    )

    return {"message": "User role updated", "username": user.username, "role": user.role}


@router.delete("/auth/users/{username}")
def delete_user(username: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = user.id
    db.delete(user)
    db.commit()

    record_audit_log(
        db,
        actor="system",
        action="USER_DELETED",
        target_type="User",
        target_id=str(user_id),
        details=f"Deleted user {username}",
    )

    return {"message": "User deleted", "username": username}


@router.post("/auth/login")
def login_user(username: str, password: str, db: Session = Depends(get_db)):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    record_audit_log(
        db,
        actor=user.username,
        action="USER_LOGIN",
        target_type="Auth",
        target_id=user.username,
        details="Successful login",
    )

    return {"message": "Login successful", "username": user.username}


@router.post("/auth/scanner/login")
def scanner_login(username: str, password: str, db: Session = Depends(get_db)):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    scanner_session = create_scanner_session(user.username, user.role or "Admin")

    record_audit_log(
        db,
        actor=user.username,
        action="SCANNER_LOGIN",
        target_type="Auth",
        target_id=user.username,
        details="Scanner session created",
    )

    return {
        "message": "Scanner login successful",
        "username": user.username,
        "role": user.role or "Admin",
        **scanner_session,
    }


@router.post("/auth/scanner/logout")
def scanner_logout(token: str):
    from ..core import scanner_sessions
    scanner_sessions.pop(token, None)
    return {"message": "Scanner session cleared"}
