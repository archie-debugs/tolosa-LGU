import requests, os, sys, time
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.database import SessionLocal
from backend import models

BACKEND = os.getenv('BACKEND_URL', 'http://127.0.0.1:8001')
USERNAME = 'devadmin'
PASSWORD = 'password123'

s = requests.Session()
# login
r = s.post(f"{BACKEND}/auth/login", data={'username': USERNAME, 'password': PASSWORD}, verify=False)
print('login status', r.status_code, r.text[:200])
if r.status_code != 200:
    sys.exit(1)
body = r.json()
token = body.get('access_token')
headers = {'Authorization': f'Bearer {token}'}

# prepare files metadata
files = [ {'filename':'test_a.pdf','size':123}, {'filename':'test_b.docx','size':456} ]
r = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files': files}, headers=headers, verify=False)
print('create_tmp_uploads', r.status_code, r.text)
if r.status_code != 200:
    sys.exit(1)
info = r.json()
print('info', info)
# upload files
for f in info.get('files',[]):
    if not f.get('ok'):
        print('file rejected', f)
        continue
    upload_url = f.get('upload_url')
    fname = f.get('filename')
    # create minimal bytes depending on extension
    if fname.lower().endswith('.pdf'):
        content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    else:
        content = b"DUMMYDOCCONTENT"
    put = s.put(upload_url, data=content, headers={}, verify=False)
    print('PUT', upload_url, put.status_code, put.text[:200])
    time.sleep(0.2)

# validate tmp
tmp_names = [f.get('tmp_name') for f in info.get('files',[]) if f.get('ok')]
r = s.post(f"{BACKEND}/documents/bulk-register/validate_tmp", json={'tmp_names': tmp_names}, headers=headers, verify=False)
print('validate_tmp', r.status_code, r.text)
if r.status_code != 200:
    sys.exit(1)

# confirm
payload = {'tmp_names': tmp_names, 'title': 'BulkTest', 'description':'E2E test'}
r = s.post(f"{BACKEND}/documents/bulk-register/confirm_tmp", json=payload, headers=headers, verify=False)
print('confirm_tmp', r.status_code, r.text)

# inspect DB
DB = SessionLocal()
rows = DB.query(models.Document).filter(models.Document.created_by==USERNAME).all()
print('documents created by', USERNAME, len(rows))
for d in rows[-10:]:
    print(d.id, d.tracking_number, d.title, d.attachment_name, d.created_by)
DB.close()
