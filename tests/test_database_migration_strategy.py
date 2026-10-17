import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import Backends.backend.database as database
import Backends.backend.schema as schema
from Backends.backend import models

ALEMBIC_CFG = Config(os.path.join(schema.PROJECT_ROOT, "alembic.ini"))
HEAD = ScriptDirectory.from_config(ALEMBIC_CFG).get_current_head()
PRE_LEGACY_REVISION = "0019_document_action_received"

# The pre-Alembic base tables as an old database has them: only their original columns,
# plus the foreign key columns added by migration 0001.
LEGACY_BASE_TABLES = {
    "users": """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username VARCHAR NOT NULL UNIQUE,
            hashed_password VARCHAR NOT NULL,
            office_id INTEGER
        )
    """,
    "documents": """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            tracking_number VARCHAR NOT NULL UNIQUE,
            title VARCHAR NOT NULL,
            document_type_id INTEGER,
            category_id INTEGER,
            originating_office_id INTEGER,
            current_office_id INTEGER,
            created_by_id INTEGER,
            assigned_to_id INTEGER
        )
    """,
}


@pytest.fixture
def migration_engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.sqlite'}")
    # alembic/env.py and the startup code both read the shared engine.
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(schema, "engine", engine)
    yield engine
    engine.dispose()


def _missing_model_columns(engine):
    inspector = inspect(engine)
    missing = []
    for table in models.Base.metadata.sorted_tables:
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        missing.extend(f"{table.name}.{column.name}" for column in table.columns if column.name not in existing)
    return missing


def _current_revision(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_empty_database_is_created_from_models_and_stamped(migration_engine):
    schema.run_database_migrations()

    assert set(models.Base.metadata.tables) <= set(inspect(migration_engine).get_table_names())
    assert _current_revision(migration_engine) == HEAD


def test_upgrade_brings_legacy_base_tables_up_to_the_model(migration_engine):
    models.Base.metadata.create_all(bind=migration_engine)
    with migration_engine.begin() as connection:
        for table_name in ("users", "documents", "registration_requests", "audit_logs"):
            connection.execute(text(f"DROP TABLE {table_name}"))
        for ddl in LEGACY_BASE_TABLES.values():
            connection.execute(text(ddl))
        connection.execute(text("INSERT INTO users (username, hashed_password) VALUES ('old-admin', 'x'), ('old-staff', 'x')"))
        connection.execute(text("INSERT INTO documents (tracking_number, title) VALUES ('T-1', 'One'), ('T-2', 'Two')"))
    command.stamp(ALEMBIC_CFG, PRE_LEGACY_REVISION)
    # Legacy role names only exist once the column does, so set them after stamping.
    with migration_engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR"))
        connection.execute(text("UPDATE users SET role = 'admin' WHERE username = 'old-admin'"))
        connection.execute(text("UPDATE users SET role = 'staff' WHERE username = 'old-staff'"))

    schema.run_database_migrations()

    assert _missing_model_columns(migration_engine) == []
    assert _current_revision(migration_engine) == HEAD
    with migration_engine.connect() as connection:
        users = dict(connection.execute(text("SELECT username, role FROM users")).fetchall())
        user_defaults = connection.execute(text("SELECT DISTINCT status, is_active, permissions FROM users")).fetchall()
        user_created_at = connection.execute(text("SELECT count(*) FROM users WHERE created_at IS NULL")).scalar_one()
        tokens = [row[0] for row in connection.execute(text("SELECT qr_token FROM documents")).fetchall()]
    assert users == {"old-admin": "Super Administrator", "old-staff": "Employee"}
    assert user_defaults == [("Active", 1, "[]")]
    assert user_created_at == 0
    assert all(tokens) and len(set(tokens)) == len(tokens)
    assert "ix_documents_qr_token" in {index["name"] for index in inspect(migration_engine).get_indexes("documents")}


def test_upgrade_is_a_no_op_on_a_database_the_old_startup_already_patched(migration_engine):
    models.Base.metadata.create_all(bind=migration_engine)
    command.stamp(ALEMBIC_CFG, PRE_LEGACY_REVISION)

    schema.run_database_migrations()

    assert _missing_model_columns(migration_engine) == []
    assert _current_revision(migration_engine) == HEAD


def test_tables_without_alembic_version_refuse_to_start(migration_engine):
    with migration_engine.begin() as connection:
        connection.execute(text(LEGACY_BASE_TABLES["users"]))

    with pytest.raises(RuntimeError, match="alembic_version"):
        schema.run_database_migrations()


def test_versioned_database_only_runs_upgrade(monkeypatch):
    calls = []

    class DummyInspector:
        def get_table_names(self):
            return ["users", "alembic_version"]

    monkeypatch.setattr(schema, "inspect", lambda engine: DummyInspector())
    monkeypatch.setattr(schema.command, "upgrade", lambda cfg, revision: calls.append(("upgrade", revision)))
    monkeypatch.setattr(schema.command, "stamp", lambda cfg, revision: calls.append(("stamp", revision)))
    monkeypatch.setattr(schema.models.Base.metadata, "create_all", lambda **kwargs: calls.append(("create_all",)))

    schema.run_database_migrations()

    assert calls == [("upgrade", "head")]
