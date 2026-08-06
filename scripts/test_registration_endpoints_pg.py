import os
import sys
import time
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BASE = 'http://127.0.0.1:8001'

if 'DATABASE_URL' not in os.environ:
    print('ERROR: set DATABASE_URL in env before running this test')
    sys.exit(2)

engine = create_engine(os.environ['DATABASE_URL'])

session = requests.Session()

# Test accounts
approve_user = {
    'first_name': 'TestApprove',
    'last_name': 'User',
    'email': 'testreg_approve+20260806@example.com',
    'username': 'testreg_approve_20260806',
    'password': 'TestPass!234'
}

reject_user = {
    'first_name': 'TestReject',
    'last_name': 'User',
    'email': 'testreg_reject+20260806@example.com',
    'username': 'testreg_reject_20260806',
    'password': 'TestPass!234'
}

created = {}

def post_registration(u):
    url = f"{BASE}/registration/requests"
    r = session.post(url, json=u)
    print('POST', u['username'], '->', r.status_code, r.text)
    return r

# A. Create registration request (approve)
r = post_registration(approve_user)
if r.status_code != 201:
    print('Failed to create approve test registration; abort'); sys.exit(1)
reg_ref_a = r.json().get('registration_reference')
created['approve_ref'] = reg_ref_a

# B. Confirm Pending via API list
r = session.get(f"{BASE}/registration/requests")
items = r.json().get('items', [])
found = [it for it in items if it.get('username')==approve_user['username']]
print('Found in list:', bool(found))
if not found:
    print('Registration not found in list; abort'); sys.exit(1)
req_item = found[0]
print('Status (api list):', req_item.get('status'))

# C. Confirm password is hashed in DB
with engine.connect() as conn:
    row = conn.execute(text("SELECT id, registration_reference, hashed_password FROM registration_requests WHERE registration_reference = :r"), {'r':reg_ref_a}).fetchone()
    print('DB reg row:', row)
    if not row:
        print('Registration row missing in DB; abort'); sys.exit(1)
    reg_id = row[0]
    hashed = row[2]
    if hashed == approve_user['password']:
        print('ERROR: password stored in plaintext')
    else:
        print('Password appears hashed (length):', len(hashed))
created['approve_id'] = reg_id

# D. Confirm duplicate protection
r_dup = post_registration(approve_user)
print('Duplicate attempt status:', r_dup.status_code)

# E. Approve request
approve_url = f"{BASE}/registration/requests/{reg_id}/approve"
resp = session.put(approve_url, json={'final_role': 'Admin'})
print('Approve response:', resp.status_code, resp.text)
if resp.status_code != 200:
    print('Approval failed; abort'); sys.exit(1)

# F. Confirm User is created in DB
with engine.connect() as conn:
    user_row = conn.execute(text("SELECT id, username, hashed_password, role FROM users WHERE username = :u"), {'u': approve_user['username']}).fetchone()
    print('User row:', user_row)
    if not user_row:
        print('User was not created; abort'); sys.exit(1)
    created['user_id'] = user_row[0]
    created['user_role'] = user_row[3]

# G. Confirm final role
print('Final role from DB:', created['user_role'])

# H. Reject another request
r2 = post_registration(reject_user)
if r2.status_code != 201:
    print('Failed to create reject test registration; abort'); sys.exit(1)
reg_ref_b = r2.json().get('registration_reference')
with engine.connect() as conn:
    rowb = conn.execute(text("SELECT id FROM registration_requests WHERE registration_reference = :r"), {'r':reg_ref_b}).fetchone()
    reg_id_b = rowb[0]
    created['reject_ref'] = reg_ref_b
    created['reject_id'] = reg_id_b

# Reject
rej_url = f"{BASE}/registration/requests/{reg_id_b}/reject"
rej_resp = session.put(rej_url, json={'reason': 'Not eligible'})
print('Reject response:', rej_resp.status_code, rej_resp.text)

# I. Confirm rejected request does not create a User
with engine.connect() as conn:
    u = conn.execute(text("SELECT id FROM users WHERE username = :u"), {'u': reject_user['username']}).fetchone()
    print('User for rejected request exists?:', bool(u))

# J. Confirm audit logs are created
with engine.connect() as conn:
    al_sub = conn.execute(text("SELECT id, actor, action, target_id FROM audit_logs WHERE target_id = :r"), {'r': reg_ref_a}).fetchall()
    al_rej = conn.execute(text("SELECT id, actor, action, target_id FROM audit_logs WHERE target_id = :r"), {'r': reg_ref_b}).fetchall()
    print('Audit logs for approve reg:', al_sub)
    print('Audit logs for reject reg:', al_rej)

print('\nTest records to cleanup:', created)

# Cleanup: only delete the created test rows
confirm = os.getenv('CLEANUP_TEST_RECORDS', '1')
if confirm == '1':
    print('Cleaning up test records...')
    with engine.begin() as conn:
        # delete user
        if 'user_id' in created:
            conn.execute(text('DELETE FROM users WHERE id = :id'), {'id': created['user_id']})
            print('Deleted user id', created['user_id'])
        # delete registration requests
        if 'approve_ref' in created:
            conn.execute(text('DELETE FROM registration_requests WHERE registration_reference = :r'), {'r': created['approve_ref']})
            print('Deleted registration request', created['approve_ref'])
        if 'reject_ref' in created:
            conn.execute(text('DELETE FROM registration_requests WHERE registration_reference = :r'), {'r': created['reject_ref']})
            print('Deleted registration request', created['reject_ref'])
        # delete audit logs by target_id
        if 'approve_ref' in created:
            conn.execute(text('DELETE FROM audit_logs WHERE target_id = :r'), {'r': created['approve_ref']})
        if 'reject_ref' in created:
            conn.execute(text('DELETE FROM audit_logs WHERE target_id = :r'), {'r': created['reject_ref']})
    print('Cleanup complete')
else:
    print('Skipped cleanup; set CLEANUP_TEST_RECORDS=1 to enable')

print('Done')
