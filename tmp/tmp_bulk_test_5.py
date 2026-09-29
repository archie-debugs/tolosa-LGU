import os, time
import requests
BACKEND = os.getenv('BACKEND_URL', 'http://127.0.0.1:8001')
requests.packages.urllib3.disable_warnings()
s = requests.Session()
login = s.post(f'{BACKEND}/auth/login', data={'username':'a','password':'a'}, verify=False, timeout=30)
headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
files = [{'filename': f'five_{i}.pdf', 'size': 1024} for i in range(5)]
resp = s.post(f'{BACKEND}/documents/uploads/create_tmp_uploads', json={'files': files}, headers=headers, verify=False, timeout=30)
items = resp.json()['files']
print('create_count', len(items), 'status', resp.status_code)
body = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n'
results = []
for item in items:
    r = requests.put(item['upload_url'], data=body, verify=False, timeout=30)
    results.append((item['filename'], r.status_code, r.text[:120]))
print('five_results', results)
# invalid token rejection
bad = requests.put(items[0]['upload_url'].replace('upload_token=', 'upload_token=badtoken'), data=body, verify=False, timeout=30)
print('invalid_token', bad.status_code, bad.text[:200])
