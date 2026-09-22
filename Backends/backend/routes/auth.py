import uuid
from datetime import timedelta
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from ..database import get_db
from .. import models
from ..core import (
    get_password_hash,
    verify_password,
    record_audit_log,
    get_current_admin_user,
    normalize_user_role,
    normalize_permissions,
    validate_permissions,
    get_default_permissions_for_role,
    require_permission,
    require_user_management_permission,
    get_current_user_for_user_management,
)
from ..auth_jwt import create_access_token, create_refresh_token, decode_refresh_token

router = APIRouter()


class UserUpdate(BaseModel):
    full_name: str
    username: str
    email: str
    office_id: int | None = None
    role: str
    status: str
    permissions: list[str] = []


class PasswordReset(BaseModel):
    new_password: str
    confirm_password: str


def validate_reset_password(password: str) -> str:
    normalized = password or ""
    if len(normalized) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    if not normalized.strip():
        raise HTTPException(status_code=400, detail="Password cannot be blank")
    return normalized


@router.post("/auth/register")
async def register_user(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("create_users")),
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
    office_id = data.get("office_id")
    role = data.get("role", "Employee")
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
        permission_list = validate_permissions(permissions)
    if not permission_list:
        permission_list = get_default_permissions_for_role(normalized_role)
    if normalized_role == "Super Administrator":
        if normalize_user_role(current_admin.role) != "Super Administrator":
            raise HTTPException(status_code=403, detail="Only a Super Administrator can create a Super Administrator")
        permission_list = ["*"]

    office = None
    if office_id not in (None, ""):
        try:
            office = db.query(models.Office).filter(models.Office.id == int(office_id)).first()
        except (TypeError, ValueError):
            office = None
        if not office:
            raise HTTPException(status_code=400, detail="Office not found")

    try:
        new_user = models.User(
            username=username,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            email=email,
            office_id=office.id if office else None,
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
        details=f"{current_admin.username} created account {new_user.username} for role {normalized_role}",
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
    current_admin: models.User = Depends(require_user_management_permission("view_users")),
):
    users = db.query(models.User).order_by(models.User.id.asc()).all()
    return [
        {
            "id": user.id,
            "full_name": getattr(user, "full_name", None) or user.username,
            "username": user.username,
            "email": getattr(user, "email", None) or None,
            "office_id": getattr(user, "office_id", None),
            "department": user.office.name if getattr(user, "office", None) else None,
            "role": normalize_user_role(user.role),
            "status": getattr(user, "status", "Active"),
            "permissions": sorted(list(normalize_permissions(getattr(user, "permissions", None)))),
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "created": user.created_at.isoformat() if user.created_at else None,
        }
        for user in users
    ]


@router.get("/auth/roles")
def list_roles(
    current_admin: models.User = Depends(require_user_management_permission("view_users")),
):
    from ..core import ROLE_DEFINITIONS

    return [
        {"name": role, "permissions": list(permissions)}
        for role, permissions in ROLE_DEFINITIONS.items()
    ]


@router.get("/auth/offices")
def list_user_offices(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("view_users")),
):
    return [
        {"id": office.id, "name": office.name}
        for office in db.query(models.Office).order_by(models.Office.name.asc()).all()
    ]


