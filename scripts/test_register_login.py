#!/usr/bin/env python3
"""Test admin register -> employee login flow.

Usage: run with workspace venv python.
"""
import os
import sys
from pathlib import Path
import time

project = Path(__file__).resolve().parents[1]
if str(project) not in sys.path:
    sys.path.insert(0, str(project))

import requests

BACKEND = os.getenv("BACKEND_URL", "http://127.0.0.1:8011")
ADMIN_USER = os.getenv("TEST_ADMIN_USER", "devadmin")
ADMIN_PASS = os.getenv("TEST_ADMIN_PASS", "password123")

new_username = f"testuser_{int(time.time())}"
new_password = "TestPass!23"

print("Backend:", BACKEND)

# Login admin (login endpoint expects form data)
r = requests.post(f"{BACKEND}/auth/login", data={"username": ADMIN_USER, "password": ADMIN_PASS})
if r.status_code != 200:
    print("Admin login failed:", r.status_code, r.text)
    sys.exit(1)

token = r.json().get("access_token")
print("Admin token obtained.")

headers = {"Authorization": f"Bearer {token}"}

# Register new user (endpoint expects query params)
params = {"username": new_username, "password": new_password, "role": "Employee"}
rr = requests.post(f"{BACKEND}/auth/register", params=params, headers=headers)
print("Register status:", rr.status_code, rr.text)
if rr.status_code != 200 and rr.status_code != 201:
    sys.exit(1)

# Attempt login as new user (login endpoint expects form data)
rl = requests.post(f"{BACKEND}/auth/login", data={"username": new_username, "password": new_password})
print("New user login status:", rl.status_code, rl.text)
if rl.status_code == 200:
    print("Success: new user can login.")
else:
    print("Failure: new user cannot login.")
    sys.exit(2)
