import csv
import io
from calendar import monthrange
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models
from ..auth_jwt import get_current_user
from ..core import require_permission
from ..database import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _to_bool(value):
    return bool(value) if value is not None else False


def _as_aware_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except Exception:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _norm_status(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if text in {"pending", "for approval", "awaiting action", "awaiting review"}:
        return "Pending"
    if text in {"in progress", "in processing", "ongoing"}:
        return "In Progress"
    if text in {"completed", "complete", "done", "approved", "finished"}:
        return "Completed"
    if text in {"archived", "archive", "closed"}:
        return "Archived"
    return str(value).strip() or "Unknown"


@router.get("")
@router.get("/")
@router.get("/overview")
def get_analytics_overview(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    year: int | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    office: str | None = Query(default=None),
):
    """Return database-derived analytics for documents and activity."""
    require_permission(current_user, "view_analytics")

    base_query = db.query(models.Document)
    if document_type:
        base_query = base_query.filter(models.Document.document_type == document_type)
    if status:
        base_query = base_query.filter(models.Document.status == status)
    if office:
        base_query = base_query.filter(models.Document.current_office == office)

    documents = base_query.all()

    if year:
        documents = [doc for doc in documents if _as_aware_datetime(doc.created_at) and _as_aware_datetime(doc.created_at).year == year]
    if start_date:
        try:
            start_dt = _as_aware_datetime(start_date)
            if start_dt:
                documents = [doc for doc in documents if _as_aware_datetime(doc.created_at) and _as_aware_datetime(doc.created_at) >= start_dt]
        except Exception:
            pass
    if end_date:
        try:
            end_dt = _as_aware_datetime(end_date)
            if end_dt:
                documents = [doc for doc in documents if _as_aware_datetime(doc.created_at) and _as_aware_datetime(doc.created_at) <= end_dt]
        except Exception:
            pass

    total_documents = len(documents)
    archived_documents = sum(1 for doc in documents if _to_bool(doc.archived))
    active_documents = sum(1 for doc in documents if not _to_bool(doc.archived))

    pending_documents = sum(1 for doc in documents if _norm_status(doc.status) == "Pending")
    completed_documents = sum(1 for doc in documents if _norm_status(doc.status) == "Completed")

    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    added_this_month = sum(
        1 for doc in documents
        if _as_aware_datetime(doc.created_at) and _as_aware_datetime(doc.created_at) >= start_of_month
    )

    status_breakdown = {}
    for doc in documents:
        normalized = _norm_status(doc.status)
        status_breakdown[normalized] = status_breakdown.get(normalized, 0) + 1

    document_types = {}
    for doc in documents:
        key = doc.document_type or "Unspecified"
        document_types[key] = document_types.get(key, 0) + 1

    offices = {}
    for doc in documents:
        key = doc.current_office or "Unassigned"
        offices[key] = offices.get(key, 0) + 1

    processing_days = []
    for doc in documents:
        doc_created = _as_aware_datetime(doc.created_at)
        update_dt = _as_aware_datetime(doc.updated_at) or doc_created
        if doc_created and update_dt:
            try:
                diff = update_dt - doc_created
                days = diff.total_seconds() / 86400.0
                if days >= 0:
                    processing_days.append(days)
            except Exception:
                pass

    average_processing_days = round(sum(processing_days) / len(processing_days), 2) if processing_days else None

    awaiting_action = sum(1 for doc in documents if _norm_status(doc.status) in {"Pending", "In Progress"})

    pending_docs = [doc for doc in documents if _norm_status(doc.status) == "Pending"]
    longest_pending = None
    if pending_docs:
        oldest = sorted(
            pending_docs,
            key=lambda d: (_as_aware_datetime(d.created_at) or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=False,
        )[0]
        oldest_created = _as_aware_datetime(oldest.created_at)
        longest_pending = {
            "tracking_number": oldest.tracking_number,
            "days": None,
            "created_at": oldest_created.isoformat() if oldest_created else None,
        }
        if oldest_created:
            try:
                longest_pending["days"] = (now - oldest_created).days
            except Exception:
                longest_pending["days"] = None

    completed_this_month = sum(
        1 for doc in documents
        if _norm_status(doc.status) == "Completed"
        and _as_aware_datetime(doc.created_at)
        and _as_aware_datetime(doc.created_at).year == now.year
        and _as_aware_datetime(doc.created_at).month == now.month
    )

    archived_this_month = sum(
        1 for doc in documents
        if _to_bool(doc.archived)
        and _as_aware_datetime(doc.updated_at)
        and _as_aware_datetime(doc.updated_at).year == now.year
        and _as_aware_datetime(doc.updated_at).month == now.month
    )

    monthly_activity = []
    for index in range(6):
        month_dt = datetime(now.year, now.month - index, 1, tzinfo=timezone.utc)
        month_start = datetime(month_dt.year, month_dt.month, 1, tzinfo=month_dt.tzinfo)
        days_in_month = monthrange(month_dt.year, month_dt.month)[1]
        month_end = datetime(month_dt.year, month_dt.month, days_in_month, 23, 59, 59, tzinfo=month_dt.tzinfo)
        count = sum(
            1 for doc in documents
            if _as_aware_datetime(doc.created_at)
            and month_start <= _as_aware_datetime(doc.created_at) <= month_end
        )
        monthly_activity.append({
            "month": month_dt.strftime("%Y-%m"),
            "label": month_dt.strftime("%b"),
            "count": count,
        })
    monthly_activity.reverse()

    recent_activity = []
    audit_logs = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.created_at.desc())
        .limit(10)
        .all()
    )
    for item in audit_logs:
        recent_activity.append({
            "tracking_number": item.target_id or "-",
            "activity": item.action,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "actor": item.actor or "System",
        })

    recent_documents = []
    for doc in db.query(models.Document).order_by(models.Document.created_at.desc()).limit(10).all():
        recent_documents.append({
            "id": doc.id,
            "tracking_number": doc.tracking_number,
            "title": doc.title,
            "document_type": doc.document_type,
            "status": doc.status,
            "priority": doc.priority,
            "current_office": doc.current_office,
            "date_registered": doc.date_registered or (doc.created_at.date().isoformat() if doc.created_at else None),
        })

    return {
        "overview": {
            "total_documents": total_documents,
            "active_documents": active_documents,
            "pending_documents": pending_documents,
            "completed_documents": completed_documents,
            "archived_documents": archived_documents,
            "added_this_month": added_this_month,
        },
        "status_breakdown": status_breakdown,
        "document_types": document_types,
        "offices": offices,
        "processing": {
            "average_processing_days": average_processing_days,
            "awaiting_action": awaiting_action,
            "longest_pending": longest_pending or {"tracking_number": "N/A", "days": "Insufficient data"},
            "completed_this_month": completed_this_month,
            "archived_this_month": archived_this_month,
        },
        "monthly_activity": monthly_activity,
        "recent_activity": recent_activity,
        "recent_documents": recent_documents,
    }


