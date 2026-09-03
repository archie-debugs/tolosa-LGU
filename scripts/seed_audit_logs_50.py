from __future__ import annotations

from datetime import datetime, timedelta, timezone
from random import choice, randint

from Backends.backend.database import SessionLocal
from Backends.backend.models import AuditLog


USERS = ["admin", "joel", "beth", "rhea", "maria", "marla", "staff1", "staff2"]
ACTIONS = [
    ("USER_LOGIN", "Successful login", "Auth"),
    ("USER_LOGOUT", "Session closed successfully", "Auth"),
    ("DOCUMENT_CREATE", "Document registered in the system", "Documents"),
    ("DOCUMENT_UPDATE", "Document metadata updated", "Documents"),
    ("DOCUMENT_APPROVE", "Document approved by administrative review", "Documents"),
    ("DOCUMENT_REJECT", "Document rejected because required validation fields were missing", "Documents"),
    ("ROLE_ASSIGN", "Role assigned to user account", "Users & Roles"),
    ("REPORT_EXPORT", "Analytics report exported successfully", "Analytics"),
    ("DOCUMENT_ARCHIVE", "Document archived and moved to closed records", "Documents"),
    ("USER_LOGIN", "Failed login attempt detected and blocked", "Auth"),
]


def build_details(action: str) -> str:
    if action == "USER_LOGIN":
        return "Successful login"
    if action == "USER_LOGOUT":
        return "Session closed successfully"
    if action == "DOCUMENT_CREATE":
        return "Document registered in the system. Related record {}.".format(randint(1, 999))
    if action == "DOCUMENT_UPDATE":
        return "Document metadata updated. Related record {}.".format(randint(1, 999))
    if action == "DOCUMENT_APPROVE":
        return "Document approved by administrative review. Related record {}.".format(randint(1, 999))
    if action == "DOCUMENT_REJECT":
        return "Document rejected because required validation fields were missing. Related record {}.".format(randint(1, 999))
    if action == "ROLE_ASSIGN":
        return "Role assigned to user account. Related record {}.".format(randint(1, 999))
    if action == "REPORT_EXPORT":
        return "Analytics report exported successfully. Related record {}.".format(randint(1, 999))
    if action == "DOCUMENT_ARCHIVE":
        return "Document archived and moved to closed records. Related record {}.".format(randint(1, 999))
    return "System activity recorded."


def make_audit_row(index: int, now: datetime):
    action, base_details, target_type = choice(ACTIONS)
    actor = choice(USERS)
    days_ago = randint(0, 29)
    hours_ago = randint(0, 23)
    minute_offset = randint(0, 59)
    created_at = now - timedelta(days=days_ago, hours=hours_ago, minutes=minute_offset)

    if "FAILED" in base_details.upper() or action == "USER_LOGIN" and "Failed" in base_details:
        status = "Failed"
        display_details = base_details
    else:
        status = "Success"
        display_details = base_details

    target_id = f"TEST-{100 + index}"
    return AuditLog(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=display_details + f" Record {index}.",
        created_at=created_at,
    )


def ensure_audit_logs_total(target_total: int = 50):
    db = SessionLocal()
    try:
        current_total = db.query(AuditLog).count()
        needed = max(0, target_total - current_total)
        if needed == 0:
            print(f"Audit logs already at {current_total}. No new rows inserted.")
            return current_total

        now = datetime.now(timezone.utc)
        rows = [make_audit_row(i, now) for i in range(needed)]
        db.add_all(rows)
        db.commit()
        final_total = db.query(AuditLog).count()
        print(f"Inserted {needed} audit log rows. Total now: {final_total}")
        return final_total
    finally:
        db.close()


if __name__ == "__main__":
    ensure_audit_logs_total(50)
