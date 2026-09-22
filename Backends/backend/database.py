import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# Require an explicit DATABASE_URL so the real application cannot silently fall back
# to SQLite. Tests may still set DATABASE_URL to sqlite:// for isolated coverage.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. PostgreSQL is the authoritative application database; "
        "SQLite is not an allowed silent fallback in production."
    )

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite://"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to manage opening and closing DB connections safely
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_database_info():
    return {
        "dialect": engine.url.get_dialect().name,
        "url": str(engine.url),
    }