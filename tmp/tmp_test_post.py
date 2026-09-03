import requests
url='http://127.0.0.1:8001/documents'
files={'file':('test_doc.pdf', b'%PDF-1.4 test pdf', 'application/pdf')}
data={'title':'Test upload from agent','description':'Test','status_field':'Pending'}
try:
    r=requests.post(url, data=data, files=files, timeout=15)
    print('status', r.status_code)
    print(r.text)
except Exception as e:
    print('error', e)
