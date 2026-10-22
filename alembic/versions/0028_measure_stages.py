"""A measure's legislative stage and its stage history"""

from alembic import op
import sqlalchemy as sa


revision = "0028_measure_stages"
down_revision = "0027_council_members_committees"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "stage" not in {column["name"] for column in inspector.get_columns("documents")}:
        op.add_column("documents", sa.Column("stage", sa.String(length=40), nullable=True))
        op.create_index("ix_documents_stage", "documents", ["stage"])
    if "document_stage_changes" not in inspector.get_table_names():
        op.create_table(
            "document_stage_changes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stage", sa.String(length=40), nullable=False),
            sa.Column("previous_stage", sa.String(length=40), nullable=True),
            sa.Column("effective_on", sa.Date(), nullable=False),
            sa.Column("committee_id", sa.Integer(), sa.ForeignKey("committees.id"), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("is_correction", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("changed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("changed_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_document_stage_changes_document_id", "document_stage_changes", ["document_id"])


def downgrade():
    op.drop_table("document_stage_changes")
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_index("ix_documents_stage")
        batch_op.drop_column("stage")
