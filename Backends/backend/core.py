import ast
from fastapi import Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta, timezone
import os
import json
import re
import tempfile
from . import models
from .authentication import get_current_user_for_user_management
from .database import get_db

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def _default_document_storage_dir() -> str:
    base = os.getenv("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "sb_tolosa_tracking", "documents")


# Stored attachments are official records, so they live in a persistent folder outside the
# repository (DOCUMENT_STORAGE_DIR, or a per-user application data folder). Only in-progress
# browser uploads belong in the system temp area, which the OS may clean at any time.
UPLOAD_DIR = os.path.abspath(os.getenv("DOCUMENT_STORAGE_DIR", "").strip() or _default_document_storage_dir())
TEMP_UPLOAD_DIR = os.path.abspath(
    os.getenv("TEMP_UPLOAD_DIR", "").strip() or os.path.join(tempfile.gettempdir(), "sb_tolosa_tracking", "tmp")
)
# Attachments stored before DOCUMENT_STORAGE_DIR existed; scripts/migrate_attachment_storage.py moves them.
LEGACY_UPLOAD_DIR = os.path.abspath(os.path.join(tempfile.gettempdir(), "sb_tolosa_tracking", "uploads"))


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def record_audit_log(
    db: Session,
    *,
    actor: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: str | None = None,
    commit: bool = True,
):
    """Record an audit entry.

    By default the entry is committed immediately, together with anything else pending in
    the session; that keeps denial and failure entries even when the caller then raises.
    Pass commit=False inside a multi-step write so the entry commits (or rolls back) with
    the caller's own transaction.
    """
    audit_log = models.AuditLog(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    db.add(audit_log)
    if not commit:
        db.flush()
        return audit_log
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(audit_log)
    return audit_log


def ensure_default_super_admin_account() -> None:
    """Create the first Super Administrator from INITIAL_ADMIN_USERNAME/INITIAL_ADMIN_PASSWORD.

    Runs only while no active Super Administrator exists, and never modifies existing
    accounts, so it cannot reset a password or re-enable a deactivated user.
    """
    from .database import SessionLocal

    db = SessionLocal()
    try:
        has_active_super_admin = db.query(models.User.id).filter(
            models.User.role == "Super Administrator",
            models.User.is_active.is_(True),
            models.User.status == "Active",
        ).first() is not None
        if has_active_super_admin:
            return

        username = os.getenv("INITIAL_ADMIN_USERNAME", "").strip()
        password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
        if not username or not password:
            print(
                "WARNING: No active Super Administrator exists. Set INITIAL_ADMIN_USERNAME and "
                "INITIAL_ADMIN_PASSWORD to create one at startup."
            )
            return
        if len(password) < 8:
            raise RuntimeError("INITIAL_ADMIN_PASSWORD must be at least 8 characters")
        if db.query(models.User.id).filter(models.User.username == username).first() is not None:
            raise RuntimeError(
                f"INITIAL_ADMIN_USERNAME '{username}' already belongs to an account; "
                "activate it or choose a different username"
            )

        db.add(models.User(
            username=username,
            hashed_password=get_password_hash(password),
            role="Super Administrator",
            permissions=str(["*"]),
            status="Active",
            is_active=True,
            full_name="Initial Super Administrator",
        ))
        db.commit()
        record_audit_log(
            db,
            actor="System",
            action="INITIAL_SUPER_ADMIN_CREATED",
            target_type="User",
            target_id=username,
            details="Initial Super Administrator created from environment configuration",
        )
    finally:
        db.close()


VALID_ROLES = {"Super Administrator", "Employee", "SB Member"}
LEGACY_ROLE_MAP = {
    "admin": "Super Administrator",
    "super administrator": "Super Administrator",
    "employee": "Employee",
    "sb member": "SB Member",
    "staff": "Employee",
    "secretary / vice mayor": "Employee",
    "secretary": "Employee",
}
DEFAULT_ROLE_PERMISSIONS = {
    "Super Administrator": ["*"],
    "Employee": [
        "view_dashboard",
        "view_documents",
        "search_documents",
        "filter_documents",
        "view_document_details",
        "pass_office_documents",
        "edit_documents",
        "register_documents",
        "archive_documents",
        "restore_documents",
        "import_documents",
        "export_documents",
        "download_documents",
        "print_documents",
        "update_document_status",
        "generate_qr_codes",
        "print_qr_codes",
        "view_qr_tracking",
        "set_documents_for_sb_members",
        "manage_members_and_committees",
        "change_measure_stage",
        "view_audit_logs",
        "export_audit_logs",
        "view_analytics",
        "export_analytics",
    ],
    "SB Member": [
        "view_documents",
        "search_documents",
        "filter_documents",
        "view_document_details",
        "download_documents",
        "print_documents",
    ],
}

# "Today" for Today's Documents is the LGU's calendar day, not the server's or UTC's.
# The Philippines is UTC+8 all year (no daylight saving).
LGU_UTC_OFFSET_HOURS = float(os.getenv("LGU_UTC_OFFSET_HOURS", "8"))
LGU_TIMEZONE = timezone(timedelta(hours=LGU_UTC_OFFSET_HOURS))


def lgu_today() -> date:
    return datetime.now(LGU_TIMEZONE).date()

USER_MANAGEMENT_PERMISSIONS = {
    "view_users",
    "create_users",
    "edit_users",
    "reset_passwords",
    "activate_users",
    "deactivate_users",
    "delete_users",
    "assign_roles",
    "manage_permissions",
}
UI_PERMISSIONS = {
    "delete_documents",
    "modify_system_settings",
    "manage_public_visibility",
}
OFFICE_WORKFLOW_PERMISSIONS = {
    "view_office_documents",
    "search_office_documents",
    "view_office_document_details",
    "scan_qr",
    "pass_office_documents",
    "confirm_document_receipt",
    "view_office_history",
}
VALID_PERMISSIONS = {
    permission
    for permissions in DEFAULT_ROLE_PERMISSIONS.values()
    for permission in permissions
    if permission != "*"
} | USER_MANAGEMENT_PERMISSIONS | UI_PERMISSIONS | OFFICE_WORKFLOW_PERMISSIONS

# Shown on the public homepage until a Super Administrator edits them in Settings.
DEFAULT_HOMEPAGE_ANNOUNCEMENTS = [
    {"category": "PUBLIC NOTICE", "title": "Public sessions and notices", "date": "", "details": ""},
    {"category": "LEGISLATIVE UPDATE", "title": "Official records and updates", "date": "", "details": ""},
]

DEFAULT_SYSTEM_SETTINGS = {
    "organization_name": "LGU Tolosa",
    "system_name": "LGU Tolosa Legislative Document Tracking System",
    "public_portal_enabled": True,
    "maintenance_mode": False,
    "session_timeout_minutes": 60,
    "upload_max_size_mb": 25,
    "allowed_file_types": ["pdf", "doc", "docx", "jpg", "jpeg", "png"],
    "homepage_announcements": DEFAULT_HOMEPAGE_ANNOUNCEMENTS,
}

SYSTEM_SETTING_TYPES = {
    "organization_name": str,
    "system_name": str,
    "public_portal_enabled": bool,
    "maintenance_mode": bool,
    "session_timeout_minutes": int,
    "upload_max_size_mb": int,
    "allowed_file_types": list,
    "homepage_announcements": list,
}

ROLE_DEFINITIONS = {
    role: tuple(permissions)
    for role, permissions in DEFAULT_ROLE_PERMISSIONS.items()
}


def normalize_user_role(role: str | None) -> str:
    # A missing role must never grant access: return "" so role and permission checks fail closed.
    if role is None:
        return ""
    normalized = str(role).strip()
    if not normalized:
        return ""
    lowered = normalized.lower()
    if lowered in LEGACY_ROLE_MAP:
        return LEGACY_ROLE_MAP[lowered]
    for valid_role in VALID_ROLES:
        if valid_role.lower() == lowered:
            return valid_role
    return normalized


def normalize_permission_name(permission: str | None) -> str:
    if permission is None:
        return ""
    return str(permission).strip().lower().replace(" ", "_")


def normalize_permissions(value) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return set()
        parsed = None
        if text.startswith("[") or text.startswith("{"):
            try:
                parsed = json.loads(text)
            except Exception:
                try:
                    parsed = ast.literal_eval(text)
                except Exception:
                    parsed = None
        if parsed is None:
            parsed = [item.strip() for item in re.split(r"[\s,]+", text) if item.strip()]
        if isinstance(parsed, str):
            parsed = [parsed]
        if isinstance(parsed, (list, tuple, set)):
            return {normalize_permission_name(item) for item in parsed}
        if isinstance(parsed, dict):
            return {normalize_permission_name(item) for item in parsed.keys()}
        return {normalize_permission_name(str(parsed))}
    if isinstance(value, (list, tuple, set)):
        return {normalize_permission_name(item) for item in value}
    if isinstance(value, dict):
        return {normalize_permission_name(item) for item in value.keys()}
    return {normalize_permission_name(str(value))}


def validate_permissions(value) -> list[str]:
    permissions = normalize_permissions(value)
    invalid = sorted(permission for permission in permissions if permission not in VALID_PERMISSIONS and permission != "*")
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown permission(s): {', '.join(invalid)}")
    return sorted(permissions)


def get_default_permissions_for_role(role: str | None) -> list[str]:
    normalized = normalize_user_role(role)
    return list(DEFAULT_ROLE_PERMISSIONS.get(normalized, []))


def user_has_permission(user: models.User, permission: str) -> bool:
    if user is None:
        return False
    role = normalize_user_role(getattr(user, "role", None))
    if role == "Super Administrator":
        return True
    if role not in VALID_ROLES:
        return False
    normalized_permission = normalize_permission_name(permission)
    if normalized_permission in OFFICE_WORKFLOW_PERMISSIONS and (
        role != "Employee" or getattr(user, "office_id", None) is None
    ):
        return False
    # SB Members are read-only, whatever was saved on their account.
    if role == "SB Member" and normalized_permission not in DEFAULT_ROLE_PERMISSIONS["SB Member"]:
        return False
    permissions = normalize_permissions(getattr(user, "permissions", None))
    if "*" in permissions:
        return True
    return normalized_permission in permissions


def get_current_admin_user(current_user: models.User = Depends(get_current_user_for_user_management)):
    if normalize_user_role(current_user.role) != "Super Administrator":
        raise HTTPException(status_code=403, detail="Super Administrator access required")
    return current_user


def require_user_management_permission(permission: str):
    def dependency(current_user: models.User = Depends(get_current_user_for_user_management)):
        require_permission(current_user, permission)
        return current_user

    return dependency


def require_user_role(user: models.User, allowed_roles: set[str]):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if normalize_user_role(getattr(user, "role", None)) == "Super Administrator":
        return
    if normalize_user_role(getattr(user, "role", None)) not in allowed_roles:
        raise HTTPException(status_code=403, detail="Access denied")


def require_permission(user: models.User, permission: str):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if normalize_user_role(getattr(user, "role", None)) == "Super Administrator":
        return
    if not user_has_permission(user, permission):
        raise HTTPException(status_code=403, detail="Permission denied")
