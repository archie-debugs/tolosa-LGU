import requests
BASE='http://127.0.0.1:8001'
# register test admin (ignore if exists)
try:
    r = requests.post(f'{BASE}/auth/register', params={'username':'test_importer','password':'password','role':'Admin'}, timeout=10)
    print('register', r.status_code, r.text)
except Exception as e:
    print('register failed', e)
# create a small pdf
with open('test_doc.pdf','wb') as f:
    f.write(b'%PDF-1.4\n%Test\n')
with open('test_doc.pdf','rb') as fh:
    headers={'X-Admin-Username':'test_importer','X-Admin-Role':'Admin'}
    r = requests.post(f'{BASE}/documents/import', files={'file': ('test_doc.pdf', fh)}, headers=headers, timeout=30)
    print('upload', r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text)
