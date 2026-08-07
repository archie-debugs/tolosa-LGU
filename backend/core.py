from fastapi import Depends, Header, HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
import secrets
import os
from . import models
from .database import get_db

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))


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
    if not db.in_transaction():
        db.commit()
    else:
        db.flush()
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
                connection.exec_driver_sql("ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'Admin'")
            connection.exec_driver_sql("UPDATE users SET role = 'Admin' WHERE role IS NULL OR role = ''")
        else:
            _add_column_if_missing(connection, "users", "role", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR NOT NULL DEFAULT 'Admin'"))
            connection.execute(text("UPDATE users SET role = 'Admin' WHERE role IS NULL OR role = ''"))


def ensure_schema_columns() -> None:
    from .database import engine
    with engine.begin() as connection:
        dialect = engine.dialect.name

        if dialect == "sqlite":
            _add_column_if_missing(connection, "users", "status", "ALTER TABLE users ADD COLUMN status VARCHAR NOT NULL DEFAULT 'Active'")
            _add_column_if_missing(connection, "users", "is_active", "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
            _add_column_if_missing(connection, "users", "created_at", "ALTER TABLE users ADD COLUMN created_at DATETIME")
            _add_column_if_missing(connection, "users", "updated_at", "ALTER TABLE users ADD COLUMN updated_at DATETIME")
            _add_column_if_missing(connection, "registration_requests", "assigned_role", "ALTER TABLE registration_requests ADD COLUMN assigned_role VARCHAR")
            _add_column_if_missing(connection, "registration_requests", "approved_by", "ALTER TABLE registration_requests ADD COLUMN approved_by VARCHAR")
            _add_column_if_missing(connection, "registration_requests", "approved_at", "ALTER TABLE registration_requests ADD COLUMN approved_at DATETIME")
            _add_column_if_missing(connection, "registration_requests", "rejected_by", "ALTER TABLE registration_requests ADD COLUMN rejected_by VARCHAR")
            _add_column_if_missing(connection, "registration_requests", "rejected_at", "ALTER TABLE registration_requests ADD COLUMN rejected_at DATETIME")
        else:
            _add_column_if_missing(connection, "users", "status", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'Active'"))
            _add_column_if_missing(connection, "users", "is_active", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"))
            _add_column_if_missing(connection, "users", "created_at", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP"))
            _add_column_if_missing(connection, "users", "updated_at", text("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
            _add_column_if_missing(connection, "registration_requests", "assigned_role", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS assigned_role VARCHAR"))
            _add_column_if_missing(connection, "registration_requests", "approved_by", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS approved_by VARCHAR"))
            _add_column_if_missing(connection, "registration_requests", "approved_at", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP"))
            _add_column_if_missing(connection, "registration_requests", "rejected_by", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS rejected_by VARCHAR"))
            _add_column_if_missing(connection, "registration_requests", "rejected_at", text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP"))

        connection.execute(text("UPDATE users SET role = 'Admin' WHERE role IS NULL OR role = ''"))
        connection.execute(text("UPDATE users SET status = 'Active' WHERE status IS NULL OR status = ''"))
        connection.execute(text("UPDATE users SET is_active = TRUE WHERE is_active IS NULL"))


def get_current_admin_user(
    db: Session = Depends(get_db),
    admin_username: str | None = Header(default=None, alias="X-Admin-Username"),
    admin_role: str | None = Header(default=None, alias="X-Admin-Role"),
):
    if not admin_username or not admin_role or admin_role.strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    user = db.query(models.User).filter(models.User.username == admin_username).first()
    if not user or user.role != "Admin" or not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
