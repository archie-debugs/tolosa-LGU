from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import uuid
import qrcode
import io
import re
import os
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from .database import engine, Base, get_db
from . import models

# Import document parsing libraries
from docx import Document as DocxDocument
from pypdf import PdfReader

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

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

app = FastAPI(title="LGU Tolosa SB Legislative Tracking Backend")

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))

@app.get("/")
def root():
    return {"status": "SB Tolosa System Engine Live"}

@app.post("/auth/register")
def register_user(username: str, password: str, db: Session = Depends(get_db)):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    try:
        new_user = models.User(
            username=username,
            hashed_password=get_password_hash(password),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {exc}") from exc

    return {"message": "User registered successfully", "username": new_user.username}

@app.post("/auth/login")
def login_user(username: str, password: str, db: Session = Depends(get_db)):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

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
    new_item = models.LegislativeItem(
        tracking_uuid=unique_id, 
        title=title, 
        item_type=item_type, 
        assigned_committee=committee
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return {"message": f"{item_type} Registered Successfully", "id": new_item.id, "tracking_uuid": unique_id}


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
    
    return {
        "message": "Tracking log updated", 
        "item_title": item.title, 
        "current_stage": item.current_status
    }