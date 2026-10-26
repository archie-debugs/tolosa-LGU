import base64
import io
import re
import uuid
from datetime import timedelta

import qrcode
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from ..database import get_db
from .. import login_lockout, models, two_step
from ..core import (
    get_password_hash,
    verify_password,
    record_audit_log,
    get_current_admin_user,
    normalize_user_role,
    normalize_permissions,
    validate_permissions,
    get_default_permissions_for_role,
    OFFICE_WORKFLOW_PERMISSIONS,
    require_permission,
    require_user_management_permission,
)
from ..authentication import get_current_user, get_current_user_for_user_management, oauth2_scheme
from ..auth_jwt import create_access_token, create_refresh_token, decode_access_token, decode_refresh_token
from .council import POSITIONS as COUNCIL_POSITIONS

router = APIRouter()


class UserUpdate(BaseModel):
    full_name: str
    username: str
    email: str
    office_id: int | None = None
    role: str
    status: str
    permissions: list[str] = []
    sb_position: str | None = None


class PasswordReset(BaseModel):
    new_password: str
    confirm_password: str


class ProfileUpdate(BaseModel):
    full_name: str = ""
    email: str = ""


def _sb_position(role, position):
    """The SB position an account keeps: only SB Members have one. Accounts made before it was asked have none."""
    position = (position or "").strip()
    if role != "SB Member" or not position:
        return None
    if position not in COUNCIL_POSITIONS:
        raise HTTPException(status_code=400, detail=f"SB position must be one of: {', '.join(COUNCIL_POSITIONS)}")
    return position


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


def validate_reset_password(password: str) -> str:
    normalized = password or ""
    if len(normalized) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    if not normalized.strip():
        raise HTTPException(status_code=400, detail="Password cannot be blank")
    return normalized


