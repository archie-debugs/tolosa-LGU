from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..auth_jwt import get_current_user
from ..core import require_permission

router = APIRouter()


def _derive_status_value(action: str | None) -> str:
    if not action:
        return "Success"
    action_upper = str(action).upper()
    if any(token in action_upper for token in ["FAIL", "ERROR", "DENY", "REJECT", "BLOCK", "EXPIRED"]):
        return "Failed"
    return "Success"


@router.get("/audit/logs")
def list_audit_logs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    date_range: str | None = Query("today"),
    user: str | None = Query(None),
    action: str | None = Query(None),
    module: str | None = Query(None),
    status: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
):
    require_permission(current_user, "view_audit_logs")

    query = db.query(models.AuditLog)

    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.AuditLog.actor.ilike(like),
                models.AuditLog.action.ilike(like),
                models.AuditLog.target_type.ilike(like),
                models.AuditLog.target_id.ilike(like),
                models.AuditLog.details.ilike(like),
            )
        )

    if user:
        query = query.filter(models.AuditLog.actor == user)
    if action:
        query = query.filter(models.AuditLog.action == action)
    if module:
        query = query.filter(models.AuditLog.target_type == module)
    if status:
        normalized_status = str(status).strip().lower()
        if normalized_status == "failed":
            query = query.filter(
                or_(
                    models.AuditLog.action.ilike("%fail%"),
                    models.AuditLog.action.ilike("%error%"),
                    models.AuditLog.action.ilike("%deny%"),
                    models.AuditLog.action.ilike("%reject%"),
                    models.AuditLog.action.ilike("%expired%"),
                )
            )
        elif normalized_status == "success":
            query = query.filter(
                ~or_(
                    models.AuditLog.action.ilike("%fail%"),
                    models.AuditLog.action.ilike("%error%"),
                    models.AuditLog.action.ilike("%deny%"),
                    models.AuditLog.action.ilike("%reject%"),
                    models.AuditLog.action.ilike("%expired%"),
                )
            )

    now = datetime.now(timezone.utc)
    if date_range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        query = query.filter(models.AuditLog.created_at >= start, models.AuditLog.created_at <= end)
    elif date_range == "yesterday":
        day = (now - timedelta(days=1)).date()
        start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(day, datetime.max.time().replace(tzinfo=timezone.utc), tzinfo=timezone.utc)
        query = query.filter(models.AuditLog.created_at >= start, models.AuditLog.created_at <= end)
    elif date_range == "last_7_days":
        start = now - timedelta(days=6)
        query = query.filter(models.AuditLog.created_at >= start)
    elif date_range == "last_30_days":
        start = now - timedelta(days=29)
        query = query.filter(models.AuditLog.created_at >= start)
    elif date_range == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query = query.filter(models.AuditLog.created_at >= start)
    elif date_range == "last_month":
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month = first_of_this_month - timedelta(days=1)
        start = last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_of_this_month - timedelta(microseconds=1)
        query = query.filter(models.AuditLog.created_at >= start, models.AuditLog.created_at <= end)
    elif date_range == "custom_range":
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                query = query.filter(models.AuditLog.created_at >= from_dt)
            except ValueError:
                pass
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                query = query.filter(models.AuditLog.created_at <= to_dt)
            except ValueError:
                pass
    # all_time: no date filter

    total = query.count()
    pages = max(1, (total + limit - 1) // limit) if total else 1
    page = min(page, pages)
    offset = (page - 1) * limit

    audit_logs = query.order_by(models.AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    all_logs = db.query(models.AuditLog).all()
    total_activities = len(all_logs)
    today = sum(1 for item in all_logs if item.created_at and item.created_at.date() == now.date())
    week_start = now.date() - timedelta(days=now.weekday())
    this_week = sum(1 for item in all_logs if item.created_at and item.created_at.date() >= week_start)
    this_month = sum(1 for item in all_logs if item.created_at and item.created_at.year == now.year and item.created_at.month == now.month)
    failed_actions = sum(1 for item in all_logs if _derive_status_value(item.action) == "Failed")

    all_items = [
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
            "target_type": audit_log.target_type,
            "target_id": audit_log.target_id,
            "details": audit_log.details,
            "module": audit_log.target_type,
            "status": _derive_status_value(audit_log.action),
            "role": None,
            "ip_address": None,
            "metadata": {},
        }
        for audit_log in audit_logs
    ]

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": pages,
        "items": all_items,
        "summary": {
            "total_activities": total_activities,
            "today": today,
            "this_week": this_week,
            "this_month": this_month,
            "failed_actions": failed_actions,
        },
        "filters": {
            "users": sorted({item.actor for item in all_logs if item.actor}),
            "modules": sorted({item.target_type for item in all_logs if item.target_type}),
            "actions": sorted({item.action for item in all_logs if item.action}),
            "statuses": ["Success", "Failed"],
        },
    }
