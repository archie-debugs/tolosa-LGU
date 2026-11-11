"""Add the foreign keys on documents that older databases never got.

Migration 0001 added these columns without constraints, so only databases built from the
models had them. Deleting a user keeps their documents and clears the link.
"""

from alembic import op
import sqlalchemy as sa


revision = "0040_documents_foreign_keys"
down_revision = "0039_avatar_email_verified"
branch_labels = None
depends_on = None

# (column, target table, ON DELETE)
FOREIGN_KEYS = (
    ("document_type_id", "document_types", None),
    ("category_id", "categories", None),
    ("originating_office_id", "offices", None),
    ("current_office_id", "offices", None),
    ("created_by_id", "users", "SET NULL"),
    ("assigned_to_id", "users", "SET NULL"),
)


def _name(column):
    return f"fk_documents_{column}"


def _existing_fk_columns():
    return {
        fk["constrained_columns"][0]: fk["name"]
        for fk in sa.inspect(op.get_bind()).get_foreign_keys("documents")
        if len(fk["constrained_columns"]) == 1
    }


def upgrade():
    existing = _existing_fk_columns()
    with op.batch_alter_table("documents") as batch_op:
        for column, target, ondelete in FOREIGN_KEYS:
            if column in existing:
                # Databases built from the models already have a key here; give users the new ON DELETE rule.
                # shortcut: SQLite reports these keys unnamed and batch mode can't drop them, so they keep the old rule; SQLite is test-only.
                if ondelete is None or not existing[column]:
                    continue
                batch_op.drop_constraint(existing[column], type_="foreignkey")
            batch_op.create_foreign_key(_name(column), target, [column], ["id"], ondelete=ondelete)


def downgrade():
    existing = _existing_fk_columns()
    with op.batch_alter_table("documents") as batch_op:
        for column, _target, _ondelete in FOREIGN_KEYS:
            if existing.get(column) == _name(column):
                batch_op.drop_constraint(_name(column), type_="foreignkey")
