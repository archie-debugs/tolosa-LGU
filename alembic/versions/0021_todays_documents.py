"""Today's Documents: documents employees set for SB Members per day

Also retires the document-request permissions, which never had a feature behind them:
employees' request-handling permissions become set_documents_for_sb_members, and SB Members'
request permissions are removed.
"""

import ast
import json

from alembic import op
import sqlalchemy as sa


revision = "0021_todays_documents"
down_revision = "0020_legacy_base_columns"
branch_labels = None
depends_on = None

EMPLOYEE_REQUEST_PERMISSIONS = {
    "view_document_requests",
    "approve_document_requests",
    "reject_document_requests",
    "fulfill_document_requests",
}
SB_MEMBER_REQUEST_PERMISSIONS = {
    "request_documents",
    "view_own_document_requests",
    "cancel_own_pending_requests",
}


def _parse_permissions(value):
    text = (value or "").strip()
    if not text:
        return []
    for parse in (json.loads, ast.literal_eval):
        try:
            parsed = parse(text)
        except Exception:
            continue
        if isinstance(parsed, (list, tuple, set)):
            return [str(item) for item in parsed]
    return None


def _rewrite_permissions(bind):
    retired = EMPLOYEE_REQUEST_PERMISSIONS | SB_MEMBER_REQUEST_PERMISSIONS
    for user_id, value in bind.execute(sa.text("SELECT id, permissions FROM users")).fetchall():
        permissions = _parse_permissions(value)
        if permissions is None or not retired.intersection(permissions):
            continue
        updated = [permission for permission in permissions if permission not in retired]
        if EMPLOYEE_REQUEST_PERMISSIONS.intersection(permissions) and "set_documents_for_sb_members" not in updated:
            updated.append("set_documents_for_sb_members")
        bind.execute(sa.text("UPDATE users SET permissions = :permissions WHERE id = :id"), {"permissions": str(updated), "id": user_id})


def upgrade():
    bind = op.get_bind()
    if "todays_documents" not in sa.inspect(bind).get_table_names():
        _create_table()
    _rewrite_permissions(bind)


def _create_table():
    op.create_table(
        "todays_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("added_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("scheduled_for", "document_id", name="uq_todays_documents_date_document"),
    )
    op.create_index("ix_todays_documents_scheduled_for", "todays_documents", ["scheduled_for"])
    op.create_index("ix_todays_documents_document_id", "todays_documents", ["document_id"])
    op.create_index("ix_todays_documents_scheduled_for_position", "todays_documents", ["scheduled_for", "position"])


def downgrade():
    op.drop_index("ix_todays_documents_scheduled_for_position", table_name="todays_documents")
    op.drop_index("ix_todays_documents_document_id", table_name="todays_documents")
    op.drop_index("ix_todays_documents_scheduled_for", table_name="todays_documents")
    op.drop_table("todays_documents")
