"""Let a deleted user's handoffs and receipts keep their history.

Both columns already have ON DELETE SET NULL but were NOT NULL, so deleting any employee
who sent a handoff or confirmed a receipt failed.
"""

from alembic import op
import sqlalchemy as sa


revision = "0037_user_delete_keeps_handoffs"
down_revision = "0036_temporary_documents"
branch_labels = None
depends_on = None

COLUMNS = (("document_handoffs", "sending_employee_id"), ("document_receipts", "confirmed_by_user_id"))


def upgrade():
    for table, column in COLUMNS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(column, existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Fails while any row has a blank user; those rows came from deleted accounts.
    for table, column in COLUMNS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(column, existing_type=sa.Integer(), nullable=False)
