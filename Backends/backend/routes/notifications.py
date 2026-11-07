"""Notifications: what needs the signed-in user's attention, built from handoffs, registrations,
due dates and archived documents whose retention period is ending.

Nothing is stored per notification. An item is unread when it happened after the user's
notifications_seen_at, which POST /notifications/seen moves to now. A priority item (an archived
document due for deletion) stays unread and on top until someone deletes or extends the document.
"""

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..authentication import get_current_user
from ..core import LGU_TIMEZONE, lgu_today, normalize_user_role, user_has_permission
from ..database import get_db
from ..retention import RETENTION_WARNING_DAYS, documents_due
from .documents import QR_TRACKING_OVERDUE_HOURS
from .temporary_documents import due_on as temporary_due_on

router = APIRouter()

DUE_SOON_DAYS = 3
RECENT_REGISTRATION_DAYS = 7
# How long a received, cancelled or returned handoff stays in the other office's notifications.
RECENT_CLOSED_HANDOFF_DAYS = 7
MAX_ITEMS = 30
# How long before its date an archived temporary document shows up as due for deletion soon.
TEMPORARY_WARNING_DAYS = 7


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _day_start(day):
    return datetime.combine(day, time.min, tzinfo=LGU_TIMEZONE)


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def _item(kind, doc, at, message, key):
    return {
        "id": f"{kind}:{key}",
        "kind": kind,
        "document_id": doc.id,
        "tracking_number": doc.tracking_number,
        "title": doc.title,
        "message": message,
        "at": at.isoformat(),
    }


