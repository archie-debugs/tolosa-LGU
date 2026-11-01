"""Retention of archived documents: the date someone extended an archived document to"""

from alembic import op
import sqlalchemy as sa


revision = "0034_document_retention"
down_revision = "0033_per_type_tracking_numbers"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "retention_extended_until" not in columns:
        op.add_column("documents", sa.Column("retention_extended_until", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("documents", "retention_extended_until")
