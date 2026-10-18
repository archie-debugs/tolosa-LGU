import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

load_dotenv()

from Backends.backend import models
from Backends.backend.auth_jwt import create_download_token, decode_download_token
from Backends.backend.authentication import ensure_active_user, get_current_user
from Backends.backend.lan import refresh_development_public_urls
from Backends.backend.core import LEGACY_UPLOAD_DIR, UPLOAD_DIR, lgu_today, normalize_permissions, normalize_user_role
from Backends.backend.database import get_db

refresh_development_public_urls()

SB_ROLE = "SB Member"
SB_PERMISSIONS = {
    "view_documents",
    "search_documents",
    "filter_documents",
    "view_document_details",
    "download_documents",
    "print_documents",
}

app = FastAPI(title="LGU Tolosa SB Member Workspace")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8551", "http://localhost:8551"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


def get_current_sb_member(user: models.User = Depends(get_current_user)) -> models.User:
    if normalize_user_role(getattr(user, "role", None)) != SB_ROLE:
        raise HTTPException(status_code=403, detail="An active SB Member account is required")
    return user


def require_sb_permission(user: models.User, permission: str) -> None:
    permissions = normalize_permissions(getattr(user, "permissions", None))
    if permission not in SB_PERMISSIONS or permission not in permissions:
        raise HTTPException(status_code=403, detail="This SB Member permission is not enabled")


def _safe_document(doc: models.Document, db: Session) -> dict[str, Any]:
    attachments = db.query(models.Attachment).filter(models.Attachment.document_id == doc.id).all()
    return {
        "id": doc.id,
        "tracking_number": doc.tracking_number,
        "document_number": doc.document_number,
        "series_year": doc.series_year,
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
                models.Document.document_number.ilike(like),
                cast(models.Document.series_year, String).ilike(like),
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
        query = query.filter(
            or_(
                models.Document.series_year == int(year),
                models.Document.series_year.is_(None)
                & (models.Document.created_at >= start)
                & (models.Document.created_at < end),
            )
        )
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


@app.get("/todays-documents")
def todays_documents(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    """The documents employees set for today, in their order, so members need not search."""
    require_sb_permission(current_user, "view_documents")
    today = lgu_today()
    entries = (
        db.query(models.TodaysDocument)
        .join(models.Document, models.Document.id == models.TodaysDocument.document_id)
        .filter(models.TodaysDocument.scheduled_for == today, models.Document.archived.is_(False))
        .order_by(models.TodaysDocument.position.asc(), models.TodaysDocument.id.asc())
        .all()
    )
    return {
        "date": today.isoformat(),
        "items": [{**_safe_document(entry.document, db), "note": entry.note} for entry in entries],
    }


@app.get("/documents")
def list_documents(
    search: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    year: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_sb_member),
):
    require_sb_permission(current_user, "view_documents")
    if search and search.strip():
        require_sb_permission(current_user, "search_documents")
    query = _document_query(db, search=search, document_type=document_type, year=year, status=status)
    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    docs = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_safe_document(doc, db) for doc in docs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@app.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    require_sb_permission(current_user, "view_documents")
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.archived:
        raise HTTPException(status_code=403, detail="Archived documents are not available to SB Members")
    return _safe_document(doc, db)


def _member_attachment_path(db: Session, document_id: int, attachment_id: int) -> tuple[Path, models.Attachment]:
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
    allowed_roots = {Path(UPLOAD_DIR).resolve(), Path(LEGACY_UPLOAD_DIR).resolve()}
    if not any(root in path.parents for root in allowed_roots) or not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return path, attachment


def _attachment_response(path: Path, attachment: models.Attachment) -> FileResponse:
    return FileResponse(str(path), filename=os.path.basename(attachment.original_filename or "") or "document", media_type=attachment.mime_type or "application/octet-stream")


@app.get("/documents/{document_id}/attachments/{attachment_id}")
def download_document(document_id: int, attachment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    require_sb_permission(current_user, "download_documents")
    return _attachment_response(*_member_attachment_path(db, document_id, attachment_id))


def _public_url() -> str:
    """This service's address as the member's browser reaches it."""
    port = os.getenv("SBMEM_BACKEND_PORT", "8002")
    return (os.getenv("SBMEM_PUBLIC_URL") or f"http://127.0.0.1:{port}").strip().rstrip("/")


# The member app runs in the member's browser, so a download has to be a link that browser
# opens; saving the file from the app would put it on the machine running the app.
@app.post("/documents/{document_id}/attachments/{attachment_id}/download-token")
def create_download_link(document_id: int, attachment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    require_sb_permission(current_user, "download_documents")
    _member_attachment_path(db, document_id, attachment_id)
    token = create_download_token({"sub": current_user.username, "document_id": document_id, "attachment_id": attachment_id})
    return {"download_url": f"{_public_url()}/documents/{document_id}/attachments/{attachment_id}/download?download_token={quote(token, safe='')}"}


@app.get("/documents/{document_id}/attachments/{attachment_id}/download")
def download_by_link(document_id: int, attachment_id: int, download_token: str = Query(...), db: Session = Depends(get_db)):
    payload = decode_download_token(download_token)
    if payload.get("document_id") != document_id or payload.get("attachment_id") != attachment_id:
        raise HTTPException(status_code=403, detail="Link does not match attachment")
    user = db.query(models.User).filter(models.User.username == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="Link user not found")
    ensure_active_user(user)
    get_current_sb_member(user)
    require_sb_permission(user, "download_documents")
    return _attachment_response(*_member_attachment_path(db, document_id, attachment_id))


@app.get("/dashboard")
def dashboard(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    require_sb_permission(current_user, "view_documents")
    total = db.query(func.count(models.Document.id)).filter(models.Document.archived.is_(False)).scalar() or 0
    recent = db.query(models.Document).filter(models.Document.archived.is_(False)).order_by(models.Document.created_at.desc()).limit(5).all()
    return {"total_documents": total, "recent_documents": [_safe_document(doc, db) for doc in recent]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Backends.SBmem_backend.main:app", host="127.0.0.1", port=int(os.getenv("SBMEM_BACKEND_PORT", "8002")), reload=False)

