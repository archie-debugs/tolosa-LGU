"""SB terms, the member roster and committees"""

from alembic import op
import sqlalchemy as sa


revision = "0027_council_members_committees"
down_revision = "0026_timezone_aware_timestamps"
branch_labels = None
depends_on = None

POSITIONS = (
    "position IN ('Vice Mayor', 'Regular Member', 'Liga ng mga Barangay President', "
    "'SK Federation President', 'IPMR')"
)


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "council_terms" not in existing:
        op.create_table(
            "council_terms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False, unique=True),
            sa.Column("starts_on", sa.Date(), nullable=False),
            sa.Column("ends_on", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "council_members" not in existing:
        op.create_table(
            "council_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("term_id", sa.Integer(), sa.ForeignKey("council_terms.id"), nullable=False),
            sa.Column("full_name", sa.String(length=160), nullable=False),
            sa.Column("position", sa.String(length=60), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("left_on", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(POSITIONS, name="ck_council_members_position"),
        )
        op.create_index("ix_council_members_term_id", "council_members", ["term_id"])
        op.create_index("ix_council_members_user_id", "council_members", ["user_id"])
    if "committees" not in existing:
        op.create_table(
            "committees",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=160), nullable=False, unique=True),
            sa.Column("chair_member_id", sa.Integer(), sa.ForeignKey("council_members.id"), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_committees_chair_member_id", "committees", ["chair_member_id"])


def downgrade():
    op.drop_table("committees")
    op.drop_table("council_members")
    op.drop_table("council_terms")