@router.get("/export")
def export_analytics_csv(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Stream a CSV export of the current document list."""
    require_permission(current_user, "export_analytics")

    documents = db.query(models.Document).order_by(models.Document.id.asc()).all()

    output = io.StringIO()
    fieldnames = [
        "id",
        "tracking_number",
        "title",
        "description",
        "document_type",
        "category",
        "originating_office",
        "current_office",
        "assigned_to",
        "status",
        "priority",
        "remarks",
        "author",
        "session",
        "date_registered",
        "qr_code_value",
        "archived",
        "created_by",
        "created_at",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for doc in documents:
        writer.writerow(
            {
                "id": doc.id,
                "tracking_number": doc.tracking_number,
                "title": doc.title,
                "description": doc.description,
                "document_type": doc.document_type,
                "category": doc.category,
                "originating_office": doc.originating_office,
                "current_office": doc.current_office,
                "assigned_to": doc.assigned_to,
                "status": doc.status,
                "priority": doc.priority,
                "remarks": doc.remarks,
                "author": doc.author,
                "session": doc.session,
                "date_registered": doc.date_registered,
                "qr_code_value": doc.qr_code_value,
                "archived": "true" if doc.archived else "false",
                "created_by": doc.created_by,
                "created_at": doc.created_at.isoformat() if doc.created_at else "",
            }
        )

    headers = {
        "Content-Disposition": 'attachment; filename="analytics_documents_export.csv"',
        "Content-Type": "text/csv; charset=utf-8",
    }
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)
