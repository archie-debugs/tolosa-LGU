import os

import backend.main as main

os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///./test_migration_strategy.sqlite"


def test_run_database_migrations_stamps_existing_schema(monkeypatch):
    calls = []

    class DummyInspector:
        def get_table_names(self):
            return ["users", "alembic_version"]

    monkeypatch.setattr(main, "inspect", lambda engine: DummyInspector())

    def fake_upgrade(cfg, revision):
        calls.append(("upgrade", cfg, revision))

    def fake_stamp(cfg, revision):
        calls.append(("stamp", cfg, revision))

    monkeypatch.setattr(main.command, "upgrade", fake_upgrade)
    monkeypatch.setattr(main.command, "stamp", fake_stamp)

    main.run_database_migrations()

    assert calls and calls[0][0] == "upgrade"
