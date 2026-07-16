from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Free, local embedded database configuration
DATABASE_URL = "sqlite:///./sb_tolosa.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to manage opening and closing DB connections safely
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()