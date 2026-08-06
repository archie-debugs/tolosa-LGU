import os
import requests
from sqlalchemy import create_engine, text

BASE = 'http://127.0.0.1:8001'
engine = create_engine(os.environ['DATABASE_URL'])

payload = {
    'first_name': 'TestLogin',
    'last_name': 'User',
    'email': 'testlogin+20260806@example.com',
    'username': 'testlogin_20260806',
    'password': 'TestPass!234',
}
resp = requests.post(f'{BASE}/registration/requests', json=payload, timeout=10)
print('POST_STATUS', resp.status_code)
print('POST_BODY', resp.text)
ref = resp.json()['registration_reference']

with engine.connect() as conn:
    row = conn.execute(text("SELECT id, status, registration_reference, hashed_password FROM registration_requests WHERE registration_reference=:ref"), {'ref': ref}).fetchone()
    req_id = row[0]
    print('DB_ROW', row)
    print('DB_STATUS', row[1])
    print('HASHED', row[3] != payload['password'])

print('LIST_STATUS', requests.get(f'{BASE}/registration/requests', timeout=10).status_code)
print('DETAIL_STATUS', requests.get(f'{BASE}/registration/requests/{req_id}', timeout=10).status_code)
print('DETAIL_BODY', requests.get(f'{BASE}/registration/requests/{req_id}', timeout=10).text)

approve_resp = requests.put(f'{BASE}/registration/requests/{req_id}/approve', json={'final_role': 'Admin'}, timeout=10)
print('APPROVE_STATUS', approve_resp.status_code)
print('APPROVE_BODY', approve_resp.text)

login_resp = requests.post(f'{BASE}/auth/login', json={'username': payload['username'], 'password': payload['password']}, timeout=10)
print('LOGIN_STATUS', login_resp.status_code)
print('LOGIN_BODY', login_resp.text)

payload2 = {
    'first_name': 'TestState',
    'last_name': 'User',
    'email': 'teststate+20260806@example.com',
    'username': 'teststate_20260806',
    'password': 'TestPass!234',
}
resp2 = requests.post(f'{BASE}/registration/requests', json=payload2, timeout=10)
ref2 = resp2.json()['registration_reference']
with engine.connect() as conn:
    row2 = conn.execute(text("SELECT id FROM registration_requests WHERE registration_reference=:ref"), {'ref': ref2}).fetchone()
    req_id2 = row2[0]

approve2 = requests.put(f'{BASE}/registration/requests/{req_id2}/approve', json={'final_role': 'Admin'}, timeout=10)
print('SECOND_APPROVE_STATUS', approve2.status_code)
print('SECOND_APPROVE_BODY', approve2.text)

reject_after_approve = requests.put(f'{BASE}/registration/requests/{req_id2}/reject', json={'reason': 'Nope'}, timeout=10)
print('REJECT_AFTER_APPROVE_STATUS', reject_after_approve.status_code)
print('REJECT_AFTER_APPROVE_BODY', reject_after_approve.text)

with engine.begin() as conn:
    conn.execute(text("DELETE FROM audit_logs WHERE target_id IN (:a, :b)"), {'a': ref, 'b': ref2})
    conn.execute(text("DELETE FROM registration_requests WHERE registration_reference IN (:a, :b)"), {'a': ref, 'b': ref2})
    conn.execute(text("DELETE FROM users WHERE username IN (:u1, :u2)"), {'u1': payload['username'], 'u2': payload2['username']})
print('CLEANUP_DONE')
