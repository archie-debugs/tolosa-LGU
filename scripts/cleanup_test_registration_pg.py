import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['DATABASE_URL'])
with engine.begin() as conn:
    conn.execute(text("DELETE FROM audit_logs WHERE target_id = 'REG-2026-0001'"))
    conn.execute(text("DELETE FROM registration_requests WHERE registration_reference = 'REG-2026-0001'"))
    conn.execute(text("DELETE FROM users WHERE username = 'testreg_approve_20260806'"))
print('cleanup done')
