import os
import shutil
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

# Stored attachments, QR images and in-progress uploads go to a throwaway folder too, never
# the real document storage. The paths are fixed when core is imported, so import it now.
TEST_STORAGE_ROOT = tempfile.mkdtemp(prefix="sb_tolosa_pytest_storage_")
os.environ["DOCUMENT_STORAGE_DIR"] = os.path.join(TEST_STORAGE_ROOT, "documents")
os.environ["TEMP_UPLOAD_DIR"] = os.path.join(TEST_STORAGE_ROOT, "tmp")

from Backends.backend import core, database, models  # noqa: E402

if TEST_DATABASE_URL:
    # Start empty, like the SQLite file, so the app's own startup builds the current schema
    # rather than tests running on whatever an earlier run left behind.
    models.Base.metadata.drop_all(bind=database.engine)
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")


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
    storage_root = os.path.normcase(os.path.abspath(TEST_STORAGE_ROOT))
    for name in ("UPLOAD_DIR", "TEMP_UPLOAD_DIR"):
        path = os.path.normcase(getattr(core, name))
        if os.path.commonpath([path, storage_root]) != storage_root:
            pytest.exit(f"Refusing to run tests with {name} outside the test storage folder: {path}", returncode=1)


def pytest_sessionfinish(session, exitstatus):
    database.engine.dispose()
    shutil.rmtree(TEST_STORAGE_ROOT, ignore_errors=True)
    if TEST_DATABASE_PATH:
        try:
            os.remove(TEST_DATABASE_PATH)
        except OSError:
            pass
