"""Retention of archived documents: how long each one is kept, and which are due for deletion.

The clock starts when a document is archived. Its type's retention_months system setting says how
long it is kept (None keeps it permanently); someone may extend one document past that. Nothing is
deleted on its own: a due document waits in notifications until someone deletes or extends it.
"""
import calendar
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import models
from .routes.settings import retention_months
from .tracking_numbers import standard_document_type

# How long before its date a document shows up as due for deletion soon.
RETENTION_WARNING_DAYS = 30
# The longest one extension may add.
MAX_EXTENSION_MONTHS = 120


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def add_months(moment: datetime, months: int) -> datetime:
    """`moment` plus `months` calendar months; the 31st becomes the month's last day when it has none."""
    index = moment.month - 1 + months
    year, month = moment.year + index // 12, index % 12 + 1
    return moment.replace(year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1]))


def retain_until(doc: models.Document, retention: dict) -> datetime | None:
    """When an archived document is due for deletion; None when it is not archived or is kept permanently."""
    if not doc.archived or doc.archived_at is None:
        return None
    months = retention.get(standard_document_type(doc.document_type))
    if months is None:
        return None
    due = add_months(_aware(doc.archived_at), months)
    extended = _aware(doc.retention_extended_until)
    return max(due, extended) if extended else due


def documents_due(db: Session, now: datetime, within_days: int = RETENTION_WARNING_DAYS) -> list[tuple[models.Document, datetime]]:
    """Archived documents due for deletion by `within_days` from now, with their dates, soonest first."""
    retention = retention_months(db)
    kept_for_a_time = [document_type for document_type, months in retention.items() if months is not None]
    if not kept_for_a_time:
        return []
    horizon = now + timedelta(days=within_days)
    due = []
    for doc in db.query(models.Document).filter(models.Document.archived.is_(True), models.Document.document_type.in_(kept_for_a_time)):
        until = retain_until(doc, retention)
        if until is not None and until <= horizon:
            due.append((doc, until))
    due.sort(key=lambda pair: pair[1])
    return due


def extend_retention(db: Session, doc: models.Document, months: int, now: datetime) -> datetime:
    """Keep `doc` `months` longer, counted from its current date or from now when that has passed."""
    until = retain_until(doc, retention_months(db))
    if until is None:
        raise ValueError("Only an archived document with a retention period can be extended.")
    doc.retention_extended_until = add_months(max(until, now), months)
    return doc.retention_extended_until
