import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# Use DATABASE_URL from environment for PostgreSQL or other SQLAlchemy backends.
# Fall back to local SQLite for development if DATABASE_URL is not set.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sb_tolosa.db")

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