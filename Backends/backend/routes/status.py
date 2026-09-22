import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models
from ..core import require_permission, require_user_management_permission
from ..database import engine, get_db
from ..routes.analytics import _storage_information

router = APIRouter()


def _status_from_bool(value: bool) -> str:
    return "operational" if value else "warning"


@router.get("/")
def root():
    return {"status": "SB Tolosa System Engine Live"}


@router.get("/system-health")
def system_health(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("modify_system_settings")),
):
    require_permission(current_admin, "modify_system_settings")

    maintenance_mode = False
    try:
        maintenance_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "maintenance_mode").first()
        if maintenance_setting is not None and maintenance_setting.value is not None:
            maintenance_mode = str(maintenance_setting.value).strip().lower() == "true"
    except Exception:
        maintenance_mode = False

    db_status = "operational"
    db_detail = "Database connection healthy"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "unavailable"
        db_detail = str(exc)

    storage = _storage_information()
    storage_status = str(storage.get("status") or "warning").lower()
    if storage_status not in {"operational", "ok", "healthy"}:
        storage_status = "warning" if storage_status != "unavailable" else "unavailable"

    audit_failures = db.query(models.AuditLog).filter(
        models.AuditLog.action.ilike("%fail%")
        | models.AuditLog.action.ilike("%error%")
        | models.AuditLog.action.ilike("%deny%")
        | models.AuditLog.action.ilike("%reject%")
        | models.AuditLog.action.ilike("%expired%")
    ).count()
    audit_status = "operational" if audit_failures == 0 else "warning"

    backup_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backups"))
    backup_status = "warning"
    backup_detail = "No backup directory found"
    if os.path.isdir(backup_dir):
        backups = [
            os.path.join(backup_dir, name)
            for name in sorted(os.listdir(backup_dir))
            if os.path.isdir(os.path.join(backup_dir, name))
        ]
        if backups:
            backup_status = "operational"
            backup_detail = f"{len(backups)} backup(s) available"
        else:
            backup_status = "warning"
            backup_detail = "Backup directory exists but contains no backups"

    components = {
        "database": {
            "status": db_status,
            "detail": db_detail,
        },
        "storage": {
            "status": storage_status,
            "detail": storage,
        },
        "audit": {
            "status": audit_status,
            "detail": {"failed_events": audit_failures},
        },
        "backup": {
            "status": backup_status,
            "detail": backup_detail,
        },
        "authentication": {
            "status": "operational",
            "detail": {"authenticated_user": current_admin.username},
        },
        "maintenance": {
            "status": _status_from_bool(not maintenance_mode),
            "detail": {"maintenance_mode": maintenance_mode},
        },
    }

    component_states = [component["status"] for component in components.values()]
    if any(status == "unavailable" for status in component_states):
        overall_status = "degraded"
    elif any(status == "warning" for status in component_states):
        overall_status = "warning"
    else:
        overall_status = "operational"

    return {
        "status": overall_status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "maintenance_mode": maintenance_mode,
        "components": components,
        "alerts": [
            {"component": "maintenance", "message": "Maintenance mode is enabled"}
        ] if maintenance_mode else [],
    }
