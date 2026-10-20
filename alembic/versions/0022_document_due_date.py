"""Due dates on documents: when a document needs to be acted on"""

from alembic import op
import sqlalchemy as sa


revision = "0022_document_due_date"
down_revision = "0021_todays_documents"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "due_date" not in columns:
        op.add_column("documents", sa.Column("due_date", sa.Date(), nullable=True))
        op.create_index("ix_documents_due_date", "documents", ["due_date"])


def downgrade():
    op.drop_index("ix_documents_due_date", table_name="documents")
    op.drop_column("documents", "due_date")
