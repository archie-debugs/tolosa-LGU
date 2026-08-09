import json
import os
import time
from pathlib import Path
import requests
from backend.database import SessionLocal
from backend import models

BACKEND = os.getenv('BACKEND_URL', 'http://127.0.0.1:8001')
requests.packages.urllib3.disable_warnings()

s = requests.Session()

SUPER_ADMIN = ('devadmin', 'password123')
EMPLOYEE_WITH = ('testuser_1786063076', 'password123')
EMPLOYEE_WITHOUT = ('testuser_d8f96d', 'password123')
SB_MEMBER = ('d', 'password123')

TEST_MARKER = f'MULTI_DOC_REG_{int(time.time())}'

FILE_CONTENTS = {
    '.pdf': b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n',
    '.doc': b'DUMMY_DOC_CONTENT',
    '.docx': b'PK\x03\x04DUMMYDOCX',
}


def login(username, password):
    return s.post(f"{BACKEND}/auth/login", data={'username': username, 'password': password}, verify=False, timeout=30)


def create_tmp(headers, files):
    return s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files': files}, headers=headers, verify=False, timeout=30)


def put_file(url, content, headers=None):
    return requests.put(url, data=content, headers=headers or {}, verify=False, timeout=30)


def validate_tmp(headers, tmp_names):
    return s.post(f"{BACKEND}/documents/bulk-register/validate_tmp", json={'tmp_names': tmp_names}, headers=headers, verify=False, timeout=30)


def confirm_tmp(headers, payload):
    return s.post(f"{BACKEND}/documents/bulk-register/confirm_tmp", json=payload, headers=headers, verify=False, timeout=60)


def db_counts():
    db = SessionLocal()
    try:
        return {'documents': db.query(models.Document).count(), 'audit_logs': db.query(models.AuditLog).count()}
    finally:
        db.close()


def query_docs_by_title(title):
    db = SessionLocal()
    try:
        return db.query(models.Document).filter(models.Document.title == title).all()
    finally:
        db.close()


def query_audits(actor, action):
    db = SessionLocal()
    try:
        return db.query(models.AuditLog).filter(models.AuditLog.actor == actor, models.AuditLog.action == action).order_by(models.AuditLog.created_at.desc()).all()
    finally:
        db.close()


results = {}

print('Backend URL:', BACKEND)
print('Backend docs endpoint test...')
try:
    r = s.get(f"{BACKEND}/docs", verify=False, timeout=10)
    results['backend_startup'] = (r.status_code == 200)
    print('/docs', r.status_code)
except Exception as exc:
    results['backend_startup'] = False
    print('Backend request failed:', exc)

counts_before = db_counts()
print('DB counts before:', counts_before)
results['postgres_connection'] = isinstance(counts_before.get('documents'), int)

# Super Admin flow
print('\n=== SUPER ADMIN ===')
r = login(*SUPER_ADMIN)
results['superadmin_login'] = (r.status_code == 200)
print('login', r.status_code, r.text[:200])
super_headers = {'Authorization': f"Bearer {r.json().get('access_token')}"} if r.status_code == 200 else {}

