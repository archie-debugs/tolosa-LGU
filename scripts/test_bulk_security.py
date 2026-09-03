import requests, os, sys, time
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from Backends.backend.database import SessionLocal
from Backends.backend import models
from Backends.backend.core import get_password_hash

BACKEND = os.getenv('BACKEND_URL', 'http://127.0.0.1:8001')

s = requests.Session()

def login(username, password):
    r = s.post(f"{BACKEND}/auth/login", data={'username': username, 'password': password}, verify=False)
    return r

# prepare test users
DB = SessionLocal()
# pick an employee user
emp = DB.query(models.User).filter(models.User.role.ilike('%Employee%')).first()
if not emp:
    print('No employee user found')
    DB.close(); sys.exit(1)
emp_username = emp.username
print('Employee username:', emp_username)
# set password and grant permission
emp.hashed_password = get_password_hash('password123')
emp.permissions = str(['register_documents'])
DB.add(emp); DB.commit()

# pick an sb member
sb = DB.query(models.User).filter(models.User.role.ilike('%SB%')).first()
if not sb:
    print('No SB Member found')
    DB.close(); sys.exit(1)
sb_username = sb.username
sb.hashed_password = get_password_hash('password123')
DB.add(sb); DB.commit()
DB.close()

results = {}

# Test Employee with permission
r = login(emp_username, 'password123')
results['employee_login'] = (r.status_code==200)
print('employee login', r.status_code)
if r.status_code==200:
    token = r.json().get('access_token')
    headers = {'Authorization': f'Bearer {token}'}
    files = [{'filename':'e1.pdf','size':10}]
    r2 = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files':files}, headers=headers, verify=False)
    results['employee_create_tmp'] = (r2.status_code==200)
    print('employee create_tmp', r2.status_code)
else:
    results['employee_create_tmp'] = False

# Revoke permission
DB = SessionLocal()
emp2 = DB.query(models.User).filter(models.User.username==emp_username).first()
emp2.permissions = str([])
DB.add(emp2); DB.commit(); DB.close()
# Test Employee without permission
r = login(emp_username, 'password123')
print('employee login (no perm)', r.status_code)
if r.status_code==200:
    token = r.json().get('access_token')
    headers = {'Authorization': f'Bearer {token}'}
    r2 = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files':[{'filename':'e2.pdf','size':10}]}, headers=headers, verify=False)
    results['employee_no_perm_create_tmp'] = (r2.status_code==403)
    print('create_tmp after revoke', r2.status_code)
else:
    results['employee_no_perm_create_tmp'] = False

# Test SB Member
r = login(sb_username, 'password123')
results['sb_login'] = (r.status_code==200)
print('sb login', r.status_code)
if r.status_code==200:
    token = r.json().get('access_token')
    headers = {'Authorization': f'Bearer {token}'}
    r2 = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files':[{'filename':'s1.pdf','size':10}]}, headers=headers, verify=False)
    results['sb_create_tmp'] = (r2.status_code==403)
    print('sb create_tmp', r2.status_code)
else:
    results['sb_create_tmp'] = False

# Test unauthenticated create_tmp_uploads
r = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files':[{'filename':'u1.pdf','size':10}]}, verify=False)
results['unauthenticated_create_tmp'] = (r.status_code==401)
print('unauthenticated create_tmp', r.status_code)

# Test invalid JWT
bad_headers = {'Authorization':'Bearer invalid-token'}
r = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files':[{'filename':'u1.pdf','size':10}]}, headers=bad_headers, verify=False)
results['invalid_jwt'] = (r.status_code==401)
print('invalid jwt', r.status_code)

# Test upload token expiry
# Login as devadmin and create a tmp upload
r = login('devadmin','password123')
assert r.status_code==200
token = r.json().get('access_token')
headers = {'Authorization':f'Bearer {token}'}
r2 = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files':[{'filename':'expire.pdf','size':10}]}, headers=headers, verify=False)
files = r2.json().get('files',[])
ok = files[0]
upload_url = ok.get('upload_url')
tmp_name = ok.get('tmp_name')
upload_token = ok.get('upload_token')
# artificially expire meta file by editing it
meta_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__),'..','uploads')),'tmp', f"{tmp_name}.meta.json")
import json
m = json.load(open(meta_path))
m['expires_at'] = int(time.time()) - 10
json.dump(m, open(meta_path,'w'))
# attempt upload
put = s.put(upload_url, data=b'hello', verify=False)
results['expired_token_upload'] = put.status_code in (401,403)
print('expired upload put', put.status_code)

# Test duplicate confirm protection
# create tmp upload again and complete confirm then try confirm again
r2 = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files':[{'filename':'dup.pdf','size':10}]}, headers=headers, verify=False)
fileinfo = r2.json()['files'][0]
upload_url = fileinfo['upload_url']
tmp_name = fileinfo['tmp_name']
put = s.put(upload_url, data=b'hello', verify=False)
# validate
val = s.post(f"{BACKEND}/documents/bulk-register/validate_tmp", json={'tmp_names':[tmp_name]}, headers=headers, verify=False)
print('dup validate', val.status_code, val.text)
conf = s.post(f"{BACKEND}/documents/bulk-register/confirm_tmp", json={'tmp_names':[tmp_name],'title':'dup'}, headers=headers, verify=False)
print('first confirm', conf.status_code, conf.text)
# second confirm (should not create duplicate)
conf2 = s.post(f"{BACKEND}/documents/bulk-register/confirm_tmp", json={'tmp_names':[tmp_name],'title':'dup'}, headers=headers, verify=False)
print('second confirm', conf2.status_code, conf2.text)
results['duplicate_confirm'] = conf2.status_code in (400,404) or ('failed' in conf2.text.lower())

# Test token misuse: user A's token used by user B
# create upload url as devadmin (done above fileinfo)
# login as employee with different user and attempt to PUT to upload_url
r_emp = login(emp_username,'password123')
print('emp login for misuse', r_emp.status_code)
put_misuse = requests.put(upload_url, data=b'bad', verify=False)
results['token_misuse_no_auth'] = (put_misuse.status_code==200) # currently will be allowed because presigned URL is sufficient

print('\nRESULTS')
for k,v in results.items():
    print(k, v)
print('\nNote: token_misuse_no_auth True indicates presigned URL allows upload by anyone with URL (this may be considered a security issue).')
