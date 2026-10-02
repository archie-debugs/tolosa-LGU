"""add document handoff workflow and link receipts to handoffs"""

from alembic import op
import sqlalchemy as sa


revision = "0017_document_handoffs"
down_revision = "0016_document_offices"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    table_names = set(sa.inspect(bind).get_table_names())

    if "document_handoffs" not in table_names:
        op.create_table(
            "document_handoffs",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("sending_office_id", sa.Integer(), nullable=False),
            sa.Column("receiving_office_id", sa.Integer(), nullable=False),
            sa.Column("sending_employee_id", sa.Integer(), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="Pending Receipt"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["sending_office_id"], ["offices.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["receiving_office_id"], ["offices.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["sending_employee_id"], ["users.id"], ondelete="SET NULL"),
            sa.CheckConstraint("sending_office_id <> receiving_office_id", name="ck_document_handoffs_sender_receiver_diff"),
            sa.CheckConstraint("status IN ('Pending Receipt', 'Received')", name="ck_document_handoffs_status"),
        )
        op.create_index("ix_document_handoffs_document_id", "document_handoffs", ["document_id"], unique=False)
        op.create_index("ix_document_handoffs_sending_office_id", "document_handoffs", ["sending_office_id"], unique=False)
        op.create_index("ix_document_handoffs_receiving_office_id", "document_handoffs", ["receiving_office_id"], unique=False)
        op.create_index("ix_document_handoffs_status", "document_handoffs", ["status"], unique=False)
        op.create_index("ix_document_handoffs_sent_at", "document_handoffs", ["sent_at"], unique=False)
        op.create_index("ix_document_handoffs_created_at", "document_handoffs", ["created_at"], unique=False)
        op.create_index("ix_document_handoffs_updated_at", "document_handoffs", ["updated_at"], unique=False)
        if bind.dialect.name != "sqlite":
            op.execute(sa.text("CREATE UNIQUE INDEX uq_document_handoffs_pending_receipt ON document_handoffs (document_id) WHERE status = 'Pending Receipt'"))

    if "handoff_id" not in [c.name for c in sa.inspect(bind).get_columns("document_receipts")]:
        op.add_column("document_receipts", sa.Column("handoff_id", sa.Integer(), nullable=True))
        op.create_index("ix_document_receipts_handoff_id", "document_receipts", ["handoff_id"], unique=False)
        op.create_foreign_key(
            "fk_document_receipts_handoff_id",
            "document_receipts",
            "document_handoffs",
            ["handoff_id"],
            ["id"],
            ondelete="SET NULL",
        )

    existing_unique = False
    for constraint in sa.inspect(bind).get_unique_constraints("document_receipts"):
        if constraint.get("name") == "uq_document_receipts_document_office":
            existing_unique = True
            break
    if existing_unique:
        op.drop_constraint("uq_document_receipts_document_office", "document_receipts", type_="unique")
    if "uq_document_receipts_handoff" not in {c.get("name") for c in sa.inspect(bind).get_unique_constraints("document_receipts")}:
        op.create_unique_constraint("uq_document_receipts_handoff", "document_receipts", ["handoff_id"])


def downgrade():
    bind = op.get_bind()
    if "document_receipts" in sa.inspect(bind).get_table_names():
        for constraint in sa.inspect(bind).get_unique_constraints("document_receipts"):
            if constraint.get("name") == "uq_document_receipts_handoff":
                op.drop_constraint("uq_document_receipts_handoff", "document_receipts", type_="unique")
                break
        op.drop_constraint("fk_document_receipts_handoff_id", "document_receipts", type_="foreignkey")
        op.drop_index(op.f("ix_document_receipts_handoff_id"), table_name="document_receipts")
        op.drop_column("document_receipts", "handoff_id")

    if "document_handoffs" in sa.inspect(bind).get_table_names():
        if bind.dialect.name != "sqlite":
            op.execute(sa.text("DROP INDEX IF EXISTS uq_document_handoffs_pending_receipt"))
        op.drop_index("ix_document_handoffs_updated_at", table_name="document_handoffs")
        op.drop_index("ix_document_handoffs_created_at", table_name="document_handoffs")
        op.drop_index("ix_document_handoffs_sent_at", table_name="document_handoffs")
        op.drop_index("ix_document_handoffs_status", table_name="document_handoffs")
        op.drop_index("ix_document_handoffs_receiving_office_id", table_name="document_handoffs")
        op.drop_index("ix_document_handoffs_sending_office_id", table_name="document_handoffs")
        op.drop_index("ix_document_handoffs_document_id", table_name="document_handoffs")
        op.drop_constraint("ck_document_handoffs_status", "document_handoffs", type_="check")
        op.drop_constraint("ck_document_handoffs_sender_receiver_diff", "document_handoffs", type_="check")
        op.drop_table("document_handoffs")
