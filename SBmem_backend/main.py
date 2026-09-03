import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

load_dotenv()

from backend import models
from backend.auth_jwt import ALGORITHM, SECRET_KEY
from backend.core import normalize_permissions, normalize_user_role
from backend.database import get_db


SB_ROLE = "SB Member"
SB_PERMISSIONS = {"view_documents", "search_documents", "download_documents"}

app = FastAPI(title="LGU Tolosa SB Member Workspace")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8551", "http://localhost:8551"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


def _active_sb_member(db: Session, username: str | None) -> models.User:
    user = db.query(models.User).filter(models.User.username == username).first()
    if (
        not user
        or normalize_user_role(getattr(user, "role", None)) != SB_ROLE
        or not getattr(user, "is_active", False)
        or getattr(user, "status", "Active") != "Active"
    ):
        raise HTTPException(status_code=403, detail="An active SB Member account is required")
    return user


def get_current_sb_member(request: Request, db: Session = Depends(get_db)) -> models.User:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = header.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid access token")
    return _active_sb_member(db, payload.get("sub"))


def require_sb_permission(user: models.User, permission: str) -> None:
    permissions = normalize_permissions(getattr(user, "permissions", None))
    if permission not in SB_PERMISSIONS or permission not in permissions:
        raise HTTPException(status_code=403, detail="This SB Member permission is not enabled")


def _safe_document(doc: models.Document, db: Session) -> dict[str, Any]:
    attachments = db.query(models.Attachment).filter(models.Attachment.document_id == doc.id).all()
    return {
        "id": doc.id,
        "document_number": doc.tracking_number,
        "title": doc.title,
        "document_type": doc.document_type,
        "description": doc.description,
        "date": doc.date_registered or (doc.created_at.isoformat() if doc.created_at else None),
        "originating_office": doc.originating_office,
        "status": doc.status,
        "archived": bool(doc.archived),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "attachments": [
            {
                "id": item.id,
                "filename": item.original_filename,
                "mime_type": item.mime_type,
                "size": item.size,
            }
            for item in attachments
        ],
    }


def _document_query(
    db: Session,
    *,
    search: str | None,
    document_type: str | None,
    year: str | None,
    status: str | None,
):
    query = db.query(models.Document).filter(models.Document.archived.is_(False))
    if search:
        like = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                models.Document.tracking_number.ilike(like),
                models.Document.title.ilike(like),
                models.Document.document_type.ilike(like),
                models.Document.description.ilike(like),
                models.Document.category.ilike(like),
                models.Document.author.ilike(like),
            )
        )
    if document_type:
        query = query.filter(models.Document.document_type == document_type)
    if status:
        query = query.filter(models.Document.status == status)
    if year and year.isdigit() and len(year) == 4:
        start = datetime(int(year), 1, 1, tzinfo=timezone.utc)
        end = datetime(int(year) + 1, 1, 1, tzinfo=timezone.utc)
        query = query.filter(models.Document.created_at >= start, models.Document.created_at < end)
    return query.order_by(models.Document.created_at.desc())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sb-member"}


@app.get("/me")
def me(current_user: models.User = Depends(get_current_sb_member)):
    return {
        "username": current_user.username,
        "full_name": current_user.full_name or current_user.username,
        "email": current_user.email,
        "role": SB_ROLE,
        "status": current_user.status,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "permissions": sorted(normalize_permissions(getattr(current_user, "permissions", None)) & SB_PERMISSIONS),
    }


@app.get("/documents")
def list_documents(
    search: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    year: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_sb_member),
):
    require_sb_permission(current_user, "view_documents")
    if search and search.strip():
        require_sb_permission(current_user, "search_documents")
    docs = _document_query(db, search=search, document_type=document_type, year=year, status=status).all()
    return {"items": [_safe_document(doc, db) for doc in docs], "total": len(docs)}


@app.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    require_sb_permission(current_user, "view_documents")
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.archived:
        raise HTTPException(status_code=403, detail="Archived documents are not available to SB Members")
    return _safe_document(doc, db)


@app.get("/documents/{document_id}/attachments/{attachment_id}")
def download_document(document_id: int, attachment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    require_sb_permission(current_user, "download_documents")
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.archived:
        raise HTTPException(status_code=403, detail="Archived documents are not available to SB Members")
    attachment = db.query(models.Attachment).filter(
        models.Attachment.id == attachment_id,
        models.Attachment.document_id == document_id,
    ).first()
    if not attachment or not attachment.stored_path or not os.path.isabs(attachment.stored_path):
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = Path(attachment.stored_path).resolve()
    upload_root = Path(__file__).resolve().parents[1] / "uploads"
    if upload_root.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(str(path), filename=attachment.original_filename, media_type=attachment.mime_type or "application/octet-stream")


@app.get("/dashboard")
def dashboard(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    require_sb_permission(current_user, "view_documents")
    total = db.query(func.count(models.Document.id)).filter(models.Document.archived.is_(False)).scalar() or 0
    recent = db.query(models.Document).filter(models.Document.archived.is_(False)).order_by(models.Document.created_at.desc()).limit(5).all()
    return {"total_documents": total, "recent_documents": [_safe_document(doc, db) for doc in recent]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("SBmem_backend.main:app", host="127.0.0.1", port=int(os.getenv("SBMEM_BACKEND_PORT", "8002")), reload=False)
