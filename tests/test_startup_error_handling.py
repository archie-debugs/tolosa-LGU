import os

import pytest
import backend.main as main

os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///./test_startup_error.sqlite"


def test_startup_raises_when_migration_fails(monkeypatch):
    class DummyInspector:
        def get_table_names(self):
            return ["users", "alembic_version"]

    monkeypatch.setattr(main, "inspect", lambda engine: DummyInspector())

    def boom(cfg, revision):
        raise RuntimeError("schema migration failed")

    monkeypatch.setattr(main.command, "upgrade", boom)

    with pytest.raises(RuntimeError, match="schema migration failed|startup initialization"):
        main.run_database_migrations()
