"""Action required on documents: what the SB has to do with it (For Agenda, Posting, Approval…)"""

from alembic import op
import sqlalchemy as sa


revision = "0031_document_action_required"
down_revision = "0030_order_of_business"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "action_required" not in columns:
        op.add_column("documents", sa.Column("action_required", sa.String(), nullable=True))


def downgrade():
    op.drop_column("documents", "action_required")
