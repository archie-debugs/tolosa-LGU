import os
import tempfile

import pytest

# Tests reset tables with bulk DELETEs, so they must never reach the real database.
# This runs before any test module is imported: bind the shared engine to a throwaway
# SQLite file now, so later DATABASE_URL changes (test modules, or frontend modules that
# call load_dotenv(override=True)) cannot repoint it at the .env PostgreSQL database.
TEST_DATABASE_PATH = os.path.join(tempfile.gettempdir(), f"sb_tolosa_pytest_{os.getpid()}.sqlite")
if os.path.exists(TEST_DATABASE_PATH):
    os.remove(TEST_DATABASE_PATH)

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"

from Backends.backend import database  # noqa: E402


def pytest_collection_finish(session):
    if database.engine.dialect.name != "sqlite":
        pytest.exit(
            f"Refusing to run tests against a {database.engine.dialect.name} database; "
            "tests must use the isolated SQLite database configured in tests/conftest.py.",
            returncode=1,
        )


def pytest_sessionfinish(session, exitstatus):
    database.engine.dispose()
    try:
        os.remove(TEST_DATABASE_PATH)
    except OSError:
        pass
