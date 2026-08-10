"""add status and priority lookup tables

Revision ID: 0002_add_status_priority_lookup
Revises: 0001_add_normalized_tables
Create Date: 2026-08-08 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_status_priority_lookup'
down_revision = '0001_add_normalized_tables'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'status_lookup',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
    )
    op.create_table(
        'priority_lookup',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
    )

    # seed common values
    op.bulk_insert(sa.table('status_lookup', sa.column('name', sa.String())), [{'name': 'Pending'}, {'name': 'Completed'}, {'name': 'Archived'}])
    op.bulk_insert(sa.table('priority_lookup', sa.column('name', sa.String())), [{'name': 'Low'}, {'name': 'Medium'}, {'name': 'High'}])


def downgrade():
    op.drop_table('priority_lookup')
    op.drop_table('status_lookup')
