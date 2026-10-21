"""Store every timestamp with its time zone

The naive columns below received timezone-aware UTC values, which PostgreSQL saved as the
session's local time (the server's TimeZone) and the app read back as UTC. The app's
sessions now run in UTC (database.py), so the existing rows are converted using the zone
they were written in: the server default, read from a session without that override.
SQLite stores both kinds the same way, so there is nothing to do there.
"""

import re

from alembic import op
import sqlalchemy as sa


revision = "0026_timezone_aware_timestamps"
down_revision = "0025_handoff_cancel_return"
branch_labels = None
depends_on = None

COLUMNS = {
    "attachments": ["created_at"],
    "audit_logs": ["created_at"],
    # Older databases have a legacy document_history with a "timestamp" column instead.
    "document_history": ["created_at", "timestamp"],
    "documents": ["archived_at", "created_at", "updated_at"],
    "legislative_tracking_logs": ["timestamp"],  # legacy table, not in the models
    "registration_requests": ["reviewed_at", "approved_at", "rejected_at", "created_at", "updated_at"],
    "system_settings": ["updated_at"],
    "user_sessions": ["created_at", "last_activity", "expires_at", "revoked_at"],
    "users": ["last_login", "created_at", "updated_at"],
}


def _written_zone(bind) -> str:
    """The TimeZone app sessions had before they were pinned to UTC."""
    engine = sa.create_engine(bind.engine.url)
    try:
        with engine.connect() as connection:
            zone = connection.execute(sa.text("SHOW timezone")).scalar()
    finally:
        engine.dispose()
    if not re.fullmatch(r"[A-Za-z0-9_+\-/:]+", zone or ""):
        raise RuntimeError(f"Unexpected server TimeZone {zone!r}")
    return zone


def _columns(bind, to_aware: bool):
    """(table, column) pairs that exist and still need converting to (or, for a downgrade, from) timestamptz."""
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, names in COLUMNS.items():
        if table not in tables:
            continue
        types = {column["name"]: column["type"] for column in inspector.get_columns(table)}
        for name in names:
            kind = types.get(name)
            if isinstance(kind, sa.DateTime) and bool(kind.timezone) != to_aware:
                yield table, name


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    pending = list(_columns(bind, to_aware=True))
    if not pending:
        return
    zone = _written_zone(bind)
    for table, name in pending:
        op.execute(sa.text(
            f'ALTER TABLE {table} ALTER COLUMN "{name}" TYPE TIMESTAMP WITH TIME ZONE USING "{name}" AT TIME ZONE \'{zone}\''
        ))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    pending = list(_columns(bind, to_aware=False))
    if not pending:
        return
    zone = _written_zone(bind)
    for table, name in pending:
        op.execute(sa.text(
            f'ALTER TABLE {table} ALTER COLUMN "{name}" TYPE TIMESTAMP WITHOUT TIME ZONE USING "{name}" AT TIME ZONE \'{zone}\''
        ))
