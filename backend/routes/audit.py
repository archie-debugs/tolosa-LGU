from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..auth_jwt import get_current_user
from ..core import require_permission

router = APIRouter()

@router.get("/audit/logs")
def list_audit_logs(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, "view_audit_logs")
    audit_logs = db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).all()
    return {
        "items": [
            {
                "id": audit_log.id,
                "created_at": audit_log.created_at.isoformat() if audit_log.created_at else None,
                "actor": audit_log.actor,
                "action": audit_log.action,
                "target": (
                    f"{audit_log.target_type}:{audit_log.target_id}"
                    if audit_log.target_type or audit_log.target_id
                    else None
                ),
                "details": audit_log.details,
            }
            for audit_log in audit_logs
        ]
    }
