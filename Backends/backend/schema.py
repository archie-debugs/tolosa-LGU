import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from . import models
from .database import engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_database_migrations() -> None:
    """Bring the database schema to the latest Alembic revision.

    Alembic migrations are the only way the schema changes. The one exception is an
    empty database: the migration chain assumes the pre-Alembic base tables already
    exist, so a fresh database is built from the models and stamped at head.
    """
    alembic_cfg = Config(os.path.join(PROJECT_ROOT, "alembic.ini"))
    table_names = set(inspect(engine).get_table_names())

    if not table_names:
        models.Base.metadata.create_all(bind=engine)
        command.stamp(alembic_cfg, "head")
        return

    if "alembic_version" not in table_names:
        raise RuntimeError(
            "The database has tables but no alembic_version table, so its schema revision is unknown. "
            "Run `alembic stamp <revision>` with the revision that matches the existing schema, then restart."
        )

    command.upgrade(alembic_cfg, "head")