super_tmp_names = []
if r.status_code == 200:
    files = [
        {'filename': f'{TEST_MARKER}_a.pdf', 'size': 1024},
        {'filename': f'{TEST_MARKER}_b.doc', 'size': 2048},
        {'filename': f'{TEST_MARKER}_c.docx', 'size': 3072},
    ]
    r2 = create_tmp(super_headers, files)
    results['superadmin_create_upload_urls'] = (r2.status_code == 200)
    print('create_tmp_uploads', r2.status_code, r2.text)
    if r2.status_code == 200:
        info = r2.json()
        upload_urls = []
        file_ok = True
        for f in info.get('files', []):
            if not f.get('ok'):
                file_ok = False
                print('file rejected payload:', f)
            else:
                upload_urls.append((f['filename'], f['tmp_name'], f['upload_url']))
                super_tmp_names.append(f['tmp_name'])
        results['superadmin_file_request'] = file_ok
        put_results = {}
        for filename, tmp_name, upload_url in upload_urls:
            ext = Path(filename).suffix.lower()
            content = FILE_CONTENTS.get(ext, b'TEST')
            put = put_file(upload_url, content)
            ok = (put.status_code == 200)
            put_results[ext] = ok
            print('PUT', filename, put.status_code, put.text[:200])
        results['superadmin_pdf_upload'] = put_results.get('.pdf', False)
        results['superadmin_doc_upload'] = put_results.get('.doc', False)
        results['superadmin_docx_upload'] = put_results.get('.docx', False)

        r3 = validate_tmp(super_headers, super_tmp_names)
        results['superadmin_validation'] = (r3.status_code == 200 and all(item.get('valid') for item in r3.json().get('files', [])))
        print('validate_tmp', r3.status_code, r3.text)

        payload = {
            'tmp_names': super_tmp_names,
            'title': f'{TEST_MARKER} Super Admin Bulk',
            'description': f'{TEST_MARKER} super admin bulk registration',
            'category': 'Legislation',
            'document_type': 'Ordinance',
            'current_office': 'SB Secretariat',
            'assigned_to': 'SuperTester',
            'author': 'SuperTester',
            'priority': 'High',
        }
        r4 = confirm_tmp(super_headers, payload)
        results['superadmin_confirmation'] = (r4.status_code == 200 and r4.json().get('registered') == len(super_tmp_names))
        print('confirm_tmp', r4.status_code, r4.text)
    else:
        results['superadmin_file_request'] = False
        results['superadmin_pdf_upload'] = False
        results['superadmin_doc_upload'] = False
        results['superadmin_docx_upload'] = False
        results['superadmin_validation'] = False
        results['superadmin_confirmation'] = False
else:
    results['superadmin_create_upload_urls'] = False
    results['superadmin_file_request'] = False
    results['superadmin_pdf_upload'] = False
    results['superadmin_doc_upload'] = False
    results['superadmin_docx_upload'] = False
    results['superadmin_validation'] = False
    results['superadmin_confirmation'] = False

counts_after_super = db_counts()
print('DB counts after super admin:', counts_after_super)
results['superadmin_postgres'] = counts_after_super['documents'] > counts_before['documents']

super_docs = query_docs_by_title(f'{TEST_MARKER} Super Admin Bulk')
results['superadmin_docs_inserted'] = len(super_docs) == len(super_tmp_names) and all(d.created_by == 'devadmin' for d in super_docs)
print('super admin docs found:', len(super_docs))
for d in super_docs:
    print('doc', d.id, d.tracking_number, d.title, d.attachment_name, d.created_by, d.status, d.created_at, d.document_type, d.category)

audit_entries = query_audits('devadmin', 'BULK_DOCUMENT_REGISTRATION')
results['superadmin_audit'] = len(audit_entries) > 0
print('audit entries found:', len(audit_entries))
for a in audit_entries[:3]:
    print('audit', a.id, a.actor, a.action, a.target_type, a.details, a.created_at)

