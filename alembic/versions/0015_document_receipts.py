"""add document receipt confirmations by office"""

from alembic import op
import sqlalchemy as sa


revision = "0015_document_receipts"
down_revision = "0014_stable_document_qr_token"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    table_names = set(bind.dialect.get_table_names(bind))
    if "document_receipts" in table_names:
        return

    op.create_table(
        "document_receipts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="Received"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index(op.f("ix_document_receipts_document_id"), "document_receipts", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_receipts_office_id"), "document_receipts", ["office_id"], unique=False)
    op.create_index(op.f("ix_document_receipts_confirmed_by_user_id"), "document_receipts", ["confirmed_by_user_id"], unique=False)
    op.create_index(op.f("ix_document_receipts_status"), "document_receipts", ["status"], unique=False)
    op.create_index(op.f("ix_document_receipts_confirmed_at"), "document_receipts", ["confirmed_at"], unique=False)
    op.create_index(op.f("ix_document_receipts_created_at"), "document_receipts", ["created_at"], unique=False)
    op.create_index(op.f("ix_document_receipts_updated_at"), "document_receipts", ["updated_at"], unique=False)
    op.create_unique_constraint("uq_document_receipts_document_office", "document_receipts", ["document_id", "office_id"])


def downgrade():
    bind = op.get_bind()
    table_names = set(bind.dialect.get_table_names(bind))
    if "document_receipts" not in table_names:
        return

    op.drop_constraint("uq_document_receipts_document_office", "document_receipts", type_="unique")
    op.drop_index(op.f("ix_document_receipts_updated_at"), table_name="document_receipts")
    op.drop_index(op.f("ix_document_receipts_created_at"), table_name="document_receipts")
    op.drop_index(op.f("ix_document_receipts_confirmed_at"), table_name="document_receipts")
    op.drop_index(op.f("ix_document_receipts_status"), table_name="document_receipts")
    op.drop_index(op.f("ix_document_receipts_confirmed_by_user_id"), table_name="document_receipts")
    op.drop_index(op.f("ix_document_receipts_office_id"), table_name="document_receipts")
    op.drop_index(op.f("ix_document_receipts_document_id"), table_name="document_receipts")
    op.drop_table("document_receipts")
