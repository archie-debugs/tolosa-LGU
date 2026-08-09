import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.database import SessionLocal, DATABASE_URL
from backend import models
s=SessionLocal()
users=s.query(models.User).all()
print('DB:', DATABASE_URL)
print('Users count:', len(users))
for u in users:
    print(u.id, u.username, getattr(u,'role',None), getattr(u,'permissions',None), getattr(u,'is_active',None))
s.close()
