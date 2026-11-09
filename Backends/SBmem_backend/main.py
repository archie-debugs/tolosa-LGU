import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

load_dotenv()

from Backends.backend import models
from Backends.backend.auth_jwt import create_download_token, decode_download_token
from Backends.backend.authentication import ensure_active_user, get_current_user
from Backends.backend.lan import refresh_development_public_urls
from Backends.backend.core import LEGACY_UPLOAD_DIR, UPLOAD_DIR, lgu_today, normalize_permissions, normalize_user_role
from Backends.backend.database import get_db
from Backends.backend.routes.temporary_documents import moa_path

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


def _documents_for(db: Session, day) -> list[dict[str, Any]]:
    """The documents employees set for a day, in their order, then that day's temporary documents
    (ordinances and MOAs): members are not told which ones are temporary. A MOA has no document id;
    it carries `temporary_id` instead."""
    entries = (
        db.query(models.TodaysDocument)
        .join(models.Document, models.Document.id == models.TodaysDocument.document_id)
        .filter(models.TodaysDocument.scheduled_for == day, models.Document.archived.is_(False))
        .order_by(models.TodaysDocument.position.asc(), models.TodaysDocument.id.asc())
        .all()
    )
    items = [{**_safe_document(entry.document, db), "note": entry.note} for entry in entries]
    listed = {item["id"] for item in items}
    temporary = db.query(models.TemporaryDocument).filter(models.TemporaryDocument.scheduled_for == day).order_by(models.TemporaryDocument.id).all()
    for entry in temporary:
        doc = entry.document
        if doc is not None:
            if not doc.archived and doc.id not in listed:
                listed.add(doc.id)
                items.append({**_safe_document(doc, db), "note": None})
        else:
            items.append({
                "id": None, "temporary_id": entry.id, "kind": "MOA", "title": entry.title, "document_type": "MOA", "note": None,
                "attachments": [{"id": entry.id, "filename": entry.original_filename, "mime_type": entry.mime_type, "size": entry.size}],
            })
    return items


@app.get("/todays-documents")
def todays_documents(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    """The documents employees set for today, so members need not search."""
    require_sb_permission(current_user, "view_documents")
    today = lgu_today()
    return {"date": today.isoformat(), "items": _documents_for(db, today)}


@app.get("/upcoming-documents")
def upcoming_documents(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    """Each day after today that has documents set for it, earliest first, with that day's documents.

    Members may view and download these before their day, but not open their details.
    """
    require_sb_permission(current_user, "view_documents")
    today = lgu_today()
    days = {day for (day,) in db.query(models.TodaysDocument.scheduled_for).filter(models.TodaysDocument.scheduled_for > today).distinct()}
    days |= {day for (day,) in db.query(models.TemporaryDocument.scheduled_for).filter(models.TemporaryDocument.scheduled_for > today).distinct()}
    result = [{"date": day.isoformat(), "items": items} for day in sorted(days) if (items := _documents_for(db, day))]
    return {"date": today.isoformat(), "days": result}


def _set_for_today(db: Session, document_id: int, upcoming: bool = False) -> models.Document:
    """A document members may open: one employees set for today, on the day's list or as temporary.

    With `upcoming`, also one set for a later day: its file only, not its details.
    """
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.archived:
        raise HTTPException(status_code=403, detail="Archived documents are not available to SB Members")
    today = lgu_today()

    def set_for(table):
        day = table.scheduled_for >= today if upcoming else table.scheduled_for == today
        return db.query(table.id).filter(table.document_id == document_id, day).first()

    if not (set_for(models.TodaysDocument) or set_for(models.TemporaryDocument)):
        raise HTTPException(status_code=403, detail="SB Members can only open the documents set for them today or for a later day")
    return doc


@app.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    require_sb_permission(current_user, "view_documents")
    return _safe_document(_set_for_today(db, document_id), db)


def _member_attachment_path(db: Session, document_id: int, attachment_id: int) -> tuple[Path, models.Attachment]:
    _set_for_today(db, document_id, upcoming=True)
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


def _attachment_response(path: Path, attachment: models.Attachment, inline: bool = False) -> FileResponse:
    # Inline lets the browser show a PDF in its own viewer instead of saving it.
    return FileResponse(str(path), filename=os.path.basename(attachment.original_filename or "") or "document", media_type=attachment.mime_type or "application/octet-stream",
                        content_disposition_type="inline" if inline else "attachment")


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
def create_download_link(document_id: int, attachment_id: int, inline: bool = Query(False), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    """A link to the file; with `inline` it opens in the browser (View PDF) and needs only view_documents."""
    require_sb_permission(current_user, "view_documents" if inline else "download_documents")
    _member_attachment_path(db, document_id, attachment_id)
    token = create_download_token({"sub": current_user.username, "document_id": document_id, "attachment_id": attachment_id, "inline": inline})
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
    inline = bool(payload.get("inline"))
    require_sb_permission(user, "view_documents" if inline else "download_documents")
    return _attachment_response(*_member_attachment_path(db, document_id, attachment_id), inline=inline)


def _member_moa(db: Session, entry_id: int) -> tuple[Path, models.TemporaryDocument]:
    """A temporary MOA members may open: on its day, or before it; never after (it is archived then)."""
    entry = db.query(models.TemporaryDocument).filter(models.TemporaryDocument.id == entry_id).first()
    if entry is None or entry.document_id is not None or entry.scheduled_for < lgu_today():
        raise HTTPException(status_code=404, detail="File not found")
    return moa_path(entry), entry


@app.post("/temporary-documents/{entry_id}/download-token")
def create_moa_download_link(entry_id: int, inline: bool = Query(False), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_sb_member)):
    require_sb_permission(current_user, "view_documents" if inline else "download_documents")
    _member_moa(db, entry_id)
    token = create_download_token({"sub": current_user.username, "temporary_document_id": entry_id, "inline": inline})
    return {"download_url": f"{_public_url()}/temporary-documents/{entry_id}/download?download_token={quote(token, safe='')}"}


@app.get("/temporary-documents/{entry_id}/download")
def download_moa_by_link(entry_id: int, download_token: str = Query(...), db: Session = Depends(get_db)):
    payload = decode_download_token(download_token)
    if payload.get("temporary_document_id") != entry_id:
        raise HTTPException(status_code=403, detail="Link does not match this file")
    user = db.query(models.User).filter(models.User.username == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="Link user not found")
    ensure_active_user(user)
    get_current_sb_member(user)
    inline = bool(payload.get("inline"))
    require_sb_permission(user, "view_documents" if inline else "download_documents")
    path, entry = _member_moa(db, entry_id)
    return FileResponse(str(path), filename=entry.original_filename or "moa", media_type=entry.mime_type or "application/octet-stream",
                        content_disposition_type="inline" if inline else "attachment")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Backends.SBmem_backend.main:app", host="127.0.0.1", port=int(os.getenv("SBMEM_BACKEND_PORT", "8002")), reload=False)

