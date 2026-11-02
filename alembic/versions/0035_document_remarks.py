"""Remark history: every remark added to a document, instead of one overwritten remark.

Each document's existing remark becomes its first entry, written by whoever registered it.
"""

from alembic import op
import sqlalchemy as sa


revision = "0035_document_remarks"
down_revision = "0034_document_retention"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "document_remarks" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "document_remarks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("author", sa.String(), nullable=True),
            sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_document_remarks_id", "document_remarks", ["id"])
        op.create_index("ix_document_remarks_document_id", "document_remarks", ["document_id"])
    bind.execute(sa.text(
        """
        INSERT INTO document_remarks (document_id, text, author, author_id, created_at)
        SELECT d.id, d.remarks, d.created_by, d.created_by_id, COALESCE(d.updated_at, d.created_at, CURRENT_TIMESTAMP)
        FROM documents d
        WHERE d.remarks IS NOT NULL AND TRIM(d.remarks) <> ''
          AND NOT EXISTS (SELECT 1 FROM document_remarks r WHERE r.document_id = d.id)
        """
    ))


def downgrade():
    op.drop_index("ix_document_remarks_document_id", table_name="document_remarks")
    op.drop_index("ix_document_remarks_id", table_name="document_remarks")
    op.drop_table("document_remarks")
