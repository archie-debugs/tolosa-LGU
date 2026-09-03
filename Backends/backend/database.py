import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# Prefer the active environment, but do not silently hide a bad DB configuration.
# If the env file is present and still does not define DATABASE_URL, fail loudly instead
# of silently switching to a development SQLite database that can mismatch credentials.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./sb_tolosa.db"

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