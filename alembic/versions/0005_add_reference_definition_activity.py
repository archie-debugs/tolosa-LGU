"""add activation state to category and document type definitions

Revision ID: 0005_add_reference_definition_activity
Revises: 0004_add_public_document_visibility
Create Date: 2026-09-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_add_reference_definition_activity"
down_revision = "0004_add_public_document_visibility"
branch_labels = None
depends_on = None


def _add_active_column(table_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "is_active" not in columns:
        op.add_column(table_name, sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))


def upgrade():
    _add_active_column("categories")
    _add_active_column("document_types")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in ("document_types", "categories"):
        if table_name not in inspector.get_table_names():
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "is_active" in columns:
            op.drop_column(table_name, "is_active")
