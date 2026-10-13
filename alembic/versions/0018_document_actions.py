"""add document action records"""

from alembic import op
import sqlalchemy as sa


revision = "0018_document_actions"
down_revision = "0017_document_handoffs"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "document_actions" in sa.inspect(bind).get_table_names():
        return

    op.create_table(
        "document_actions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("handoff_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["handoff_id"], ["document_handoffs.id"]),
        sa.CheckConstraint(
            "action_type IN ('Signed', 'Reviewed', 'Approved', 'Noted', 'Other')",
            name="ck_document_actions_action_type",
        ),
    )

    op.create_index("ix_document_actions_id", "document_actions", ["id"], unique=False)
    op.create_index("ix_document_actions_document_id", "document_actions", ["document_id"], unique=False)
    op.create_index("ix_document_actions_office_id", "document_actions", ["office_id"], unique=False)
    op.create_index("ix_document_actions_employee_id", "document_actions", ["employee_id"], unique=False)
    op.create_index("ix_document_actions_handoff_id", "document_actions", ["handoff_id"], unique=False)
    op.create_index("ix_document_actions_action_type", "document_actions", ["action_type"], unique=False)
    op.create_index("ix_document_actions_performed_at", "document_actions", ["performed_at"], unique=False)
    op.create_index("ix_document_actions_created_at", "document_actions", ["created_at"], unique=False)
    op.create_index(
        "ix_document_actions_document_performed",
        "document_actions",
        ["document_id", "performed_at", "id"],
        unique=False,
    )


def downgrade():
    bind = op.get_bind()
    if "document_actions" not in sa.inspect(bind).get_table_names():
        return

    op.drop_index("ix_document_actions_document_performed", table_name="document_actions")
    op.drop_index("ix_document_actions_created_at", table_name="document_actions")
    op.drop_index("ix_document_actions_performed_at", table_name="document_actions")
    op.drop_index("ix_document_actions_action_type", table_name="document_actions")
    op.drop_index("ix_document_actions_handoff_id", table_name="document_actions")
    op.drop_index("ix_document_actions_employee_id", table_name="document_actions")
    op.drop_index("ix_document_actions_office_id", table_name="document_actions")
    op.drop_index("ix_document_actions_document_id", table_name="document_actions")
    op.drop_index("ix_document_actions_id", table_name="document_actions")
    op.drop_table("document_actions")
