"""SB position on SB Member accounts, so the member roster can be filled from the account"""

from alembic import op
import sqlalchemy as sa


revision = "0032_user_sb_position"
down_revision = "0031_document_action_required"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "sb_position" not in columns:
        op.add_column("users", sa.Column("sb_position", sa.String(60), nullable=True))


def downgrade():
    op.drop_column("users", "sb_position")
