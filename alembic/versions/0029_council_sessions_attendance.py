"""SB sessions and attendance"""

from alembic import op
import sqlalchemy as sa


revision = "0029_council_sessions_attendance"
down_revision = "0028_measure_stages"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "council_sessions" not in existing:
        op.create_table(
            "council_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("term_id", sa.Integer(), sa.ForeignKey("council_terms.id"), nullable=False),
            sa.Column("kind", sa.String(length=10), nullable=False),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("held_on", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=10), nullable=False, server_default="Draft"),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("term_id", "kind", "number", name="uq_council_sessions_term_kind_number"),
            sa.CheckConstraint("kind IN ('Regular', 'Special')", name="ck_council_sessions_kind"),
            sa.CheckConstraint("status IN ('Draft', 'Scheduled', 'Held')", name="ck_council_sessions_status"),
        )
        op.create_index("ix_council_sessions_term_id", "council_sessions", ["term_id"])
        op.create_index("ix_council_sessions_held_on", "council_sessions", ["held_on"])
    if "session_attendance" not in existing:
        op.create_table(
            "session_attendance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("council_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("member_id", sa.Integer(), sa.ForeignKey("council_members.id"), nullable=False),
            sa.Column("mark", sa.String(length=10), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("is_correction", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("recorded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("recorded_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("mark IN ('Present', 'Absent', 'On leave', 'Excused')", name="ck_session_attendance_mark"),
        )
        op.create_index("ix_session_attendance_session_id", "session_attendance", ["session_id"])
        op.create_index("ix_session_attendance_member_id", "session_attendance", ["member_id"])


def downgrade():
    op.drop_table("session_attendance")
    op.drop_table("council_sessions")
