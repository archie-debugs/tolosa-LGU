"""Notifications: when each user last looked at their notifications"""

from alembic import op
import sqlalchemy as sa


revision = "0023_notifications_seen_at"
down_revision = "0022_document_due_date"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "notifications_seen_at" not in columns:
        op.add_column("users", sa.Column("notifications_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("users", "notifications_seen_at")
