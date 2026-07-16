from fastapi import FastAPI, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import uuid
import qrcode
import io
from fastapi.responses import StreamingResponse
from .database import engine, Base, get_db
from . import models

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# Auto-generate the SQLite database and empty tables on launch
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    pass

app = FastAPI(title="LGU Tolosa SB Legislative Tracking Backend")

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
    return {"message": f"{item_type} Registered Successfully", "tracking_uuid": unique_id}

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