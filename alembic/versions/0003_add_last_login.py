"""add last login timestamp to users

Revision ID: 0003_add_last_login
Revises: 0002_add_status_priority_lookup
Create Date: 2026-08-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_add_last_login"
down_revision = "0002_add_status_priority_lookup"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    if "last_login" not in existing_columns:
        op.add_column("users", sa.Column("last_login", sa.DateTime(), nullable=True))

    existing_indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_last_login" not in existing_indexes:
        op.create_index("ix_users_last_login", "users", ["last_login"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_last_login" in existing_indexes:
        op.drop_index("ix_users_last_login", table_name="users")

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    if "last_login" in existing_columns:
        op.drop_column("users", "last_login")