import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.database import SessionLocal
from backend.core import get_password_hash
from backend import models

username = 'devadmin'
new_pw = 'password123'

s = SessionLocal()
user = s.query(models.User).filter(models.User.username == username).first()
if not user:
    print('User not found')
    s.close()
    sys.exit(1)
user.hashed_password = get_password_hash(new_pw)
s.add(user)
s.commit()
print('Password set for', username)
s.close()
