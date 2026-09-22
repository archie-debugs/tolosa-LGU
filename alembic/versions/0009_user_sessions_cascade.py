"""add cascade delete for user sessions"""

from alembic import op
import sqlalchemy as sa


revision = "0009_user_sessions_cascade"
down_revision = "0008_add_system_settings"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        op.execute("ALTER TABLE user_sessions DROP CONSTRAINT IF EXISTS user_sessions_user_id_fkey")
        op.create_foreign_key(
            "user_sessions_user_id_fkey",
            "user_sessions",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE user_sessions DROP CONSTRAINT IF EXISTS user_sessions_user_id_fkey")
        op.create_foreign_key(
            "user_sessions_user_id_fkey",
            "user_sessions",
            "users",
            ["user_id"],
            ["id"],
        )
