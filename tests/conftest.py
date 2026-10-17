import os
import tempfile

import pytest

from sqlalchemy.engine import make_url

# Tests reset tables with bulk DELETEs, so they must never reach the real database.
# This runs before any test module is imported: bind the shared engine to a throwaway
# database now, so later DATABASE_URL changes (test modules, or frontend modules that
# call load_dotenv(override=True)) cannot repoint it at the .env PostgreSQL database.
#
# By default that is a temporary SQLite file. SQLite ignores row locks and some
# Postgres-only indexes, so set TEST_DATABASE_URL to run against a disposable PostgreSQL
# database instead; its name must end in "_test", and all its tables are dropped first.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
TEST_DATABASE_PATH = None


def _is_disposable_postgres(url) -> bool:
    return url.get_backend_name() == "postgresql" and (url.database or "").endswith("_test")


if TEST_DATABASE_URL:
    if not _is_disposable_postgres(make_url(TEST_DATABASE_URL)):
        raise pytest.UsageError(
            "TEST_DATABASE_URL must point at a PostgreSQL database whose name ends in '_test'; "
            "the test run drops every table in it."
        )
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
else:
    TEST_DATABASE_PATH = os.path.join(tempfile.gettempdir(), f"sb_tolosa_pytest_{os.getpid()}.sqlite")
    if os.path.exists(TEST_DATABASE_PATH):
        os.remove(TEST_DATABASE_PATH)
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"

from Backends.backend import database, models  # noqa: E402

if TEST_DATABASE_URL:
    # Start from the current models, not whatever schema an earlier run left behind.
    models.Base.metadata.drop_all(bind=database.engine)
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    models.Base.metadata.create_all(bind=database.engine)


def pytest_collection_finish(session):
    url = database.engine.url
    allowed = url.get_backend_name() == "sqlite" or (
        TEST_DATABASE_URL and _is_disposable_postgres(url) and url.database == make_url(TEST_DATABASE_URL).database
    )
    if not allowed:
        pytest.exit(
            f"Refusing to run tests against the {url.get_backend_name()} database {url.database!r}; "
            "tests must use the isolated database configured in tests/conftest.py.",
            returncode=1,
        )


def pytest_sessionfinish(session, exitstatus):
    database.engine.dispose()
    if TEST_DATABASE_PATH:
        try:
            os.remove(TEST_DATABASE_PATH)
        except OSError:
            pass
