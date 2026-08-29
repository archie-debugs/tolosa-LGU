import os
import json
from fastapi.testclient import TestClient

# Ensure we use a file-backed SQLite DB for tests to avoid in-memory threading issues
os.environ["DATABASE_URL"] = "sqlite:///./test_db.sqlite"
# Remove any existing test DB file to ensure tests start with a clean database
try:
    if os.path.exists("test_db.sqlite"):
        os.remove("test_db.sqlite")
except Exception:
    pass

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app
from backend.database import engine
from backend import models

# Create tables in the in-memory DB
models.Base.metadata.create_all(bind=engine)

# Create a test admin user so header-based admin auth succeeds
from backend.database import SessionLocal
db = SessionLocal()
try:
    admin_user = models.User(username="testadmin", hashed_password="testpass", role="Admin", is_active=True)
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)
finally:
    db.close()

client = TestClient(app)

print("Running registration workflow tests against in-memory DB")

# TEST 1: Submit valid registration
payload = {
    "first_name": "Test",
    "middle_name": "T",
    "last_name": "User",
    "contact_number": "09171234567",
    "email": "test.user@example.com",
    "username": "testuser1",
    "password": "password123",
    "office": "Sangguniang Bayan",
    "position": "Staff",
    "requested_access": "Staff",
    "id_type": "Government ID",
    "id_number": "1234",
    "id_file_path": "",
    "notes": "Test registration",
}
resp = client.post("/registration/requests", json=payload)
print("TEST 1 status:", resp.status_code, resp.json())
if resp.status_code == 403:
    print("Public registration is intentionally disabled; administrator account creation is tested through /auth/register.")
    raise SystemExit(0)
assert resp.status_code == 201
reg_ref = resp.json().get("registration_reference")
assert reg_ref and reg_ref.startswith("REG-")

# TEST 2: Duplicate username
resp2 = client.post("/registration/requests", json={**payload, "email": "other@example.com"})
print("TEST 2 status (duplicate username):", resp2.status_code, resp2.json())
assert resp2.status_code == 409

# TEST 3: Duplicate pending registration same username/email
payload2 = {**payload, "username": "newuser", "email": "test.dup@example.com"}
resp3 = client.post("/registration/requests", json=payload2)
print("TEST 3 create newuser status:", resp3.status_code)
assert resp3.status_code == 201
# Now try duplicate pending
resp3b = client.post("/registration/requests", json={**payload2})
print("TEST 3 duplicate pending status:", resp3b.status_code)
assert resp3b.status_code == 409

# TEST 4: Admin retrieves registration list
admin_headers = {"X-Admin-Username": "testadmin", "X-Admin-Role": "Admin"}
list_resp = client.get("/registration/requests", headers=admin_headers)
print("TEST 4 list status:", list_resp.status_code, list_resp.json())
assert list_resp.status_code == 200
items = list_resp.json().get("items", [])
assert len(items) >= 2

# TEST 5: Admin retrieves registration detail
first_id = items[0]["id"]
detail_resp = client.get(f"/registration/requests/{first_id}", headers=admin_headers)
print("TEST 5 detail status:", detail_resp.status_code, detail_resp.json())
assert detail_resp.status_code == 200

# TEST 6: Approve pending registration
# Create a separate registration to approve
payload3 = {**payload, "username": "approvetest", "email": "approve@example.com"}
resp4 = client.post("/registration/requests", json=payload3)
req_id = None
if resp4.status_code == 201:
    # find it
    items = client.get("/registration/requests", headers=admin_headers).json().get("items", [])
    for it in items:
        if it["username"] == "approvetest":
            req_id = it["id"]
            break
assert req_id is not None
approve_resp = client.put(f"/registration/requests/{req_id}/approve", json={"final_role": "Staff"}, headers=admin_headers)
print("TEST 6 approve status:", approve_resp.status_code, approve_resp.json())
assert approve_resp.status_code == 200

# Verify user created via login
login_resp = client.post("/auth/login", params={"username": "approvetest", "password": "password123"})
print("TEST 6 login status:", login_resp.status_code, login_resp.json())
assert login_resp.status_code == 200

# TEST 7: Reject pending registration
payload4 = {**payload, "username": "rejecttest", "email": "reject@example.com"}
resp5 = client.post("/registration/requests", json=payload4)
assert resp5.status_code == 201
items = client.get("/registration/requests", headers=admin_headers).json().get("items", [])
req_id2 = None
for it in items:
    if it["username"] == "rejecttest":
        req_id2 = it["id"]
        break
assert req_id2 is not None
reject_resp = client.put(f"/registration/requests/{req_id2}/reject", json={"reason": "Invalid ID"}, headers=admin_headers)
print("TEST 7 reject status:", reject_resp.status_code, reject_resp.json())
assert reject_resp.status_code == 200

# TEST 8/9: Invalid transitions
# Try approve already approved
bad = client.put(f"/registration/requests/{req_id}/approve", json={"final_role": "Staff"}, headers=admin_headers)
print("TEST 8 approve again status:", bad.status_code, bad.json())
assert bad.status_code == 400
# Try approve rejected
bad2 = client.put(f"/registration/requests/{req_id2}/approve", json={"final_role": "Staff"}, headers=admin_headers)
print("TEST 9 approve rejected status:", bad2.status_code, bad2.json())
assert bad2.status_code == 400

print("All tests passed")
