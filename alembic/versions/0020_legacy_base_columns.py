"""bring pre-Alembic base tables up to the current model

The base tables (users, documents, registration_requests, audit_logs) predate
Alembic, and their later columns used to be patched in by ad-hoc ALTER TABLE
statements on every startup. This migration performs those patches once.

Every step is guarded, because databases that ran the startup patches already
have some or all of these columns.
"""

import secrets

from alembic import op
import sqlalchemy as sa


revision = "0020_legacy_base_columns"
down_revision = "0019_document_action_received"
branch_labels = None
depends_on = None


def _legacy_columns():
    """(column, indexed) pairs per table, built fresh because a Column attaches to one table only.

    NOT NULL columns carry a server default so existing rows stay valid.
    """
    return {
        "users": [
            (sa.Column("role", sa.String(), nullable=False, server_default="Employee"), False),
            (sa.Column("full_name", sa.String(), nullable=True), False),
            (sa.Column("email", sa.String(), nullable=True), True),
            (sa.Column("permissions", sa.Text(), nullable=True), False),
            (sa.Column("status", sa.String(), nullable=False, server_default="Active"), True),
            (sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), True),
            (sa.Column("last_login", sa.DateTime(), nullable=True), True),
            (sa.Column("created_at", sa.DateTime(), nullable=True), True),
            (sa.Column("updated_at", sa.DateTime(), nullable=True), True),
        ],
        "registration_requests": [
            (sa.Column("assigned_role", sa.String(), nullable=True), False),
            (sa.Column("approved_by", sa.String(), nullable=True), True),
            (sa.Column("approved_at", sa.DateTime(), nullable=True), True),
            (sa.Column("rejected_by", sa.String(), nullable=True), True),
            (sa.Column("rejected_at", sa.DateTime(), nullable=True), True),
        ],
        "documents": [
            (sa.Column("document_number", sa.String(), nullable=True), False),
            (sa.Column("series_year", sa.Integer(), nullable=True), False),
            (sa.Column("description", sa.Text(), nullable=True), False),
            (sa.Column("document_type", sa.String(), nullable=True), True),
            (sa.Column("category", sa.String(), nullable=True), True),
            (sa.Column("originating_office", sa.String(), nullable=True), True),
            (sa.Column("current_office", sa.String(), nullable=True), True),
            (sa.Column("assigned_to", sa.String(), nullable=True), True),
            (sa.Column("status", sa.String(), nullable=False, server_default="Approved"), True),
            (sa.Column("priority", sa.String(), nullable=False, server_default="Medium"), True),
            (sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()), True),
            (sa.Column("remarks", sa.Text(), nullable=True), False),
            (sa.Column("author", sa.String(), nullable=True), True),
            (sa.Column("session", sa.String(), nullable=True), True),
            (sa.Column("date_registered", sa.String(), nullable=True), True),
            (sa.Column("attachment_name", sa.String(), nullable=True), False),
            (sa.Column("qr_code_value", sa.String(), nullable=True), True),
            (sa.Column("created_by", sa.String(), nullable=True), True),
            (sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()), True),
            (sa.Column("archived_at", sa.DateTime(), nullable=True), True),
            (sa.Column("archived_by", sa.String(), nullable=True), True),
            (sa.Column("created_at", sa.DateTime(), nullable=True), True),
            (sa.Column("updated_at", sa.DateTime(), nullable=True), True),
        ],
    }


def _create_registration_requests():
    op.create_table(
        "registration_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registration_reference", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("middle_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("suffix", sa.String(), nullable=True),
        sa.Column("contact_number", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("office", sa.String(), nullable=True),
        sa.Column("position", sa.String(), nullable=True),
        sa.Column("requested_access", sa.String(), nullable=True),
        sa.Column("assigned_role", sa.String(), nullable=True),
        sa.Column("id_type", sa.String(), nullable=True),
        sa.Column("id_number", sa.String(), nullable=True),
        sa.Column("id_file_path", sa.String(), nullable=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_by", sa.String(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_registration_requests_id", "registration_requests", ["id"])
    op.create_index("ix_registration_requests_registration_reference", "registration_requests", ["registration_reference"], unique=True)
    for column in ("email", "username", "status", "reviewed_by", "reviewed_at", "approved_by", "approved_at",
                   "rejected_by", "rejected_at", "created_at", "updated_at"):
        op.create_index(f"ix_registration_requests_{column}", "registration_requests", [column])


def _create_audit_logs():
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    for column in ("id", "actor", "action", "target_type", "target_id", "created_at"):
        op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])


def _add_missing_columns(inspector, table_name, columns):
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    for column, indexed in columns:
        if column.name in existing_columns:
            continue
        op.add_column(table_name, column)
        index_name = f"ix_{table_name}_{column.name}"
        if indexed and index_name not in existing_indexes:
            op.create_index(index_name, table_name, [column.name])


def _ensure_document_qr_tokens(bind, inspector):
    if "qr_token" not in {column["name"] for column in inspector.get_columns("documents")}:
        op.add_column("documents", sa.Column("qr_token", sa.String(length=64), nullable=True))
    for (document_id,) in bind.execute(sa.text("SELECT id FROM documents WHERE qr_token IS NULL OR qr_token = ''")).fetchall():
        token = secrets.token_urlsafe(32)
        while bind.execute(sa.text("SELECT 1 FROM documents WHERE qr_token = :token"), {"token": token}).fetchone() is not None:
            token = secrets.token_urlsafe(32)
        bind.execute(sa.text("UPDATE documents SET qr_token = :token WHERE id = :id"), {"token": token, "id": document_id})
    if "ix_documents_qr_token" not in {index["name"] for index in sa.inspect(bind).get_indexes("documents")}:
        op.create_index("ix_documents_qr_token", "documents", ["qr_token"], unique=True)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "registration_requests" not in table_names:
        _create_registration_requests()
    if "audit_logs" not in table_names:
        _create_audit_logs()

    inspector = sa.inspect(bind)
    for table_name, columns in _legacy_columns().items():
        _add_missing_columns(inspector, table_name, columns)
    _ensure_document_qr_tokens(bind, sa.inspect(bind))

    # Data clean-ups that used to run on every startup.
    bind.execute(sa.text("UPDATE users SET role = 'Super Administrator' WHERE lower(role) = 'admin'"))
    bind.execute(sa.text("UPDATE users SET role = 'Employee' WHERE lower(role) IN ('staff', 'secretary', 'secretary / vice mayor')"))
    bind.execute(sa.text("UPDATE users SET status = 'Active' WHERE status IS NULL OR status = ''"))
    bind.execute(sa.text("UPDATE users SET is_active = TRUE WHERE is_active IS NULL"))
    bind.execute(sa.text("UPDATE users SET permissions = '[]' WHERE permissions IS NULL"))
    bind.execute(sa.text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))


def downgrade():
    # The columns may predate this migration, so dropping them could destroy data.
    pass
