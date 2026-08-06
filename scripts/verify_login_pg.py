import os
import requests
from sqlalchemy import create_engine, text

BASE = 'http://127.0.0.1:8001'
engine = create_engine(os.environ['DATABASE_URL'])
payload = {
    'first_name': 'TestLogin2',
    'last_name': 'User',
    'email': 'testlogin2+20260806@example.com',
    'username': 'testlogin2_20260806',
    'password': 'TestPass!234',
}
r = requests.post(f'{BASE}/registration/requests', json=payload, timeout=10)
print('POST_STATUS', r.status_code)
print('POST_BODY', r.text)
ref = r.json()['registration_reference']

with engine.connect() as conn:
    row = conn.execute(text('SELECT id FROM registration_requests WHERE registration_reference=:ref'), {'ref': ref}).fetchone()
    req_id = row[0]
    print('REQ_ID', req_id)

approve = requests.put(f'{BASE}/registration/requests/{req_id}/approve', json={'final_role': 'Admin'}, timeout=10)
print('APPROVE_STATUS', approve.status_code)
print('APPROVE_BODY', approve.text)

login = requests.post(f'{BASE}/auth/login', params={'username': payload['username'], 'password': payload['password']}, timeout=10)
print('LOGIN_STATUS', login.status_code)
print('LOGIN_BODY', login.text)

with engine.begin() as conn:
    conn.execute(text('DELETE FROM audit_logs WHERE target_id=:ref'), {'ref': ref})
    conn.execute(text('DELETE FROM registration_requests WHERE registration_reference=:ref'), {'ref': ref})
    conn.execute(text('DELETE FROM users WHERE username=:u'), {'u': payload['username']})
print('CLEANUP_DONE')
