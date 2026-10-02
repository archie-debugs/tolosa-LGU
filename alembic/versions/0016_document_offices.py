"""add document-office associations and backfill existing office links"""

from alembic import op
import sqlalchemy as sa


revision = "0016_document_offices"
down_revision = "0015_document_receipts"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "document_offices" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "document_offices",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("office_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["office_id"], ["offices.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("document_id", "office_id", name="uq_document_offices_document_office"),
        )
        op.create_index("ix_document_offices_id", "document_offices", ["id"], unique=False)
        op.create_index("ix_document_offices_document_id", "document_offices", ["document_id"], unique=False)
        op.create_index("ix_document_offices_office_id", "document_offices", ["office_id"], unique=False)

    bind.execute(sa.text(
        "INSERT INTO document_offices (document_id, office_id) "
        "SELECT documents.id, documents.current_office_id FROM documents "
        "JOIN offices ON offices.id = documents.current_office_id "
        "WHERE documents.current_office_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM document_offices "
        "WHERE document_offices.document_id = documents.id "
        "AND document_offices.office_id = documents.current_office_id)"
    ))


def downgrade():
    bind = op.get_bind()
    if "document_offices" not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_document_offices_office_id", table_name="document_offices")
    op.drop_index("ix_document_offices_document_id", table_name="document_offices")
    op.drop_index("ix_document_offices_id", table_name="document_offices")
    op.drop_table("document_offices")