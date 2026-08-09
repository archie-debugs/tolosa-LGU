import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.database import SessionLocal
from backend import models
s=SessionLocal()
emp=s.query(models.User).filter(models.User.username=='testuser_1786063076').first()
print('before', emp.permissions)
emp.permissions='["register_documents"]'
s.add(emp)
s.commit()
print('after', s.query(models.User).filter(models.User.username=='testuser_1786063076').first().permissions)
s.close()
