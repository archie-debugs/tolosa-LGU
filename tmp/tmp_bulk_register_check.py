import os
import requests
BACKEND = os.getenv('BACKEND_URL', 'http://127.0.0.1:8001')
requests.packages.urllib3.disable_warnings()
s = requests.Session()
login = s.post(f'{BACKEND}/auth/login', data={'username':'a','password':'a'}, verify=False, timeout=30)
headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
files = [{'filename': 'bulk_reg_a.pdf', 'size': 1024}, {'filename': 'bulk_reg_b.pdf', 'size': 1024}]
resp = s.post(f'{BACKEND}/documents/uploads/create_tmp_uploads', json={'files': files}, headers=headers, verify=False, timeout=30)
items = resp.json()['files']
body = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n'
for item in items:
    put = requests.put(item['upload_url'], data=body, verify=False, timeout=30)
    print('put', item['filename'], put.status_code, put.text[:120])
tmp_names = [item['tmp_name'] for item in items]
validate = s.post(f'{BACKEND}/documents/bulk-register/validate_tmp', json={'tmp_names': tmp_names}, headers=headers, verify=False, timeout=30)
print('validate', validate.status_code, validate.text[:300])
confirm = s.post(f'{BACKEND}/documents/bulk-register/confirm_tmp', json={'tmp_names': tmp_names, 'title': 'Bulk Validation Test', 'description': 'Bulk Validation Test', 'category': 'Legislation', 'document_type': 'Ordinance', 'current_office': 'SB Secretariat', 'assigned_to': 'Tester', 'author': 'Tester', 'priority': 'High'}, headers=headers, verify=False, timeout=180)
print('confirm', confirm.status_code, confirm.text[:300])
