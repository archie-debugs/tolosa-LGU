"""Temporary documents: ordinances and uploaded MOAs set for SB Members for one day only."""

from alembic import op
import sqlalchemy as sa


revision = "0036_temporary_documents"
down_revision = "0035_document_remarks"
branch_labels = None
depends_on = None


def upgrade():
    if "temporary_documents" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "temporary_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("stored_path", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("kept_until", sa.Date(), nullable=True),
        sa.Column("added_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scheduled_for", "document_id", name="uq_temporary_documents_date_document"),
    )
    op.create_index("ix_temporary_documents_scheduled_for", "temporary_documents", ["scheduled_for"])
    op.create_index("ix_temporary_documents_document_id", "temporary_documents", ["document_id"])


def downgrade():
    op.drop_index("ix_temporary_documents_document_id", table_name="temporary_documents")
    op.drop_index("ix_temporary_documents_scheduled_for", table_name="temporary_documents")
    op.drop_table("temporary_documents")
