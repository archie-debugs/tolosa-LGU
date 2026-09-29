import os
import requests
BACKEND = os.getenv('BACKEND_URL', 'http://127.0.0.1:8001')
requests.packages.urllib3.disable_warnings()
s = requests.Session()
login = s.post(f'{BACKEND}/auth/login', data={'username':'a','password':'a'}, verify=False, timeout=30)
headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
resp = s.post(f'{BACKEND}/documents/uploads/create_tmp_uploads', json={'files':[{'filename':'single_security.pdf','size':1024}]}, headers=headers, verify=False, timeout=30)
item = resp.json()['files'][0]
body = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n'
first = requests.put(item['upload_url'], data=body, verify=False, timeout=30)
second = requests.put(item['upload_url'], data=body, verify=False, timeout=30)
print('first', first.status_code, first.text[:120])
print('second', second.status_code, second.text[:120])
