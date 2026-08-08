import requests
with open('test_doc.pdf','wb') as f:
    f.write(b'%PDF-1.4\n%Test\n')
with open('test_doc.pdf','rb') as fh:
    r = requests.post('http://127.0.0.1:8001/documents/import', files={'file': ('test_doc.pdf', fh)}, timeout=30)
    print(r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text)
