"""prepare dedicated display tracking IDs and historical aliases"""
from alembic import op
import sqlalchemy as sa


revision = "0011_tracking_alias_seq"
down_revision = "0010_doc_legislative_meta"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_tracking_number_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("tracking_number", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_tracking_number_alias_document",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tracking_number", name="uq_tracking_number_alias_tracking_number"),
        sa.UniqueConstraint("document_id", "tracking_number", name="uq_tracking_number_alias_document_tracking"),
    )
    op.create_index(
        "ix_document_tracking_number_aliases_document_id",
        "document_tracking_number_aliases",
        ["document_id"],
    )
    op.create_index(
        "ix_document_tracking_number_aliases_tracking_number",
        "document_tracking_number_aliases",
        ["tracking_number"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.schema.CreateSequence(sa.Sequence("document_tracking_number_seq", start=1, increment=1, minvalue=1)))

    op.execute(
        sa.text(
            "INSERT INTO document_tracking_number_aliases (document_id, tracking_number) "
            "SELECT id, tracking_number FROM documents"
        )
    )


def downgrade():
    bind = op.get_bind()
    op.drop_index("ix_document_tracking_number_aliases_tracking_number", table_name="document_tracking_number_aliases")
    op.drop_index("ix_document_tracking_number_aliases_document_id", table_name="document_tracking_number_aliases")
    op.drop_table("document_tracking_number_aliases")
    if bind.dialect.name == "postgresql":
        op.execute(sa.schema.DropSequence(sa.Sequence("document_tracking_number_seq")))