@router.put("/auth/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("edit_users")),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    normalized_role = normalize_user_role(payload.role)
    target_is_super_admin = normalize_user_role(user.role) == "Super Administrator"
    if target_is_super_admin and normalize_user_role(current_admin.role) != "Super Administrator":
        raise HTTPException(status_code=403, detail="Only a Super Administrator can modify a Super Administrator account")
    if target_is_super_admin and normalized_role != "Super Administrator":
        raise HTTPException(status_code=400, detail="A Super Administrator role cannot be removed through user editing")
    if not target_is_super_admin and normalized_role not in {"Employee", "SB Member"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    normalized_status = payload.status.strip().capitalize()
    if normalized_status not in {"Active", "Inactive"}:
        raise HTTPException(status_code=400, detail="Status must be Active or Inactive")
    if not payload.username.strip() or not payload.full_name.strip() or not payload.email.strip():
        raise HTTPException(status_code=400, detail="Full name, email, and username are required")

    if normalized_role != normalize_user_role(user.role):
        require_permission(current_admin, "assign_roles")
    requested_permissions = validate_permissions(payload.permissions)
    if not target_is_super_admin and set(requested_permissions) != normalize_permissions(user.permissions):
        require_permission(current_admin, "manage_permissions")

    office = None
    if payload.office_id is not None:
        office = db.query(models.Office).filter(models.Office.id == payload.office_id).first()
        if not office:
            raise HTTPException(status_code=400, detail="Office not found")

    duplicate = db.query(models.User).filter(models.User.username == payload.username.strip(), models.User.id != user_id).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Username already exists")

    previous_role = normalize_user_role(user.role)
    previous_permissions = normalize_permissions(user.permissions)
    user.full_name = payload.full_name.strip()
    user.username = payload.username.strip()
    user.email = payload.email.strip()
    user.office_id = office.id if office else None
    user.role = normalized_role
    user.permissions = str(["*"] if target_is_super_admin else requested_permissions)
    user.status = normalized_status
    user.is_active = normalized_status == "Active"
    db.commit()
    if normalized_role != previous_role:
        record_audit_log(
            db,
            actor=current_admin.username,
            action="USER_ROLE_CHANGED",
            target_type="User",
            target_id=str(user.id),
            details=f"{current_admin.username} changed {user.username} role from {previous_role} to {normalized_role}",
        )
    if set(requested_permissions) != previous_permissions and not target_is_super_admin:
        record_audit_log(
            db,
            actor=current_admin.username,
            action="USER_PERMISSIONS_CHANGED",
            target_type="User",
            target_id=str(user.id),
            details=f"{current_admin.username} changed permissions for {user.username}",
        )
    record_audit_log(
        db,
        actor=current_admin.username,
        action="USER_UPDATED",
        target_type="User",
        target_id=str(user.id),
        details=f"{current_admin.username} updated account {user.username}",
    )
    return {"message": "User updated successfully", "id": user.id}


@router.delete("/auth/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("delete_users")),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if normalize_user_role(user.role) == "Super Administrator":
        if normalize_user_role(current_admin.role) != "Super Administrator":
            raise HTTPException(status_code=403, detail="Only a Super Administrator can delete a Super Administrator account")
        active_super_admins = db.query(models.User).filter(
            models.User.role == "Super Administrator",
            models.User.is_active.is_(True),
            models.User.status == "Active",
        ).count()
        if user.is_active and user.status == "Active" and active_super_admins <= 1:
            raise HTTPException(status_code=400, detail="The final active Super Administrator cannot be deleted")

    username = user.username
    db.query(models.UserSession).filter(models.UserSession.user_id == user_id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()
    record_audit_log(
        db,
        actor=current_admin.username,
        action="USER_DELETED",
        target_type="User",
        target_id=str(user_id),
        details=f"{current_admin.username} deleted account {username}",
    )
    return {"message": "User deleted successfully", "id": user_id}


@router.post("/auth/users/{user_id}/status")
def update_user_status(
    user_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_user_for_user_management),
):
    normalized_status = status.strip().capitalize()
    if normalized_status not in {"Active", "Inactive"}:
        raise HTTPException(status_code=400, detail="Status must be Active or Inactive")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    require_permission(current_admin, "activate_users" if normalized_status == "Active" else "deactivate_users")
    if normalize_user_role(user.role) == "Super Administrator":
        if normalize_user_role(current_admin.role) != "Super Administrator":
            raise HTTPException(status_code=403, detail="Only a Super Administrator can modify a Super Administrator account")
    if normalize_user_role(user.role) == "Super Administrator" and normalized_status == "Inactive":
        active_super_admins = db.query(models.User).filter(
            models.User.role == "Super Administrator",
            models.User.is_active.is_(True),
            models.User.status == "Active",
        ).count()
        if user.status == "Active" and user.is_active and active_super_admins <= 1:
            raise HTTPException(status_code=400, detail="The final active Super Administrator cannot be deactivated")

    user.status = normalized_status
    user.is_active = normalized_status == "Active"
    db.commit()
    record_audit_log(
        db,
        actor=current_admin.username,
        action=f"USER_{normalized_status.upper()}",
        target_type="User",
        target_id=str(user.id),
        details=f"{current_admin.username} changed {user.username} status to {normalized_status}",
    )
    return {"message": f"User {normalized_status.lower()} successfully", "id": user.id, "status": normalized_status}


@router.post("/auth/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: PasswordReset,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("reset_passwords")),
):
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    password = validate_reset_password(payload.new_password)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if normalize_user_role(user.role) == "Super Administrator" and normalize_user_role(current_admin.role) != "Super Administrator":
        raise HTTPException(status_code=403, detail="Only a Super Administrator can reset a Super Administrator password")

    user.hashed_password = get_password_hash(password)
    db.commit()
    record_audit_log(
        db,
        actor=current_admin.username,
        action="USER_PASSWORD_RESET",
        target_type="User",
        target_id=str(user.id),
        details=f"{current_admin.username} reset the password for account {user.username}",
    )
    return {"message": "User password reset successfully", "id": user.id}


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
    # This represents the user's most recent authenticated activity.
    # We intentionally update it on both credentialed login and refresh so it tracks
    # the latest time the user successfully re-established trust, not merely the
    # first time they ever signed in.
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    session_id = str(uuid.uuid4())
    session_now = datetime.now(timezone.utc)
    db.add(models.UserSession(
        session_id=session_id,
        user_id=user.id,
        created_at=session_now,
        last_activity=session_now,
        expires_at=session_now + timedelta(days=7),
    ))
    db.commit()
    access_token = create_access_token({"sub": user.username, "session_id": session_id})
    refresh_token = create_refresh_token({"sub": user.username, "session_id": session_id})

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
    session_id = payload.get("session_id")
    session = db.query(models.UserSession).filter(
        models.UserSession.session_id == session_id,
        models.UserSession.user_id == user.id if user else False,
    ).first() if session_id else None
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session and session.expires_at and session.expires_at.tzinfo is None else (session.expires_at if session else None)
    if session_id and (not session or session.revoked_at or not expires_at or expires_at <= datetime.now(timezone.utc)):
        raise HTTPException(status_code=401, detail="Session is no longer active")
    if not user or not getattr(user, "is_active", True) or getattr(user, "status", "Active") != "Active":
        raise HTTPException(status_code=401, detail="User no longer active")

    # Refresh is treated as a successful authenticated activity event. This keeps the
    # field aligned with the current rule: last authenticated activity, including
    # re-validating a persisted session.
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    role = normalize_user_role(user.role)
    permissions = list(normalize_permissions(getattr(user, "permissions", None)))
    if not permissions:
        permissions = get_default_permissions_for_role(role)

    return {
        "access_token": create_access_token({"sub": user.username, "session_id": session_id} if session_id else {"sub": user.username}),
        "refresh_token": create_refresh_token({"sub": user.username, "session_id": session_id} if session_id else {"sub": user.username}),
        "username": user.username,
        "role": role,
        "permissions": permissions,
        "token_type": "bearer",
    }


@router.post("/auth/logout")
def logout_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    from ..auth_jwt import decode_access_token

    payload = decode_access_token(authorization.split(" ", 1)[1].strip())
    session_id = payload.get("session_id")
    username = payload.get("sub")
    if session_id:
        session = db.query(models.UserSession).filter(models.UserSession.session_id == session_id).first()
        if session and not session.revoked_at:
            session.revoked_at = datetime.now(timezone.utc)
            session.revoke_reason = "logout"
            db.commit()
            record_audit_log(db, actor=username or "unknown", action="SESSION_REVOKED", target_type="Session", target_id=session_id, details="User logged out")
    return {"message": "Logged out successfully"}


@router.get("/auth/sessions")
def list_active_sessions(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user),
):
    now = datetime.now(timezone.utc)
    sessions = db.query(models.UserSession).filter(
        models.UserSession.revoked_at.is_(None),
        models.UserSession.expires_at > now,
    ).order_by(models.UserSession.last_activity.desc()).all()
    return [{
        "id": session.id,
        "session_id": session.session_id,
        "username": session.user.username if session.user else None,
        "created_at": session.created_at.isoformat(),
        "last_activity": session.last_activity.isoformat(),
        "expires_at": session.expires_at.isoformat(),
    } for session in sessions]


@router.post("/auth/sessions/{session_id}/revoke")
def revoke_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user),
):
    session = db.query(models.UserSession).filter(models.UserSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.revoked_at:
        session.revoked_at = datetime.now(timezone.utc)
        session.revoke_reason = "administrator_revocation"
        db.commit()
        record_audit_log(db, actor=current_admin.username, action="SESSION_REVOKED", target_type="Session", target_id=session_id, details="Administrator revoked session")
    return {"message": "Session revoked"}