# Employee with permission
print('\n=== EMPLOYEE WITH PERMISSION ===')
r = login(*EMPLOYEE_WITH)
results['employee_with_login'] = (r.status_code == 200)
print('login', r.status_code, r.text[:200])
employee_with_headers = {'Authorization': f"Bearer {r.json().get('access_token')}"} if r.status_code == 200 else {}
emp_tmp_names = []
if r.status_code == 200:
    files = [
        {'filename': f'{TEST_MARKER}_emp_a.pdf', 'size': 1024},
        {'filename': f'{TEST_MARKER}_emp_b.doc', 'size': 2048},
        {'filename': f'{TEST_MARKER}_emp_c.docx', 'size': 3072},
    ]
    r2 = create_tmp(employee_with_headers, files)
    results['employee_with_create_upload_urls'] = (r2.status_code == 200)
    print('create_tmp_uploads', r2.status_code, r2.text)
    if r2.status_code == 200:
        info = r2.json()
        emp_upload_ok = True
        emp_put_results = {}
        for f in info.get('files', []):
            if not f.get('ok'):
                emp_upload_ok = False
                print('file rejected', f)
                continue
            emp_tmp_names.append(f['tmp_name'])
            put = put_file(f['upload_url'], FILE_CONTENTS.get(Path(f['filename']).suffix.lower(), b'TEST'))
            ok = put.status_code == 200
            emp_put_results[Path(f['filename']).suffix.lower()] = ok
            print('PUT', f['filename'], put.status_code, put.text[:200])
        results['employee_with_pdf_upload'] = emp_put_results.get('.pdf', False)
        results['employee_with_doc_upload'] = emp_put_results.get('.doc', False)
        results['employee_with_docx_upload'] = emp_put_results.get('.docx', False)
        r3 = validate_tmp(employee_with_headers, emp_tmp_names)
        results['employee_with_validation'] = (r3.status_code == 200 and all(item.get('valid') for item in r3.json().get('files', [])))
        print('validate_tmp', r3.status_code, r3.text)
        payload = {
            'tmp_names': emp_tmp_names,
            'title': f'{TEST_MARKER} Employee Bulk',
            'description': f'{TEST_MARKER} employee bulk registration',
            'category': 'Legislation',
            'document_type': 'Ordinance',
            'current_office': 'SB Secretariat',
            'assigned_to': 'EmployeeTester',
            'author': 'EmployeeTester',
            'priority': 'Medium',
        }
        r4 = confirm_tmp(employee_with_headers, payload)
        results['employee_with_confirmation'] = (r4.status_code == 200 and r4.json().get('registered') == len(emp_tmp_names))
        print('confirm_tmp', r4.status_code, r4.text)
    else:
        results['employee_with_validation'] = False
        results['employee_with_confirmation'] = False
else:
    results['employee_with_create_upload_urls'] = False
    results['employee_with_validation'] = False
    results['employee_with_confirmation'] = False

# Employee without permission
print('\n=== EMPLOYEE WITHOUT PERMISSION ===')
r = login(*EMPLOYEE_WITHOUT)
results['employee_without_login'] = (r.status_code == 200)
print('login', r.status_code, r.text[:200])
employee_without_headers = {'Authorization': f"Bearer {r.json().get('access_token')}"} if r.status_code == 200 else {}
if r.status_code == 200:
    r2 = create_tmp(employee_without_headers, [{'filename': f'{TEST_MARKER}_no_perm.pdf', 'size': 1024}])
    results['employee_without_create_tmp_blocked'] = (r2.status_code == 403)
    print('create_tmp_uploads', r2.status_code, r2.text)
    r3 = validate_tmp(employee_without_headers, ['does_not_exist.tmp'])
    results['employee_without_validate_blocked'] = (r3.status_code == 403)
    print('validate_tmp', r3.status_code, r3.text)
    r4 = confirm_tmp(employee_without_headers, {'tmp_names': ['does_not_exist.tmp']})
    results['employee_without_confirm_blocked'] = (r4.status_code == 403)
    print('confirm_tmp', r4.status_code, r4.text)
else:
    results['employee_without_create_tmp_blocked'] = False
    results['employee_without_validate_blocked'] = False
    results['employee_without_confirm_blocked'] = False

# SB member
print('\n=== SB MEMBER ===')
r = login(*SB_MEMBER)
results['sb_login'] = (r.status_code == 200)
print('login', r.status_code, r.text[:200])
sb_headers = {'Authorization': f"Bearer {r.json().get('access_token')}"} if r.status_code == 200 else {}
if r.status_code == 200:
    r2 = create_tmp(sb_headers, [{'filename': f'{TEST_MARKER}_sb.pdf', 'size': 1024}])
    results['sb_create_tmp_blocked'] = (r2.status_code == 403)
    print('create_tmp_uploads', r2.status_code, r2.text)
    r3 = validate_tmp(sb_headers, ['does_not_exist.tmp'])
    results['sb_validate_blocked'] = (r3.status_code == 403)
    print('validate_tmp', r3.status_code, r3.text)
    r4 = confirm_tmp(sb_headers, {'tmp_names': ['does_not_exist.tmp']})
    results['sb_confirm_blocked'] = (r4.status_code == 403)
    print('confirm_tmp', r4.status_code, r4.text)
