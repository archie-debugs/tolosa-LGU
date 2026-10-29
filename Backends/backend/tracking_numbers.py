"""Tracking numbers: each document type counts on its own, ORD-000001, RES-000001, LTR-000001."""
import re

from sqlalchemy import Sequence, text
from sqlalchemy.orm import Session

from .database import Base

# The only document types a document can have, with the prefix of their tracking numbers.
TRACKING_PREFIXES = {"Ordinance": "ORD", "Resolution": "RES", "Letter Request": "LTR"}
DOCUMENT_TYPES = list(TRACKING_PREFIXES)

# One PostgreSQL sequence per type, so a number is never handed out twice, even after a delete.
TRACKING_SEQUENCES = {
    prefix: Sequence(f"{prefix.lower()}_tracking_number_seq", start=1, increment=1, minvalue=1, metadata=Base.metadata)
    for prefix in TRACKING_PREFIXES.values()
}

TRACKING_QUERY_PATTERN = re.compile(r"(?i)(?:(ORD|RES|LTR)[-\s]*)?0*([1-9][0-9]*)")


def standard_document_type(name: str | None) -> str | None:
    """The standard spelling of a document type, or None when it is not one of the three."""
    folded = " ".join((name or "").split()).lower()
    return next((standard for standard in DOCUMENT_TYPES if standard.lower() == folded), None)


def format_tracking_number(prefix: str, value: int) -> str:
    return f"{prefix}-{int(value):06d}"


def next_tracking_number(db: Session, document_type: str) -> str:
    """The next unused tracking number in `document_type`'s own series."""
    prefix = TRACKING_PREFIXES[document_type]
    if db.bind and db.bind.dialect.name == "sqlite":
        # SQLite (tests only) has no sequences: count on from the highest number given so far.
        highest = db.execute(
            text("SELECT COALESCE(MAX(CAST(SUBSTR(tracking_number, 5) AS INTEGER)), 0) FROM documents WHERE tracking_number LIKE :prefix"),
            {"prefix": f"{prefix}-%"},
        ).scalar_one()
        return format_tracking_number(prefix, int(highest) + 1)
    value = db.execute(text(f"SELECT nextval('{TRACKING_SEQUENCES[prefix].name}')")).scalar_one()
    return format_tracking_number(prefix, value)


def tracking_numbers_for_query(search: str | None) -> list[str]:
    """The tracking numbers a search means: "ORD-12" or "ord 12" one, a bare "12" one in every series."""
    match = TRACKING_QUERY_PATTERN.fullmatch(str(search or "").strip())
    if not match:
        return []
    prefix, value = match.groups()
    prefixes = [prefix.upper()] if prefix else list(TRACKING_PREFIXES.values())
    return [format_tracking_number(each, int(value)) for each in prefixes]
