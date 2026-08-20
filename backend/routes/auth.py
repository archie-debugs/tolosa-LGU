from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..core import (
    get_password_hash,
    verify_password,
    record_audit_log,
    get_current_admin_user,
    normalize_user_role,
    normalize_permissions,
    get_default_permissions_for_role,
)
from ..auth_jwt import create_access_token, create_refresh_token, decode_refresh_token

router = APIRouter()


@router.post("/auth/register")
async def register_user(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user),
):
    # Accept JSON body (preferred) or fall back to query/form parameters for backward compatibility.
    try:
        data = await request.json()
        if not isinstance(data, dict):
            data = {}
    except Exception:
        # No JSON body provided; fall back to query params / form data
        data = dict(request.query_params)

    username = data.get("username")
    password = data.get("password")
    full_name = data.get("full_name")
    email = data.get("email")
    role = data.get("role", "Super Administrator")
    permissions = data.get("permissions")

    if not username or not password or not full_name or not email:
        raise HTTPException(status_code=400, detail="Full name, email, username, and password are required")

    normalized_role = normalize_user_role(role)
    if normalized_role not in {"Super Administrator", "Employee", "SB Member"}:
        raise HTTPException(status_code=400, detail="Invalid role")

    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail=f"Username '{username}' already exists")

    permission_list = []
    if permissions:
        permission_list = list(normalize_permissions(permissions))
    if not permission_list:
        permission_list = get_default_permissions_for_role(normalized_role)

    try:
        new_user = models.User(
            username=username,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            email=email,
            role=normalized_role,
            permissions=str(permission_list),
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
        actor=current_admin.username,
        action="USER_REGISTERED",
        target_type="User",
        target_id=str(new_user.id),
        details=f"Super Administrator {current_admin.username} created account {new_user.username} for role {normalized_role}",
    )

    return {
        "message": "User registered successfully",
        "id": new_user.id,
        "username": new_user.username,
        "full_name": new_user.full_name,
        "email": new_user.email,
        "role": new_user.role,
        "permissions": permission_list,
    }


@router.get("/auth/users")
def list_users(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user),
):
    users = db.query(models.User).order_by(models.User.id.asc()).all()
    return [
        {
            "id": user.id,
            "full_name": getattr(user, "full_name", None) or user.username,
            "username": user.username,
            "email": getattr(user, "email", None) or None,
            "role": normalize_user_role(user.role),
            "status": getattr(user, "status", "Active"),
            "permissions": sorted(list(normalize_permissions(getattr(user, "permissions", None)))),
            "last_login": None,
            "created": user.created_at.isoformat() if user.created_at else None,
        }
        for user in users
    ]


@router.post("/auth/login")
def login_user(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        record_audit_log(db, actor=username or "unknown", action="FAILED_LOGIN", target_type="Auth", target_id=username or "unknown", details="Failed login attempt")
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

    access_token = create_access_token({"sub": user.username})
    refresh_token = create_refresh_token({"sub": user.username})

    role = normalize_user_role(user.role)
    permissions = list(normalize_permissions(getattr(user, "permissions", None)))
    if not permissions:
        permissions = get_default_permissions_for_role(role)

    return {
        "message": "Login successful",
        "username": user.username,
        "role": role,
        "permissions": permissions,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/auth/refresh")
def refresh_access_token(
    refresh_token: str = Form(...),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token is required")

    payload = decode_refresh_token(refresh_token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Refresh token invalid")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(status_code=401, detail="User no longer active")

    return {
        "access_token": create_access_token({"sub": user.username}),
        "refresh_token": create_refresh_token({"sub": user.username}),
        "token_type": "bearer",
    }
