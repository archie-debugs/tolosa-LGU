#!/usr/bin/env python3
"""Seed a Super Administrator user into the database for testing.

Usage:
    python scripts/seed_super_admin.py [username] [password]

If DATABASE_URL points to PostgreSQL, this will insert the user there.
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from Backends.backend.database import SessionLocal, engine
from Backends.backend import models
from Backends.backend.core import get_password_hash


def seed(username: str, password: str):
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.username == username).first()
        if existing:
            print(f"User {username} already exists (id={existing.id}).")
            return
        user = models.User(
            username=username,
            hashed_password=get_password_hash(password),
            role="Super Administrator",
            permissions=str(["*"]),
            status="Active",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created Super Administrator: {username} (id={user.id})")
    finally:
        db.close()


if __name__ == '__main__':
    uname = sys.argv[1] if len(sys.argv) > 1 else "a"
    pwd = sys.argv[2] if len(sys.argv) > 2 else "a"
    seed(uname, pwd)