else:
    results['sb_create_tmp_blocked'] = False
    results['sb_validate_blocked'] = False
    results['sb_confirm_blocked'] = False

# Unauthenticated tests
print('\n=== UNAUTHENTICATED ===')
unauth_create = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files': [{'filename': f'{TEST_MARKER}_unauth.pdf', 'size': 1024}]}, verify=False, timeout=30)
results['unauthenticated_create_tmp_blocked'] = (unauth_create.status_code == 401)
print('create_tmp_uploads', unauth_create.status_code, unauth_create.text[:200])

unauth_validate = s.post(f"{BACKEND}/documents/bulk-register/validate_tmp", json={'tmp_names': ['does_not_exist.tmp']}, verify=False, timeout=30)
results['unauthenticated_validate_blocked'] = (unauth_validate.status_code == 401)
print('validate_tmp', unauth_validate.status_code, unauth_validate.text[:200])
unauth_confirm = s.post(f"{BACKEND}/documents/bulk-register/confirm_tmp", json={'tmp_names': ['does_not_exist.tmp']}, verify=False, timeout=30)
results['unauthenticated_confirm_blocked'] = (unauth_confirm.status_code == 401)
print('confirm_tmp', unauth_confirm.status_code, unauth_confirm.text[:200])

# Invalid JWT tests
print('\n=== INVALID JWT ===')
bad_headers = {'Authorization': 'Bearer invalid-token'}
invalid_create = s.post(f"{BACKEND}/documents/uploads/create_tmp_uploads", json={'files': [{'filename': f'{TEST_MARKER}_bad.pdf', 'size': 1024}]}, headers=bad_headers, verify=False, timeout=30)
results['invalid_jwt_create_tmp_blocked'] = (invalid_create.status_code == 401)
print('create_tmp_uploads', invalid_create.status_code, invalid_create.text[:200])
invalid_validate = s.post(f"{BACKEND}/documents/bulk-register/validate_tmp", json={'tmp_names': ['does_not_exist.tmp']}, headers=bad_headers, verify=False, timeout=30)
results['invalid_jwt_validate_blocked'] = (invalid_validate.status_code == 401)
print('validate_tmp', invalid_validate.status_code, invalid_validate.text[:200])
invalid_confirm = s.post(f"{BACKEND}/documents/bulk-register/confirm_tmp", json={'tmp_names': ['does_not_exist.tmp']}, headers=bad_headers, verify=False, timeout=30)
results['invalid_jwt_confirm_blocked'] = (invalid_confirm.status_code == 401)
print('confirm_tmp', invalid_confirm.status_code, invalid_confirm.text[:200])

# File type test
print('\n=== FILE TYPE VALIDATION ===')
invalid_exts = ['jpg','png','txt','xlsx','zip','exe']
invalid_blocked = True
for ext in invalid_exts:
    r = create_tmp(super_headers, [{'filename': f'{TEST_MARKER}_invalid.{ext}', 'size': 1024}])
    blocked = r.status_code == 400 or (r.status_code == 200 and r.json().get('files',[{}])[0].get('ok') is False)
    print('invalid', ext, r.status_code, r.text[:200])
    if not blocked:
        invalid_blocked = False
results['file_validation_invalid_types'] = invalid_blocked
results['file_validation_pdf'] = results.get('superadmin_pdf_upload', False)
results['file_validation_doc'] = results.get('superadmin_doc_upload', False)
results['file_validation_docx'] = results.get('superadmin_docx_upload', False)

