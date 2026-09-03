"""Ensure FK columns exist on `documents` table when alembic migration couldn't add them."""
from Backends.backend.database import engine
from Backends.backend.core import _column_exists, _add_column_if_missing
from sqlalchemy import text

def ensure():
    with engine.begin() as connection:
        dialect = connection.dialect.name
        if dialect == "sqlite":
            # sqlite: simple ALTER TABLE ADD COLUMN if missing
            cols = [
                ("document_type_id", "INTEGER"),
                ("category_id", "INTEGER"),
                ("originating_office_id", "INTEGER"),
                ("current_office_id", "INTEGER"),
                ("created_by_id", "INTEGER"),
                ("assigned_to_id", "INTEGER"),
            ]
            for name, typ in cols:
                if not _column_exists(connection, "documents", name):
                    connection.execute(text(f"ALTER TABLE documents ADD COLUMN {name} {typ}"))
        else:
            # Postgres: use IF NOT EXISTS
            cols_sql = {
                "document_type_id": "ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_type_id INTEGER",
                "category_id": "ALTER TABLE documents ADD COLUMN IF NOT EXISTS category_id INTEGER",
                "originating_office_id": "ALTER TABLE documents ADD COLUMN IF NOT EXISTS originating_office_id INTEGER",
                "current_office_id": "ALTER TABLE documents ADD COLUMN IF NOT EXISTS current_office_id INTEGER",
                "created_by_id": "ALTER TABLE documents ADD COLUMN IF NOT EXISTS created_by_id INTEGER",
                "assigned_to_id": "ALTER TABLE documents ADD COLUMN IF NOT EXISTS assigned_to_id INTEGER",
            }
            for name, sql in cols_sql.items():
                if not _column_exists(connection, "documents", name):
                    connection.execute(text(sql))

if __name__ == "__main__":
    ensure()
