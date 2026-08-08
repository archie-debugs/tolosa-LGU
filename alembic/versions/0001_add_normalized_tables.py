"""add normalized reference tables and history/attachments

Revision ID: 0001_add_normalized_tables
Revises: 
Create Date: 2026-08-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_add_normalized_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # reference tables
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
    )
    op.create_table(
        'offices',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
    )
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
    )
    op.create_table(
        'document_types',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
    )

    # attachments
    op.create_table(
        'attachments',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(), nullable=False),
        sa.Column('stored_path', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=True),
        sa.Column('size', sa.Integer(), nullable=True),
        sa.Column('checksum', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # document history
    op.create_table(
        'document_history',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('actor', sa.String(), nullable=True),
        sa.Column('from_office', sa.String(), nullable=True),
        sa.Column('to_office', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # add FK columns to documents (best-effort, may not be supported on sqlite without table recreate)
    with op.batch_alter_table('documents') as batch_op:
        batch_op.add_column(sa.Column('document_type_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('originating_office_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('current_office_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('created_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('assigned_to_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('documents') as batch_op:
        batch_op.drop_column('assigned_to_id')
        batch_op.drop_column('created_by_id')
        batch_op.drop_column('current_office_id')
        batch_op.drop_column('originating_office_id')
        batch_op.drop_column('category_id')
        batch_op.drop_column('document_type_id')

    op.drop_table('document_history')
    op.drop_table('attachments')
    op.drop_table('document_types')
    op.drop_table('categories')
    op.drop_table('offices')
    op.drop_table('roles')
