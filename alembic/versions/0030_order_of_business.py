"""Order of business, outcomes and votes; stage changes link to the session"""

from alembic import op
import sqlalchemy as sa


revision = "0030_order_of_business"
down_revision = "0029_council_sessions_attendance"
branch_labels = None
depends_on = None


def _recorded():
    return [
        sa.Column("is_correction", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recorded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if "session_items" not in existing:
        op.create_table(
            "session_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("council_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("section", sa.String(length=30), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("added_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("session_id", "document_id", name="uq_session_items_session_document"),
        )
        op.create_index("ix_session_items_session_id", "session_items", ["session_id"])
        op.create_index("ix_session_items_document_id", "session_items", ["document_id"])
    if "session_item_outcomes" not in existing:
        op.create_table(
            "session_item_outcomes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("session_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("outcome", sa.String(length=40), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("committee_id", sa.Integer(), sa.ForeignKey("committees.id"), nullable=True),
            sa.Column("document_number", sa.String(length=40), nullable=True),
            sa.Column("series_year", sa.Integer(), nullable=True),
            sa.Column("stage_before", sa.String(length=40), nullable=True),
            sa.Column("applied_stages", sa.Text(), nullable=True),
            *_recorded(),
        )
        op.create_index("ix_session_item_outcomes_item_id", "session_item_outcomes", ["item_id"])
    if "session_item_votes" not in existing:
        op.create_table(
            "session_item_votes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("session_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("method", sa.String(length=10), nullable=False),
            sa.Column("yes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("no", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("abstain", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("result", sa.String(length=10), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            *_recorded(),
            sa.CheckConstraint("method IN ('Voice', 'Nominal')", name="ck_session_item_votes_method"),
            sa.CheckConstraint("result IN ('Carried', 'Lost')", name="ck_session_item_votes_result"),
        )
        op.create_index("ix_session_item_votes_item_id", "session_item_votes", ["item_id"])
    if "session_member_votes" not in existing:
        op.create_table(
            "session_member_votes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("vote_id", sa.Integer(), sa.ForeignKey("session_item_votes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("member_id", sa.Integer(), sa.ForeignKey("council_members.id"), nullable=False),
            sa.Column("vote", sa.String(length=10), nullable=False),
            sa.CheckConstraint("vote IN ('Yes', 'No', 'Abstain')", name="ck_session_member_votes_vote"),
        )
        op.create_index("ix_session_member_votes_vote_id", "session_member_votes", ["vote_id"])
    if "session_id" not in {column["name"] for column in inspector.get_columns("document_stage_changes")}:
        with op.batch_alter_table("document_stage_changes") as batch:
            batch.add_column(sa.Column("session_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_document_stage_changes_session_id", "council_sessions", ["session_id"], ["id"], ondelete="SET NULL")
            batch.create_index("ix_document_stage_changes_session_id", ["session_id"])


def downgrade():
    with op.batch_alter_table("document_stage_changes") as batch:
        batch.drop_index("ix_document_stage_changes_session_id")
        batch.drop_constraint("fk_document_stage_changes_session_id", type_="foreignkey")
        batch.drop_column("session_id")
    op.drop_table("session_member_votes")
    op.drop_table("session_item_votes")
    op.drop_table("session_item_outcomes")
    op.drop_table("session_items")
