import ast
from fastapi import Depends, Header, HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
import secrets
import os
import json
import re
from . import models
from fastapi import Header
from .auth_jwt import decode_access_token
from .database import get_db

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
TEMP_UPLOAD_DIR = os.path.abspath(os.path.join(UPLOAD_DIR, "tmp"))


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
):
    audit_log = models.AuditLog(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    db.add(audit_log)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(audit_log)
    return audit_log


def _column_exists(connection, table_name: str, column_name: str) -> bool:
    dialect = connection.dialect.name
    if dialect == "sqlite":
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(row[1] == column_name for row in rows)
    rows = connection.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :table_name AND column_name = :column_name"),
        {"table_name": table_name, "column_name": column_name},
    ).fetchall()
    return len(rows) > 0


def _add_column_if_missing(connection, table_name: str, column_name: str, add_sql: str) -> None:
    if not _column_exists(connection, table_name, column_name):
        if isinstance(add_sql, str):
            connection.execute(text(add_sql))
        else:
            connection.execute(add_sql)


def ensure_user_role_column() -> None:
    from .database import engine
    with engine.begin() as connection:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            columns = [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
            if "role" not in columns:
                connection.exec_driver_sql("ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'Super Administrator'")
            connection.exec_driver_sql("UPDATE users SET role = 'Super Administrator' WHERE role IS NULL OR role = ''")
            connection.exec_driver_sql("UPDATE users SET role = 'Super Administrator' WHERE lower(role) = 'admin'")
            connection.exec_driver_sql("UPDATE users SET role = 'Employee' WHERE lower(role) IN ('staff', 'secretary', 'secretary / vice mayor')")
        else:
            _add_column_if_missing(connection, "users", "role", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR NOT NULL DEFAULT 'Super Administrator'"))
            connection.execute(text("UPDATE users SET role = 'Super Administrator' WHERE role IS NULL OR role = ''"))
            connection.execute(text("UPDATE users SET role = 'Super Administrator' WHERE lower(role) = 'admin'"))
            connection.execute(text("UPDATE users SET role = 'Employee' WHERE lower(role) IN ('staff', 'secretary', 'secretary / vice mayor')"))


def ensure_schema_columns() -> None:
    from .database import engine
    with engine.begin() as connection:
        dialect = engine.dialect.name

        if dialect == "sqlite":
            _add_column_if_missing(connection, "users", "status", "ALTER TABLE users ADD COLUMN status VARCHAR NOT NULL DEFAULT 'Active'")
            _add_column_if_missing(connection, "users", "is_active", "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
            _add_column_if_missing(connection, "users", "created_at", "ALTER TABLE users ADD COLUMN created_at DATETIME")
            _add_column_if_missing(connection, "users", "updated_at", "ALTER TABLE users ADD COLUMN updated_at DATETIME")
            _add_column_if_missing(connection, "users", "permissions", "ALTER TABLE users ADD COLUMN permissions TEXT")
            _add_column_if_missing(connection, "users", "full_name", "ALTER TABLE users ADD COLUMN full_name VARCHAR")
            _add_column_if_missing(connection, "users", "email", "ALTER TABLE users ADD COLUMN email VARCHAR")
            _add_column_if_missing(connection, "registration_requests", "assigned_role", "ALTER TABLE registration_requests ADD COLUMN assigned_role VARCHAR")
            _add_column_if_missing(connection, "registration_requests", "approved_by", "ALTER TABLE registration_requests ADD COLUMN approved_by VARCHAR")
            _add_column_if_missing(connection, "registration_requests", "approved_at", "ALTER TABLE registration_requests ADD COLUMN approved_at DATETIME")
            _add_column_if_missing(connection, "registration_requests", "rejected_by", "ALTER TABLE registration_requests ADD COLUMN rejected_by VARCHAR")
            _add_column_if_missing(connection, "registration_requests", "rejected_at", "ALTER TABLE registration_requests ADD COLUMN rejected_at DATETIME")
            _add_column_if_missing(connection, "documents", "author", "ALTER TABLE documents ADD COLUMN author VARCHAR")
            _add_column_if_missing(connection, "documents", "session", "ALTER TABLE documents ADD COLUMN session VARCHAR")
            _add_column_if_missing(connection, "documents", "date_registered", "ALTER TABLE documents ADD COLUMN date_registered VARCHAR")
            _add_column_if_missing(connection, "documents", "attachment_name", "ALTER TABLE documents ADD COLUMN attachment_name VARCHAR")
            _add_column_if_missing(connection, "documents", "qr_code_value", "ALTER TABLE documents ADD COLUMN qr_code_value VARCHAR")
            _add_column_if_missing(connection, "documents", "archived_at", "ALTER TABLE documents ADD COLUMN archived_at DATETIME")
            _add_column_if_missing(connection, "documents", "archived_by", "ALTER TABLE documents ADD COLUMN archived_by VARCHAR")
        else:
            _add_column_if_missing(connection, "users", "status", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'Active'"))
            _add_column_if_missing(connection, "users", "is_active", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"))
            _add_column_if_missing(connection, "users", "created_at", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP"))
            _add_column_if_missing(connection, "users", "updated_at", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
            _add_column_if_missing(connection, "users", "permissions", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions TEXT"))
            _add_column_if_missing(connection, "users", "full_name", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR"))
            _add_column_if_missing(connection, "users", "email", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR"))
            _add_column_if_missing(connection, "registration_requests", "assigned_role", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS assigned_role VARCHAR"))
            _add_column_if_missing(connection, "registration_requests", "approved_by", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS approved_by VARCHAR"))
            _add_column_if_missing(connection, "registration_requests", "approved_at", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP"))
            _add_column_if_missing(connection, "registration_requests", "rejected_by", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS rejected_by VARCHAR"))
            _add_column_if_missing(connection, "registration_requests", "rejected_at", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP"))
            _add_column_if_missing(connection, "documents", "author", text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS author VARCHAR"))
            _add_column_if_missing(connection, "documents", "session", text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS session VARCHAR"))
            _add_column_if_missing(connection, "documents", "date_registered", text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS date_registered VARCHAR"))
            _add_column_if_missing(connection, "documents", "attachment_name", text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS attachment_name VARCHAR"))
            _add_column_if_missing(connection, "documents", "qr_code_value", text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS qr_code_value VARCHAR"))
            _add_column_if_missing(connection, "documents", "archived_at", text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP"))
            _add_column_if_missing(connection, "documents", "archived_by", text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS archived_by VARCHAR"))

        connection.execute(text("UPDATE users SET role = 'Super Administrator' WHERE role IS NULL OR role = ''"))
        connection.execute(text("UPDATE users SET role = 'Super Administrator' WHERE lower(role) = 'admin'"))
        connection.execute(text("UPDATE users SET role = 'Employee' WHERE lower(role) IN ('staff', 'secretary', 'secretary / vice mayor')"))
        connection.execute(text("UPDATE users SET status = 'Active' WHERE status IS NULL OR status = ''"))
        connection.execute(text("UPDATE users SET is_active = TRUE WHERE is_active IS NULL"))
        connection.execute(text("UPDATE users SET permissions = '[]' WHERE permissions IS NULL"))
        connection.execute(text("UPDATE users SET created_at = current_timestamp WHERE created_at IS NULL"))
        _add_column_if_missing(connection, "users", "permissions", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions TEXT"))


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
        "view_document_requests",
        "approve_document_requests",
        "reject_document_requests",
        "fulfill_document_requests",
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
        "request_documents",
        "view_own_document_requests",
        "cancel_own_pending_requests",
    ],
}


def normalize_user_role(role: str | None) -> str:
    if role is None:
        return "Super Administrator"
    normalized = str(role).strip()
    if not normalized:
        return "Super Administrator"
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


def get_default_permissions_for_role(role: str | None) -> list[str]:
    normalized = normalize_user_role(role)
    return list(DEFAULT_ROLE_PERMISSIONS.get(normalized, []))


def user_has_permission(user: models.User, permission: str) -> bool:
    if user is None:
        return False
    role = normalize_user_role(getattr(user, "role", None))
    if role == "Super Administrator":
        return True
    permissions = normalize_permissions(getattr(user, "permissions", None))
    if "*" in permissions:
        return True
    normalized_permission = normalize_permission_name(permission)
    return normalized_permission in permissions


def get_current_admin_user(
    db: Session = Depends(get_db),
    admin_username: str | None = Header(default=None, alias="X-Admin-Username"),
    admin_role: str | None = Header(default=None, alias="X-Admin-Role"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
            username = payload.get("sub")
            if username:
                user = db.query(models.User).filter(models.User.username == username).first()
                if user and normalize_user_role(user.role) == "Super Administrator" and getattr(user, "is_active", True):
                    return user
        except Exception:
            pass

    if not admin_username or not admin_role:
        raise HTTPException(status_code=403, detail="Super Administrator access required")

    if normalize_user_role(admin_role) != "Super Administrator":
        raise HTTPException(status_code=403, detail="Super Administrator access required")

    user = db.query(models.User).filter(models.User.username == admin_username).first()
    if not user or normalize_user_role(user.role) != "Super Administrator" or not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Super Administrator access required")
    return user


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


def get_current_documents_import_user(
    db: Session = Depends(get_db),
    import_username: str | None = Header(default=None, alias="X-Admin-Username"),
    import_role: str | None = Header(default=None, alias="X-Admin-Role"),
):
    if not import_username or not import_role:
        raise HTTPException(status_code=403, detail="Access denied")

    normalized_role = normalize_user_role(import_role)
    allowed_roles = {"Super Administrator", "Employee", "SB Member"}
    user = db.query(models.User).filter(models.User.username == import_username).first()
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Access denied")

    if normalize_user_role(user.role) == "Super Administrator" or normalize_user_role(user.role) in allowed_roles:
        return user

    raise HTTPException(status_code=403, detail="Access denied")
