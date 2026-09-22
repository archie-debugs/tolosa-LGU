"""add system settings table"""

from alembic import op
import sqlalchemy as sa


revision = "0008_add_system_settings"
down_revision = "0007_add_user_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("category", sa.String(), nullable=False, server_default="system"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_system_settings_key", "system_settings", ["key"], unique=True)
    op.create_index("ix_system_settings_category", "system_settings", ["category"], unique=False)
    op.create_index("ix_system_settings_updated_at", "system_settings", ["updated_at"], unique=False)


def downgrade():
    op.drop_index("ix_system_settings_updated_at", table_name="system_settings")
    op.drop_index("ix_system_settings_category", table_name="system_settings")
    op.drop_index("ix_system_settings_key", table_name="system_settings")
    op.drop_table("system_settings")