# Duplicate confirmation protection
print('\n=== DUPLICATE CONFIRMATION ===')
dup_protected = False
if super_headers and results['superadmin_login']:
    rdup = create_tmp(super_headers, [{'filename': f'{TEST_MARKER}_dup.pdf', 'size': 1024}])
    print('dup create_tmp', rdup.status_code, rdup.text)
    if rdup.status_code == 200:
        info = rdup.json().get('files', [])[0]
        if info.get('ok'):
            tmp = info['tmp_name']
            put = put_file(info['upload_url'], FILE_CONTENTS['.pdf'])
            print('dup PUT', put.status_code, put.text[:200])
            rdupval = validate_tmp(super_headers, [tmp])
            print('dup validate', rdupval.status_code, rdupval.text)
            first = confirm_tmp(super_headers, {'tmp_names': [tmp], 'title': f'{TEST_MARKER} Dup1'})
            print('first confirm', first.status_code, first.text)
            second = confirm_tmp(super_headers, {'tmp_names': [tmp], 'title': f'{TEST_MARKER} Dup2'})
            print('second confirm', second.status_code, second.text)
            dup_protected = second.status_code != 200
results['duplicate_confirmation_protection'] = dup_protected

# Upload token security
print('\n=== UPLOAD TOKEN SECURITY ===')
user_binding = False
invalid_token_rejected = False
expired_rejected = False
single_use = False
if results['superadmin_create_upload_urls']:
    # pick a fresh token from super admin create_tmp, if possible above
    rtoken = create_tmp(super_headers, [{'filename': f'{TEST_MARKER}_security.pdf', 'size': 1024}])
    if rtoken.status_code == 200:
        token_info = rtoken.json()['files'][0]
        if token_info.get('ok'):
            upload_url = token_info['upload_url']
            put_any = put_file(upload_url, FILE_CONTENTS['.pdf'])
            print('initial token PUT', put_any.status_code, put_any.text[:200])
            r_emp = login(*EMPLOYEE_WITH)
            if r_emp.status_code == 200:
                put_as_other = put_file(upload_url, FILE_CONTENTS['.pdf'])
                print('reuse token as other user PUT', put_as_other.status_code, put_as_other.text[:200])
                user_binding = (put_as_other.status_code != 200)
            else:
                user_binding = False
            # invalid token
            if '?upload_token=' in upload_url:
                bad_url = upload_url.replace('upload_token=', 'upload_token=badtoken')
                bad_put = put_file(bad_url, FILE_CONTENTS['.pdf'])
                print('invalid token PUT', bad_put.status_code, bad_put.text[:200])
                invalid_token_rejected = (bad_put.status_code == 401)
            # expire token metadata
            from urllib.parse import unquote, urlparse, parse_qs
            parsed = urlparse(upload_url)
            tmp_name = unquote(parsed.path.split('/')[-1])
            token_val = parse_qs(parsed.query).get('upload_token', [None])[0]
            meta_path = Path('uploads') / f'{tmp_name}.meta.json'
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                meta['expires_at'] = int(time.time()) - 60
                meta_path.write_text(json.dumps(meta))
                expired = put_file(upload_url, FILE_CONTENTS['.pdf'])
                print('expired token PUT', expired.status_code, expired.text[:200])
                expired_rejected = (expired.status_code == 401)
            # single-use: re-put after upload
            reuse = put_file(upload_url, FILE_CONTENTS['.pdf'])
            print('reuse token PUT', reuse.status_code, reuse.text[:200])
            single_use = (reuse.status_code != 200)

results['upload_token_user_binding'] = user_binding
results['upload_token_invalid_rejected'] = invalid_token_rejected
results['upload_token_expired_rejected'] = expired_rejected
results['upload_token_single_use'] = single_use

counts_final = db_counts()
print('\nDB counts final:', counts_final)

print('\n=== RESULTS ===')
for k, v in results.items():
    print(k, v)

print('\nCreated docs by title markers:')
for title in [f'{TEST_MARKER} Super Admin Bulk', f'{TEST_MARKER} Employee Bulk']:
    docs = query_docs_by_title(title)
    print(title, len(docs))

print('\nNOTE: If unprotected upload URLs are observed, this is a behavior/property of the current implementation.')
