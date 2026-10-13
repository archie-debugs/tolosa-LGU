"""allow Received document actions"""

from alembic import op


revision = "0019_document_action_received"
down_revision = "0018_document_actions"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_document_actions_action_type",
        "document_actions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_document_actions_action_type",
        "document_actions",
        "action_type IN ('Received', 'Signed', 'Reviewed', 'Approved', 'Noted', 'Other')",
    )


def downgrade():
    op.drop_constraint(
        "ck_document_actions_action_type",
        "document_actions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_document_actions_action_type",
        "document_actions",
        "action_type IN ('Signed', 'Reviewed', 'Approved', 'Noted', 'Other')",
    )
