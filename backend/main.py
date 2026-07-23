from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import qrcode
import io
import re
import json
import os
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from .database import engine, Base, get_db
from . import models
from sqlalchemy import desc

# Import document parsing libraries
from docx import Document as DocxDocument
from pypdf import PdfReader

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
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

# Helper function to extract text from documents
def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract text from .docx or .pdf files"""
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
                text += page.extract_text() + "\n"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing PDF: {str(e)}")
    
    else:
        raise HTTPException(status_code=400, detail="Only .docx and .pdf files are supported")
    
    return text

# Helper function to parse document content
def parse_document_content(text: str) -> dict:
    """Parse extracted text to extract title, item_type, and committee"""
    lines = text.split('\n')
    
    # Determine item type
    item_type = "Committee Report"  # default
    text_upper = text.upper()
    
    if "ORDINANCE" in text_upper:
        item_type = "Ordinance"
    elif "RESOLUTION" in text_upper:
        item_type = "Resolution"
    
    # Extract committee
    committee = "General Committee"  # default
    committee_patterns = [
        r"committee\s+on\s+([^\n,]+)",
        r"assigned\s+to\s*:\s*([^\n,]+)",
        r"committee\s+of\s+([^\n,]+)",
    ]
    
    for pattern in committee_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            committee = match.group(1).strip()
            # Capitalize properly
            committee = " ".join([word.capitalize() for word in committee.split()])
            break
    
    # Extract title - get first substantial line after headers
    title = "Untitled Document"
    for line in lines:
        line = line.strip()
        # Skip empty lines and common headers
        if line and len(line) > 5 and not any(header in line.upper() for header in 
            ["ORDINANCE", "RESOLUTION", "COMMITTEE ON", "ASSIGNED TO", "PROPOSED", "BE IT"]):
            title = line[:100]  # Limit to 100 chars
            break
    
    # If title is still default, extract from document type lines
    if title == "Untitled Document":
        for line in lines:
            line = line.strip()
            if ("ORDINANCE" in line.upper() or "RESOLUTION" in line.upper()) and len(line) > 10:
                title = line[:100]
                break
    
    return {
        "title": title,
        "item_type": item_type,
        "committee": committee
    }


# Auto-generate the SQLite database and empty tables on launch
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    pass

def ensure_user_role_column():
    with engine.begin() as connection:
        columns = [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if "role" not in columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'Admin'")
        connection.exec_driver_sql("UPDATE users SET role = 'Admin' WHERE role IS NULL OR role = ''")


try:
    ensure_user_role_column()
except Exception:
    pass

app = FastAPI(title="LGU Tolosa SB Legislative Tracking Backend")

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
WORKFLOW_CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workflow_config.json"))
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


def normalize_workflow_steps(steps: list[str]) -> list[str]:
    normalized_steps = []
    seen = set()
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

@app.get("/")
def root():
    return {"status": "SB Tolosa System Engine Live"}

@app.post("/auth/register")
def register_user(username: str, password: str, role: str = "Admin", db: Session = Depends(get_db)):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    try:
        new_user = models.User(
            username=username,
            hashed_password=get_password_hash(password),
            role=role.strip() or "Admin",
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {exc}") from exc

    record_audit_log(
        db,
        actor=new_user.username,
        action="USER_REGISTERED",
        target_type="User",
        target_id=str(new_user.id),
        details=f"Created admin account for {new_user.username}",
    )

    return {"message": "User registered successfully", "username": new_user.username}


@app.get("/auth/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.id.asc()).all()
    return {
        "items": [
            {
                "id": user.id,
                "username": user.username,
                "role": user.role or "Admin",
            }
            for user in users
        ]
    }


@app.put("/auth/users/{username}/role")
def update_user_role(username: str, role: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role.strip() or "Admin"
    db.commit()
    db.refresh(user)

    record_audit_log(
        db,
        actor="system",
        action="USER_ROLE_UPDATED",
        target_type="User",
        target_id=str(user.id),
        details=f"Updated {user.username} role to {user.role}",
    )

    return {"message": "User role updated", "username": user.username, "role": user.role}


@app.delete("/auth/users/{username}")
def delete_user(username: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = user.id
    db.delete(user)
    db.commit()

    record_audit_log(
        db,
        actor="system",
        action="USER_DELETED",
        target_type="User",
        target_id=str(user_id),
        details=f"Deleted user {username}",
    )

    return {"message": "User deleted", "username": username}

@app.post("/auth/login")
def login_user(username: str, password: str, db: Session = Depends(get_db)):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    record_audit_log(
        db,
        actor=user.username,
        action="USER_LOGIN",
        target_type="Auth",
        target_id=user.username,
        details="Successful login",
    )

    return {"message": "Login successful", "username": user.username}

# Route: Parse document template and extract metadata
@app.post("/legislative/parse")
async def parse_document(file: UploadFile = File(...)):
    """Parse uploaded .docx or .pdf document to extract title, type, and committee"""
    try:
        file_bytes = await file.read()
        
        # Extract text from file
        text = extract_text_from_file(file_bytes, file.filename)
        
        # Parse content
        parsed_data = parse_document_content(text)
        
        return parsed_data
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing document: {str(e)}")


# Route 1: Register a new Legislative Document
@app.post("/legislative/register")
def register_item(title: str, item_type: str, committee: str, db: Session = Depends(get_db)):
    unique_id = str(uuid.uuid4())
    current_workflow_steps = load_workflow_steps()
    initial_status = current_workflow_steps[0] if current_workflow_steps else DEFAULT_WORKFLOW_STEPS[0]
    new_item = models.LegislativeItem(
        tracking_uuid=unique_id, 
        title=title, 
        item_type=item_type, 
        assigned_committee=committee,
        current_status=initial_status,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)

    record_audit_log(
        db,
        actor="system",
        action="LEGISLATIVE_ITEM_REGISTERED",
        target_type="LegislativeItem",
        target_id=str(new_item.id),
        details=f"Registered {item_type}: {title} for committee {committee}",
    )

    return {
        "message": f"{item_type} Registered Successfully",
        "id": new_item.id,
        "tracking_uuid": unique_id,
        "current_stage": new_item.current_status,
    }


@app.get("/legislative/list")
def list_legislative_items(db: Session = Depends(get_db)):
    items = db.query(models.LegislativeItem).order_by(models.LegislativeItem.id.asc()).all()
    return {
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "type": item.item_type,
                "committee": item.assigned_committee,
                "status": item.current_status,
                "uuid": item.tracking_uuid,
            }
            for item in items
        ]
    }


@app.delete("/legislative/delete/{tracking_uuid}")
def delete_legislative_item(
    tracking_uuid: str,
    actor: str = "system",
    location: str = "Admin Dashboard",
    db: Session = Depends(get_db),
):
    item = db.query(models.LegislativeItem).filter(models.LegislativeItem.tracking_uuid == tracking_uuid).first()
    if not item:
        raise HTTPException(status_code=404, detail="Legislative record not found")

    db.query(models.LegislativeTrackingLog).filter(models.LegislativeTrackingLog.item_id == item.id).delete(synchronize_session=False)
    db.delete(item)
    db.commit()

    record_audit_log(
        db,
        actor=actor,
        action="LEGISLATIVE_ITEM_DELETED",
        target_type="LegislativeItem",
        target_id=str(item.id),
        details=f"Deleted document at {location}",
    )

    return {
        "message": "Legislative record deleted",
        "tracking_uuid": tracking_uuid,
        "deleted_id": item.id,
    }


@app.get("/uploads/{filename:path}")
def get_uploaded_file(filename: str):
    # Serve uploaded files from the uploads directory. Protect against path traversal.
    joined_path = os.path.join(UPLOAD_DIR, filename)
    full_path = os.path.realpath(joined_path)
    if not os.path.exists(full_path) or os.path.commonpath([full_path, UPLOAD_DIR]) != UPLOAD_DIR:
        raise HTTPException(status_code=404, detail="File not found")

    # Let the browser handle content-disposition
    return FileResponse(full_path, media_type="application/octet-stream", filename=os.path.basename(full_path))


@app.get("/legislative/preview/{filename}")
def preview_uploaded_file(filename: str):
    # Serve a previewable representation: PDFs are returned so browsers can render them;
    # DOCX files are parsed server-side and returned as extracted plain text JSON.
    joined_path = os.path.join(UPLOAD_DIR, filename)
    full_path = os.path.realpath(joined_path)
    if not os.path.exists(full_path) or os.path.commonpath([full_path, UPLOAD_DIR]) != UPLOAD_DIR:
        raise HTTPException(status_code=404, detail="File not found")

    if filename.lower().endswith('.pdf'):
        # Return PDF without Content-Disposition filename so browsers render inline instead of forcing download
        return FileResponse(full_path, media_type="application/pdf")

    if filename.lower().endswith('.docx'):
        try:
            with open(full_path, 'rb') as f:
                file_bytes = f.read()
            text = extract_text_from_file(file_bytes, filename)
            return JSONResponse({"text": text})
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Preview error: {exc}")

    # Unsupported preview types
    raise HTTPException(status_code=400, detail="Unsupported file type for preview")

# Route 2: Generate and stream a downloadable QR code image matching the document UUID
@app.get("/legislative/qrcode/{tracking_uuid}")
def get_qrcode(tracking_uuid: str):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(tracking_uuid)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return StreamingResponse(buf, media_type="image/png")

# Route 3: Endpoint for the QR application to drop a tracking log
@app.post("/legislative/track/{tracking_uuid}")
def track_item(tracking_uuid: str, location: str, action: str, scanned_by: str, db: Session = Depends(get_db)):
    item = db.query(models.LegislativeItem).filter(models.LegislativeItem.tracking_uuid == tracking_uuid).first()
    if not item:
        raise HTTPException(status_code=404, detail="Legislative record not found")
    
    item.current_status = action
    
    log_entry = models.LegislativeTrackingLog(
        item_id=item.id, 
        location_stamp=location, 
        action_taken=action,
        scanned_by=scanned_by
    )
    db.add(log_entry)
    db.commit()

    record_audit_log(
        db,
        actor=scanned_by,
        action="TRACKING_UPDATE",
        target_type="LegislativeItem",
        target_id=str(item.id),
        details=f"{action} at {location}",
    )
    
    return {
        "message": "Tracking log updated", 
        "item_title": item.title, 
        "current_stage": item.current_status
    }


@app.post("/legislative/advance/{tracking_uuid}")
def advance_item_status(
    tracking_uuid: str,
    actor: str = "system",
    location: str = "Admin Dashboard",
    db: Session = Depends(get_db),
):
    item = db.query(models.LegislativeItem).filter(models.LegislativeItem.tracking_uuid == tracking_uuid).first()
    if not item:
        raise HTTPException(status_code=404, detail="Legislative record not found")

    workflow_steps = load_workflow_steps()
    if not workflow_steps:
        raise HTTPException(status_code=400, detail="No workflow milestones are configured")

    current_stage = item.current_status or workflow_steps[0]
    if current_stage not in workflow_steps:
        current_index = -1
    else:
        current_index = workflow_steps.index(current_stage)

    next_index = current_index + 1
    if next_index >= len(workflow_steps):
        next_stage = workflow_steps[-1]
        message = "Document is already at the final milestone"
    else:
        next_stage = workflow_steps[next_index]
        message = f"Advanced to {next_stage}"

    item.current_status = next_stage

    db.add(
        models.LegislativeTrackingLog(
            item_id=item.id,
            location_stamp=location,
            action_taken=next_stage,
            scanned_by=actor,
        )
    )
    db.commit()

    record_audit_log(
        db,
        actor=actor,
        action="WORKFLOW_ADVANCED",
        target_type="LegislativeItem",
        target_id=str(item.id),
        details=f"{current_stage} -> {next_stage} at {location}",
    )

    return {
        "message": message,
        "item_title": item.title,
        "current_stage": item.current_status,
        "next_stage": next_stage,
    }


@app.get("/audit/logs")
def get_audit_logs(limit: int = 200, db: Session = Depends(get_db)):
    logs = (
        db.query(models.AuditLog)
        .order_by(desc(models.AuditLog.created_at), desc(models.AuditLog.id))
        .limit(limit)
        .all()
    )

    return {
        "items": [
            {
                "id": log.id,
                "actor": log.actor,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "details": log.details,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }


@app.get("/workflow/config")
def get_workflow_config():
    statuses = load_workflow_steps()
    return {
        "statuses": statuses,
        "default_status": statuses[0] if statuses else None,
        "uses_default_template": statuses == DEFAULT_WORKFLOW_STEPS,
    }


@app.put("/workflow/config")
def update_workflow_config(payload: WorkflowConfigPayload):
    statuses = save_workflow_steps(payload.statuses)
    return {
        "message": "Workflow updated successfully",
        "statuses": statuses,
        "default_status": statuses[0] if statuses else None,
    }


@app.post("/workflow/reset")
def reset_workflow_config():
    statuses = save_workflow_steps(DEFAULT_WORKFLOW_STEPS)
    return {
        "message": "Workflow reset to default milestones",
        "statuses": statuses,
        "default_status": statuses[0] if statuses else None,
    }