def _revoke_user_sessions(db: Session, user_id: int, reason: str) -> None:
    db.query(models.UserSession).filter(
        models.UserSession.user_id == user_id,
        models.UserSession.revoked_at.is_(None),
    ).update({"revoked_at": datetime.now(timezone.utc), "revoke_reason": reason}, synchronize_session=False)


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
    sb_position = _sb_position(normalized_role, data.get("sb_position"))

    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail=f"Username '{username}' already exists")

    office_assignment_requested = office_id not in (None, "")
    if "permissions" in data:
        permission_list = validate_permissions(permissions)
    elif normalized_role == "Employee" and office_assignment_requested:
        permission_list = sorted(OFFICE_WORKFLOW_PERMISSIONS)
    else:
        permission_list = get_default_permissions_for_role(normalized_role)
    if normalized_role == "Super Administrator":
        if normalize_user_role(current_admin.role) != "Super Administrator":
            raise HTTPException(status_code=403, detail="Only a Super Administrator can create a Super Administrator")
        permission_list = ["*"]

    office = None
    if office_id not in (None, ""):
        if normalize_user_role(current_admin.role) != "Super Administrator":
            raise HTTPException(status_code=403, detail="Only a Super Administrator can assign an office")
        try:
            office = db.query(models.Office).filter(models.Office.id == int(office_id)).first()
        except (TypeError, ValueError):
            office = None
        if not office or not office.is_active:
            raise HTTPException(status_code=400, detail="An active office is required")

    if normalized_role == "Employee" and office is not None:
        # Office employees get only office-workflow permissions, limited to those the admin chose.
        permission_list = sorted(set(permission_list) & OFFICE_WORKFLOW_PERMISSIONS)

    try:
        new_user = models.User(
            username=username,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            email=email,
            office_id=office.id if office else None,
            role=normalized_role,
            sb_position=sb_position,
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
    if new_user.office_id is not None:
        record_audit_log(
            db,
            actor=current_admin.username,
            action="USER_OFFICE_ASSIGNED",
            target_type="User",
            target_id=str(new_user.id),
            details=f"{current_admin.username} assigned {new_user.username} to office {new_user.office_id}",
        )

    return {
        "message": "User registered successfully",
        "id": new_user.id,
        "username": new_user.username,
        "full_name": new_user.full_name,
        "email": new_user.email,
        "role": new_user.role,
        "office_id": new_user.office_id,
        "sb_position": new_user.sb_position,
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
            "sb_position": user.sb_position,
            "status": getattr(user, "status", "Active"),
            "locked": login_lockout.is_username_locked(db, user.username),
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
        {"id": office.id, "name": office.name, "office_code": office.office_code}
        for office in db.query(models.Office)
        .filter(models.Office.is_active.is_(True))
        .order_by(models.Office.name.asc())
        .all()
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

    supplied_fields = getattr(payload, "model_fields_set", None)
    if supplied_fields is None:
        supplied_fields = getattr(payload, "__fields_set__", set())
    # Older clients don't send sb_position; an SB Member then keeps the one on file.
    sb_position = _sb_position(normalized_role, payload.sb_position if "sb_position" in supplied_fields else user.sb_position)

    if normalized_role != normalize_user_role(user.role):
        require_permission(current_admin, "assign_roles")
    requested_permissions = validate_permissions(payload.permissions)
    if not target_is_super_admin and set(requested_permissions) != normalize_permissions(user.permissions):
        require_permission(current_admin, "manage_permissions")

    office_id_supplied = "office_id" in supplied_fields
    next_office_id = payload.office_id if office_id_supplied else user.office_id
    office_changed = next_office_id != user.office_id
    office = user.office if not office_changed else None
    if office_changed:
        if normalize_user_role(current_admin.role) != "Super Administrator":
            raise HTTPException(status_code=403, detail="Only a Super Administrator can change an office assignment")
        if next_office_id is not None:
            office = db.query(models.Office).filter(models.Office.id == next_office_id).first()
            if not office:
                raise HTTPException(status_code=400, detail="Office not found")
            if not office.is_active:
                raise HTTPException(status_code=400, detail="Inactive offices cannot be assigned")

    duplicate = db.query(models.User).filter(models.User.username == payload.username.strip(), models.User.id != user_id).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Username already exists")

    previous_role = normalize_user_role(user.role)
    previous_permissions = normalize_permissions(user.permissions)
    previous_office_id = user.office_id
    user.full_name = payload.full_name.strip()
    user.username = payload.username.strip()
    user.email = payload.email.strip()
    user.office_id = office.id if office else None
    user.role = normalized_role
    user.sb_position = sb_position
    user.permissions = str(["*"] if target_is_super_admin else requested_permissions)
    user.status = normalized_status
    user.is_active = normalized_status == "Active"
    if not user.is_active:
        _revoke_user_sessions(db, user.id, "account_deactivated")
    db.commit()
    if previous_office_id != user.office_id:
        record_audit_log(
            db,
            actor=current_admin.username,
            action="USER_OFFICE_CHANGED",
            target_type="User",
            target_id=str(user.id),
            details=f"{current_admin.username} changed {user.username} office from {previous_office_id} to {user.office_id}",
        )
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
    if not user.is_active:
        _revoke_user_sessions(db, user.id, "account_deactivated")
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


def _my_account(user: models.User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": getattr(user, "full_name", None) or None,
        "email": getattr(user, "email", None) or None,
        "role": normalize_user_role(user.role),
        "office": user.office.name if getattr(user, "office", None) else None,
        "status": getattr(user, "status", None) or "Active",
        "permissions": sorted(normalize_permissions(getattr(user, "permissions", None))),
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "two_step_enabled": bool(getattr(user, "totp_secret", None)),
        "two_step_recovery_codes_left": two_step.recovery_codes_left(getattr(user, "totp_recovery_codes", None)),
    }


@router.get("/auth/me")
def read_my_account(current_user: models.User = Depends(get_current_user)):
    """The signed-in account, for the profile menu and My Account."""
    return _my_account(current_user)


@router.put("/auth/me")
def update_my_account(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Change your own name and email. Username, role, office and permissions stay with the Super Admin."""
    full_name = (payload.full_name or "").strip()
    email = (payload.email or "").strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Full name is required.")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")

    user = db.query(models.User).filter(models.User.id == current_user.id).one()
    changed = [field for field, value in (("full_name", full_name), ("email", email)) if getattr(user, field) != value]
    user.full_name = full_name
    user.email = email
    db.commit()
    db.refresh(user)
    if changed:
        record_audit_log(
            db,
            actor=user.username,
            action="PROFILE_UPDATED",
            target_type="User",
            target_id=str(user.id),
            details=f"{user.username} updated their own profile; fields={','.join(changed)}",
        )
    return _my_account(user)


@router.post("/auth/me/password")
def change_my_password(
    payload: PasswordChange,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Change your own password; your other sessions are signed out, this one stays."""
    if not verify_password(payload.current_password or "", current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Your current password is incorrect.")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="The new passwords do not match.")
    password = validate_reset_password(payload.new_password)
    if verify_password(password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Choose a password different from your current one.")

    user = db.query(models.User).filter(models.User.id == current_user.id).one()
    user.hashed_password = get_password_hash(password)
    this_session = decode_access_token(token).get("session_id")
    db.query(models.UserSession).filter(
        models.UserSession.user_id == user.id,
        models.UserSession.revoked_at.is_(None),
        models.UserSession.session_id != this_session,
    ).update({"revoked_at": datetime.now(timezone.utc), "revoke_reason": "password changed"}, synchronize_session=False)
    record_audit_log(
        db,
        actor=user.username,
        action="PASSWORD_CHANGED",
        target_type="User",
        target_id=str(user.id),
        details=f"{user.username} changed their password; other sessions were signed out",
    )
    return {"message": "Your password has been changed."}


@router.post("/auth/users/{user_id}/unlock")
def unlock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    record_audit_log(
        db,
        actor=current_admin.username,
        action="ACCOUNT_UNLOCKED",
        target_type="Auth",
        target_id=user.username,
        details=f"{current_admin.username} cleared the login lockout for {user.username}",
    )
    return {"message": "Login lockout cleared", "id": user.id}


TWO_STEP_HEADER = {"X-Two-Step": "required"}
TWO_STEP_ASK = "Enter the 6-digit code from your authenticator app."
TWO_STEP_WRONG = "That code is not right. Check your authenticator app and try again."


def _record_failed_login(db, username, details):
    record_audit_log(db, actor=username, action="FAILED_LOGIN", target_type="Auth", target_id=username, details=details)
    if login_lockout.recent_failure_count(db, username) == login_lockout.LOGIN_MAX_FAILURES:
        record_audit_log(
            db,
            actor="System",
            action="ACCOUNT_LOCKED",
            target_type="Auth",
            target_id=username,
            details=f"Locked for {login_lockout.LOGIN_LOCKOUT_MINUTES} minutes after {login_lockout.LOGIN_MAX_FAILURES} failed logins",
        )


def _accept_code(db, user, code):
    """Use up `code` (authenticator or recovery) for `user`; False if it is wrong or already used."""
    step = two_step.matching_step(user.totp_secret, code, user.totp_last_step)
    if step is not None:
        user.totp_last_step = step
        return True
    if two_step.looks_like_recovery_code(code):
        remaining = two_step.use_recovery_code(user.totp_recovery_codes, code)
        if remaining is not None:
            user.totp_recovery_codes = remaining
            record_audit_log(
                db, actor=user.username, action="TWO_STEP_RECOVERY_CODE_USED", target_type="Auth", target_id=user.username,
                details=f"Recovery code used; {two_step.recovery_codes_left(remaining)} left", commit=False,
            )
            return True
    return False


def _check_login_code(db, user, code):
    """The second step of login: a missing code asks for one, a wrong one counts as a failed login."""
    if not (code or "").strip():
        raise HTTPException(status_code=401, detail=TWO_STEP_ASK, headers=TWO_STEP_HEADER)
    if not _accept_code(db, user, code):
        db.rollback()
        _record_failed_login(db, user.username, "Wrong two-step code")
        raise HTTPException(status_code=401, detail=TWO_STEP_WRONG, headers=TWO_STEP_HEADER)


class TwoStepCode(BaseModel):
    code: str = ""


class TwoStepOff(BaseModel):
    password: str = ""
    code: str = ""


def _require_super_admin(user):
    if normalize_user_role(user.role) != "Super Administrator":
        raise HTTPException(status_code=403, detail="Two-step login is available to Super Admins.")


@router.post("/auth/two-step/setup")
def start_two_step_setup(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """A new secret to scan; it is not used for login until /auth/two-step/enable confirms a code."""
    _require_super_admin(current_user)
    user = db.query(models.User).filter(models.User.id == current_user.id).one()
    if user.totp_secret:
        raise HTTPException(status_code=400, detail="Two-step login is already on.")
    secret = two_step.new_secret()
    user.totp_pending_secret = secret
    db.commit()
    uri = two_step.setup_uri(secret, user.username)
    buffer = io.BytesIO()
    qrcode.make(uri).save(buffer, format="PNG")
    return {"secret": secret, "uri": uri, "qr_png_base64": base64.b64encode(buffer.getvalue()).decode("ascii")}


@router.post("/auth/two-step/enable")
def enable_two_step(payload: TwoStepCode, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _require_super_admin(current_user)
    user = db.query(models.User).filter(models.User.id == current_user.id).one()
    if user.totp_secret:
        raise HTTPException(status_code=400, detail="Two-step login is already on.")
    if not user.totp_pending_secret:
        raise HTTPException(status_code=400, detail="Start the setup first.")
    step = two_step.matching_step(user.totp_pending_secret, payload.code)
    if step is None:
        raise HTTPException(status_code=400, detail=TWO_STEP_WRONG)
    codes, hashes = two_step.new_recovery_codes()
    user.totp_secret, user.totp_pending_secret = user.totp_pending_secret, None
    user.totp_last_step = step
    user.totp_enabled_at = datetime.now(timezone.utc)
    user.totp_recovery_codes = hashes
    db.commit()
    record_audit_log(db, actor=user.username, action="TWO_STEP_ENABLED", target_type="Auth", target_id=user.username,
                     details="Two-step login turned on")
    return {"recovery_codes": codes}


def _clear_two_step(user):
    user.totp_secret = user.totp_pending_secret = user.totp_enabled_at = None
    user.totp_last_step = user.totp_recovery_codes = None


@router.post("/auth/two-step/disable")
def disable_two_step(payload: TwoStepOff, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user.id).one()
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Two-step login is not on.")
    if not verify_password(payload.password or "", user.hashed_password):
        raise HTTPException(status_code=400, detail="Your password is not right.")
    if not _accept_code(db, user, payload.code):
        db.rollback()
        raise HTTPException(status_code=400, detail=TWO_STEP_WRONG)
    _clear_two_step(user)
    db.commit()
    record_audit_log(db, actor=user.username, action="TWO_STEP_DISABLED", target_type="Auth", target_id=user.username,
                     details="Two-step login turned off")
    return {"two_step_enabled": False}


@router.post("/auth/login")
def login_user(
    username: str = Form(...),
    password: str = Form(...),
    code: str = Form(""),
    db: Session = Depends(get_db),
):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    # Checked before the password so a locked username is refused even with the right password.
    if login_lockout.is_username_locked(db, username):
        record_audit_log(db, actor=username, action="LOGIN_BLOCKED", target_type="Auth", target_id=username, details="Login refused while locked out")
        raise HTTPException(status_code=429, detail=login_lockout.lockout_message(), headers=login_lockout.retry_after_header())

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        _record_failed_login(db, username, "Failed login attempt")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if getattr(user, "status", "Active") == "Pending":
        raise HTTPException(status_code=403, detail="Your account is awaiting administrator approval.")
    if getattr(user, "status", "Active") == "Rejected":
        raise HTTPException(status_code=403, detail="Your registration request has been rejected. Please contact the system administrator.")
    if getattr(user, "status", "Active") == "Inactive" or not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Your account has been deactivated.")

    if user.totp_secret:
        _check_login_code(db, user, code)

    record_audit_log(
        db,
        actor=user.username,
        action="USER_LOGIN",
        target_type="Auth",
        target_id=user.username,
        details="Successful login",
        commit=False,
    )
    # This represents the user's most recent authenticated activity.
    # We intentionally update it on both credentialed login and refresh so it tracks
    # the latest time the user successfully re-established trust, not merely the
    # first time they ever signed in.
    user.last_login = datetime.now(timezone.utc)

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
    if not session or session.revoked_at or not expires_at or expires_at <= datetime.now(timezone.utc):
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
        "access_token": create_access_token({"sub": user.username, "session_id": session_id}),
        "refresh_token": create_refresh_token({"sub": user.username, "session_id": session_id}),
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
        "role": normalize_user_role(session.user.role) if session.user else None,
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
    if session.user and normalize_user_role(session.user.role) == "Super Administrator":
        raise HTTPException(status_code=403, detail="Super Administrator sessions cannot be revoked.")
    if not session.revoked_at:
        session.revoked_at = datetime.now(timezone.utc)
        session.revoke_reason = "administrator_revocation"
        db.commit()
        record_audit_log(db, actor=current_admin.username, action="SESSION_REVOKED", target_type="Session", target_id=session_id, details="Administrator revoked session")
    return {"message": "Session revoked"}
