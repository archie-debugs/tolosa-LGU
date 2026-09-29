import os
from concurrent.futures import ThreadPoolExecutor
import requests
BACKEND = os.getenv('BACKEND_URL', 'http://127.0.0.1:8001')
requests.packages.urllib3.disable_warnings()
s = requests.Session()
login = s.post(f'{BACKEND}/auth/login', data={'username':'a','password':'a'}, verify=False, timeout=30)
headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
files = [{'filename': f'multi_{i}.pdf', 'size': 1024} for i in range(10)]
resp = s.post(f'{BACKEND}/documents/uploads/create_tmp_uploads', json={'files': files}, headers=headers, verify=False, timeout=30)
print('created', resp.status_code)
items = resp.json()['files']
print('count', len(items))
body = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n'

def do_upload(item):
    r = requests.put(item['upload_url'], data=body, verify=False, timeout=30)
    return item['filename'], r.status_code, r.text[:120]
with ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(do_upload, items))
for result in results:
    print(result)
print('success_count', sum(1 for _, status, _ in results if status == 200))
