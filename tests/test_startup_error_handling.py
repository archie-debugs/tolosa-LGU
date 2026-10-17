import pytest

import Backends.backend.schema as schema


def test_startup_raises_when_migration_fails(monkeypatch):
    class DummyInspector:
        def get_table_names(self):
            return ["users", "alembic_version"]

    monkeypatch.setattr(schema, "inspect", lambda engine: DummyInspector())

    def boom(cfg, revision):
        raise RuntimeError("schema migration failed")

    monkeypatch.setattr(schema.command, "upgrade", boom)

    with pytest.raises(RuntimeError, match="schema migration failed"):
        schema.run_database_migrations()
