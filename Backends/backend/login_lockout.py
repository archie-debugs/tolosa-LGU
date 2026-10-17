"""Throttle password guessing on POST /auth/login.

After LOGIN_MAX_FAILURES failed logins within LOGIN_LOCKOUT_MINUTES a username is locked,
even for the correct password, until those failures age out of the window. Failures are
read from FAILED_LOGIN audit entries, so the lock is shared by every backend process and
survives restarts. A successful login or an ACCOUNT_UNLOCKED entry resets the count.

There is deliberately no per-IP limit: the Flet frontends call the backend from their own
server process, so every login arrives from the same address and an IP limit would let
one attacker lock out everyone.
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models

LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

# Audit actions that clear a username's failure count.
RESET_ACTIONS = ("USER_LOGIN", "ACCOUNT_UNLOCKED")


def recent_failure_count(db: Session, username: str) -> int:
    window_start = datetime.now(timezone.utc) - timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
    last_reset = db.query(func.max(models.AuditLog.created_at)).filter(
        models.AuditLog.target_type == "Auth",
        models.AuditLog.target_id == username,
        models.AuditLog.action.in_(RESET_ACTIONS),
    ).scalar()
    query = db.query(func.count(models.AuditLog.id)).filter(
        models.AuditLog.target_type == "Auth",
        models.AuditLog.target_id == username,
        models.AuditLog.action == "FAILED_LOGIN",
        models.AuditLog.created_at >= window_start,
    )
    if last_reset is not None:
        query = query.filter(models.AuditLog.created_at > last_reset)
    return query.scalar() or 0


def is_username_locked(db: Session, username: str) -> bool:
    return recent_failure_count(db, username) >= LOGIN_MAX_FAILURES


def lockout_message() -> str:
    return f"Too many failed login attempts. Try again in {LOGIN_LOCKOUT_MINUTES} minutes."


def retry_after_header() -> dict[str, str]:
    return {"Retry-After": str(LOGIN_LOCKOUT_MINUTES * 60)}
