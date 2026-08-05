from fastapi import HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
import uuid
import secrets
import re
import json
import os
import io
from urllib.parse import quote as urlquote
import qrcode
from docx import Document as DocxDocument
from pypdf import PdfReader
from .database import engine, Base, get_db
from . import models

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
WORKFLOW_CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workflow_config.json"))
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "https://192.168.1.4:8001").rstrip("/")
SCANNER_PUBLIC_URL = os.getenv("SCANNER_PUBLIC_URL", "https://192.168.1.4:8002").rstrip("/")
SCANNER_SESSION_TTL_MINUTES = 12 * 60
scanner_sessions: dict[str, dict[str, object]] = {}
DEFAULT_WORKFLOW_STEPS = [
    "Draft",
    "First Reading",
    "Committee Referral",
    "Public Hearing",
    "Second Reading",
    "Third/Final Reading",
    "Transmitted to Mayor",
    "Approved/Vetoed",
    "Published/Enacted",
]


class WorkflowConfigPayload(BaseModel):
    statuses: list[str]


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def record_audit_log(
    db: Session,
    *,
    actor: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: str | None = None,
):
    audit_log = models.AuditLog(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    return audit_log


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    text = ""

    if filename.lower().endswith('.docx'):
        try:
            doc = DocxDocument(io.BytesIO(file_bytes))
            text = "\n".join([para.text for para in doc.paragraphs])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing DOCX: {str(e)}")

    elif filename.lower().endswith('.pdf'):
        try:
            pdf_reader = PdfReader(io.BytesIO(file_bytes))
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing PDF: {str(e)}")

    else:
        raise HTTPException(status_code=400, detail="Only .docx and .pdf files are supported")

    return text


def parse_document_content(text: str) -> dict:
    lines = text.split('\n')
    item_type = "Committee Report"
    text_upper = text.upper()

    if "ORDINANCE" in text_upper:
        item_type = "Ordinance"
    elif "RESOLUTION" in text_upper:
        item_type = "Resolution"

    committee = "General Committee"
    committee_patterns = [
        r"committee\s+on\s+([^\n,]+)",
        r"assigned\s+to\s*:\s*([^\n,]+)",
        r"committee\s+of\s+([^\n,]+)",
    ]

    for pattern in committee_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            committee = match.group(1).strip()
            committee = " ".join([word.capitalize() for word in committee.split()])
            break

    title = "Untitled Document"
    for line in lines:
        line = line.strip()
        if line and len(line) > 5 and not any(header in line.upper() for header in [
            "ORDINANCE", "RESOLUTION", "COMMITTEE ON", "ASSIGNED TO", "PROPOSED", "BE IT",
        ]):
            title = line[:100]
            break

    if title == "Untitled Document":
        for line in lines:
            line = line.strip()
            if ("ORDINANCE" in line.upper() or "RESOLUTION" in line.upper()) and len(line) > 10:
                title = line[:100]
                break

    return {
        "title": title,
        "item_type": item_type,
        "committee": committee,
    }


def normalize_workflow_steps(steps: list[str]) -> list[str]:
    normalized_steps: list[str] = []
    seen: set[str] = set()
    for step in steps:
        value = str(step or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized_steps.append(value)
    return normalized_steps


def load_workflow_steps() -> list[str]:
    try:
        if os.path.exists(WORKFLOW_CONFIG_PATH):
            with open(WORKFLOW_CONFIG_PATH, "r", encoding="utf-8") as config_file:
                payload = json.load(config_file)
            steps = payload.get("statuses", DEFAULT_WORKFLOW_STEPS)
            normalized_steps = normalize_workflow_steps(steps)
            return normalized_steps or list(DEFAULT_WORKFLOW_STEPS)
    except Exception:
        pass
    return list(DEFAULT_WORKFLOW_STEPS)


def save_workflow_steps(steps: list[str]) -> list[str]:
    normalized_steps = normalize_workflow_steps(steps)
    if not normalized_steps:
        raise HTTPException(status_code=400, detail="At least one workflow status is required")
    with open(WORKFLOW_CONFIG_PATH, "w", encoding="utf-8") as config_file:
        json.dump({"statuses": normalized_steps}, config_file, indent=2)
    return normalized_steps


def _purge_expired_scanner_sessions() -> None:
    now = datetime.utcnow()
    expired_tokens = [token for token, session in scanner_sessions.items() if session.get("expires_at") and session["expires_at"] < now]
    for token in expired_tokens:
        scanner_sessions.pop(token, None)


def create_scanner_session(username: str, role: str) -> dict[str, str]:
    _purge_expired_scanner_sessions()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=SCANNER_SESSION_TTL_MINUTES)
    scanner_sessions[token] = {
        "username": username,
        "role": role,
        "expires_at": expires_at,
    }
    return {
        "token": token,
        "username": username,
        "role": role,
        "expires_at": expires_at.isoformat(),
    }


def validate_scanner_session(token: str) -> dict[str, object]:
    _purge_expired_scanner_sessions()
    session = scanner_sessions.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Scanner session expired or invalid")
    return session


def ensure_user_role_column() -> None:
    from .database import engine
    with engine.begin() as connection:
        columns = [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if "role" not in columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'Admin'")
        connection.exec_driver_sql("UPDATE users SET role = 'Admin' WHERE role IS NULL OR role = ''")


def ensure_current_location_column() -> None:
    from .database import engine
    with engine.begin() as connection:
        columns = [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(legislative_items)").fetchall()]
        if "current_location" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE legislative_items ADD COLUMN current_location VARCHAR NOT NULL DEFAULT 'Records Registry'"
            )
        connection.exec_driver_sql(
            "UPDATE legislative_items SET current_location = 'Records Registry' WHERE current_location IS NULL OR current_location = ''"
        )


def ensure_source_filename_column() -> None:
    from .database import engine
    with engine.begin() as connection:
        columns = [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(legislative_items)").fetchall()]
        if "source_filename" not in columns:
            connection.exec_driver_sql("ALTER TABLE legislative_items ADD COLUMN source_filename VARCHAR NULL")