def _hours_waiting(handoff, now):
    return int((now - _aware(handoff.sent_at)).total_seconds() // 3600)


def _pending_handoffs(db):
    return db.query(models.DocumentHandoff).filter(models.DocumentHandoff.status == "Pending Receipt")


def _due_items(db, query, today, with_office):
    items = []
    for doc in query.filter(
        models.Document.archived.is_(False),
        models.Document.due_date.isnot(None),
        models.Document.due_date <= today + timedelta(days=DUE_SOON_DAYS),
    ):
        days = (doc.due_date - today).days
        if days < 0:
            kind, message = "overdue", f"Overdue by {_plural(-days, 'day')}"
            # Overdue is news again on the day after it was due.
            at = _day_start(doc.due_date + timedelta(days=1))
        else:
            kind = "due"
            message = "Due today" if days == 0 else "Due tomorrow" if days == 1 else f"Due in {days} days"
            at = max(_day_start(doc.due_date - timedelta(days=DUE_SOON_DAYS)), _aware(doc.created_at) or datetime.min.replace(tzinfo=timezone.utc))
        if with_office and doc.current_office:
            message += f" · {doc.current_office}"
        items.append(_item(kind, doc, at, message + ".", doc.id))
    return items


def _office_items(db, user, now, today):
    office_id = user.office_id
    items = []
    for handoff in _pending_handoffs(db).filter(models.DocumentHandoff.receiving_office_id == office_id):
        hours = _hours_waiting(handoff, now)
        sender = handoff.sending_office.name if handoff.sending_office else "another office"
        if hours >= QR_TRACKING_OVERDUE_HOURS:
            items.append(_item("incoming_overdue", handoff.document, _aware(handoff.sent_at),
                               f"Sent to your office by {sender}, waiting for receipt for over 24 hours.", handoff.id))
        else:
            items.append(_item("incoming", handoff.document, _aware(handoff.sent_at),
                               f"Sent to your office by {sender}. Waiting for receipt.", handoff.id))
    for handoff in _pending_handoffs(db).filter(models.DocumentHandoff.sending_office_id == office_id):
        hours = _hours_waiting(handoff, now)
        if hours >= QR_TRACKING_OVERDUE_HOURS:
            receiver = handoff.receiving_office.name if handoff.receiving_office else "the other office"
            at = _aware(handoff.sent_at) + timedelta(hours=QR_TRACKING_OVERDUE_HOURS)
            items.append(_item("outgoing_overdue", handoff.document, at,
                               f"Not yet received by {receiver} after {hours} hours.", handoff.id))
    closed_since = now - timedelta(days=RECENT_CLOSED_HANDOFF_DAYS)
    for receipt in db.query(models.DocumentReceipt).join(models.DocumentHandoff, models.DocumentReceipt.handoff_id == models.DocumentHandoff.id).filter(
        models.DocumentHandoff.sending_office_id == office_id,
        models.DocumentReceipt.confirmed_at >= closed_since,
    ):
        receiver = receipt.office.name if receipt.office else "the other office"
        by = f" ({receipt.confirmed_by.username})" if receipt.confirmed_by else ""
        items.append(_item("received", receipt.document, _aware(receipt.confirmed_at),
                           f"Received by {receiver}{by}.", receipt.id))
    for handoff in db.query(models.DocumentHandoff).filter(
        models.DocumentHandoff.closed_at >= closed_since,
        ((models.DocumentHandoff.status == "Returned") & (models.DocumentHandoff.sending_office_id == office_id))
        | ((models.DocumentHandoff.status == "Cancelled") & (models.DocumentHandoff.receiving_office_id == office_id)),
    ):
        reason = f" Reason: {handoff.close_reason}" if handoff.close_reason else ""
        if handoff.status == "Returned":
            receiver = handoff.receiving_office.name if handoff.receiving_office else "the other office"
            items.append(_item("returned", handoff.document, _aware(handoff.closed_at),
                               f"Returned by {receiver} without receiving it. Your office still holds it.{reason}", handoff.id))
        else:
            sender = handoff.sending_office.name if handoff.sending_office else "The sending office"
            items.append(_item("cancelled", handoff.document, _aware(handoff.closed_at),
                               f"{sender} cancelled the handoff to your office. No need to receive it.{reason}", handoff.id))
    since = now - timedelta(days=RECENT_REGISTRATION_DAYS)
    for doc in db.query(models.Document).filter(
        models.Document.originating_office_id == office_id,
        models.Document.archived.is_(False),
        models.Document.created_at >= since,
        models.Document.created_by != user.username,
    ):
        items.append(_item("registered", doc, _aware(doc.created_at), f"Registered into your office by {doc.created_by or 'someone'}.", doc.id))
    office_documents = db.query(models.Document).filter(models.Document.current_office_id == office_id)
    return items + _due_items(db, office_documents, today, with_office=False)


def _retention_items(db, now):
    """Archived documents due for deletion (priority) or due within RETENTION_WARNING_DAYS."""
    items = []
    for doc, until in documents_due(db, now):
        local_day = until.astimezone(LGU_TIMEZONE).strftime("%b %d, %Y")
        if until <= now:
            item = _item("retention_due", doc, until,
                         f"{doc.document_type} retention ended {local_day}. Delete it now or extend how long it is kept.", doc.id)
            item["priority"] = True
        else:
            item = _item("retention_soon", doc, until - timedelta(days=RETENTION_WARNING_DAYS),
                         f"{doc.document_type} is due for deletion on {local_day}.", doc.id)
        items.append(item)
    return items


def _temporary_items(db, today):
    """Archived temporary documents due for deletion (priority) or due within TEMPORARY_WARNING_DAYS."""
    items = []
    for entry in db.query(models.TemporaryDocument).filter(models.TemporaryDocument.scheduled_for < today):
        due = temporary_due_on(entry)
        if due > today + timedelta(days=TEMPORARY_WARNING_DAYS):
            continue
        doc = entry.document
        overdue = due <= today
        kind = "temporary_due" if overdue else "temporary_soon"
        day, local_day = entry.scheduled_for.strftime("%b %d"), due.strftime("%b %d, %Y")
        message = (f"Temporary document for {day}: its 30 days ended {local_day}. Delete it or keep it 30 more days."
                   if overdue else f"Temporary document for {day} is due for deletion on {local_day}.")
        items.append({
            "id": f"{kind}:{entry.id}", "kind": kind, "temporary_document_id": entry.id,
            "document_id": doc.id if doc else None, "tracking_number": doc.tracking_number if doc else "MOA",
            "title": doc.title if doc else entry.title, "message": message,
            "at": _day_start(due if overdue else due - timedelta(days=TEMPORARY_WARNING_DAYS)).isoformat(),
            "priority": overdue,
        })
    return items


def _system_items(db, now, today):
    items = []
    for handoff in _pending_handoffs(db):
        hours = _hours_waiting(handoff, now)
        if hours < QR_TRACKING_OVERDUE_HOURS:
            continue
        sender = handoff.sending_office.name if handoff.sending_office else "?"
        receiver = handoff.receiving_office.name if handoff.receiving_office else "?"
        at = _aware(handoff.sent_at) + timedelta(hours=QR_TRACKING_OVERDUE_HOURS)
        items.append(_item("handoff_overdue", handoff.document, at, f"{sender} → {receiver}, not received after {hours} hours.", handoff.id))
    return items + _due_items(db, db.query(models.Document), today, with_office=True)


@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """What needs the user's attention: their office's work, or system-wide problems for full-access users without an office."""
    now = datetime.now(timezone.utc)
    today = lgu_today()
    if normalize_user_role(current_user.role) == "SB Member":
        # SB Members see only the documents set for them, in the SB Member app.
        return {"unread": 0, "items": []}
    if current_user.office_id is not None:
        items = _office_items(db, current_user, now, today)
    elif user_has_permission(current_user, "view_document_details"):
        items = _system_items(db, now, today)
    else:
        items = []
    if user_has_permission(current_user, "delete_documents"):
        items += _retention_items(db, now)
    if user_has_permission(current_user, "set_documents_for_sb_members"):
        items += _temporary_items(db, today)
    items.sort(key=lambda item: item["at"], reverse=True)
    # Priority items come first and are never cut off by MAX_ITEMS.
    priority = [item for item in items if item.get("priority")]
    items = priority + [item for item in items if not item.get("priority")][:MAX_ITEMS]
    seen = _aware(current_user.notifications_seen_at)
    for item in items:
        item["unread"] = item.get("priority", False) or seen is None or datetime.fromisoformat(item["at"]) > seen
    return {"unread": sum(item["unread"] for item in items), "items": items}


@router.post("/notifications/seen")
def mark_notifications_seen(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user.id).one()
    user.notifications_seen_at = datetime.now(timezone.utc)
    db.commit()
    return {"unread": 0}
