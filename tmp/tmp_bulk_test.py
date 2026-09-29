import os
import requests
BACKEND = os.getenv('BACKEND_URL', 'http://127.0.0.1:8001')
requests.packages.urllib3.disable_warnings()
s = requests.Session()
login = s.post(f'{BACKEND}/auth/login', data={'username':'a','password':'a'}, verify=False, timeout=30)
print('login', login.status_code)
headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
files = [{'filename': 'bulk_1.pdf', 'size': 1024}, {'filename': 'bulk_2.pdf', 'size': 2048}]
resp = s.post(f'{BACKEND}/documents/uploads/create_tmp_uploads', json={'files': files}, headers=headers, verify=False, timeout=30)
print('create', resp.status_code, resp.text)
for item in resp.json().get('files', []):
    body = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n'
    put = requests.put(item['upload_url'], data=body, verify=False, timeout=30)
    print(item['filename'], put.status_code, put.text[:200])
