"""Temporary documents: ordinances and uploaded MOAs that employees set for SB Members for one day.

Members see them with that day's documents (Backends/SBmem_backend). After the day an entry is
archived; the ordinance itself stays an active document. An archived entry is due for deletion
TEMPORARY_KEEP_DAYS after it was archived, or on kept_until; nothing is deleted on its own: an
employee deletes it or keeps it longer (notifications flag the due ones).
"""

import json
import mimetypes
import os
import secrets
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..auth_jwt import create_download_token, decode_download_token
from ..authentication import ensure_active_user, get_current_user
from ..core import TEMP_UPLOAD_DIR, UPLOAD_DIR, lgu_today, record_audit_log, require_permission
from ..database import get_db
from ..tracking_numbers import standard_document_type
from .documents import (
    ALLOWED_EXTENSIONS, MAX_FILE_SIZE, _images_to_pdf, _is_image, _pdf_name, _public_base_url, _remove_staged, _staged_name,
    _staged_pages,
)

router = APIRouter(prefix="/temporary-documents", tags=["temporary-documents"])

TEMPORARY_KEEP_DAYS = 30
TEMPORARY_DIR = os.path.join(UPLOAD_DIR, "temporary")
PERMISSION = "set_documents_for_sb_members"


class OrdinanceEntry(BaseModel):
    scheduled_for: date
    document_id: int = Field(..., gt=0)


class MoaEntry(BaseModel):
    scheduled_for: date
    tmp_name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=300)
    # More photos or scans of the same MOA's pages, after tmp_name's: joined with it into one PDF.
    page_tmp_names: list[str] = Field(default_factory=list, max_length=100)


def due_on(entry: models.TemporaryDocument) -> date:
    """The day an archived entry is due for deletion: 30 days after its day ended, or later when kept."""
    due = entry.scheduled_for + timedelta(days=1 + TEMPORARY_KEEP_DAYS)
    return max(due, entry.kept_until) if entry.kept_until else due


def entry_label(entry: models.TemporaryDocument) -> str:
    return entry.document.tracking_number if entry.document_id else f"MOA \"{entry.title}\""


def serialize(entry: models.TemporaryDocument, today: date) -> dict:
    doc = entry.document
    item = {
        "id": entry.id,
        "scheduled_for": entry.scheduled_for.isoformat(),
        "kind": "Ordinance" if entry.document_id else "MOA",
        "added_by": (entry.added_by.full_name or entry.added_by.username) if entry.added_by else None,
        "archived": entry.scheduled_for < today,
    }
    if doc is not None:
        item.update(title=doc.title, document={
            "id": doc.id, "tracking_number": doc.tracking_number, "document_number": doc.document_number,
            "series_year": doc.series_year, "title": doc.title, "document_type": doc.document_type, "archived": bool(doc.archived),
        })
    else:
        item.update(title=entry.title, filename=entry.original_filename, size=entry.size)
    if item["archived"]:
        item.update(due_on=due_on(entry).isoformat(), days_left=(due_on(entry) - today).days)
    return item


def moa_path(entry: models.TemporaryDocument) -> Path:
    """The MOA's file, only from the temporary folder."""
    path = Path(entry.stored_path or "").resolve()
    if entry.document_id or Path(TEMPORARY_DIR).resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return path


def _entry(db: Session, entry_id: int) -> models.TemporaryDocument:
    entry = db.query(models.TemporaryDocument).filter(models.TemporaryDocument.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Temporary document not found")
    return entry


def _check_day(day: date):
    if day < lgu_today():
        raise HTTPException(status_code=400, detail="Temporary documents can only be set for today or a later date")


def _audit(db, user, action, entry, details):
    record_audit_log(db, actor=user.username, action=action, target_type="TemporaryDocument", target_id=str(entry.id), details=details, commit=False)


@router.get("")
def list_day(scheduled_for: date | None = Query(default=None, alias="date"), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, PERMISSION)
    today = lgu_today()
    day = scheduled_for or today
    entries = db.query(models.TemporaryDocument).filter(models.TemporaryDocument.scheduled_for == day).order_by(models.TemporaryDocument.id).all()
    return {"date": day.isoformat(), "today": today.isoformat(), "items": [serialize(entry, today) for entry in entries]}


@router.get("/archive")
def list_archive(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, PERMISSION)
    today = lgu_today()
    entries = db.query(models.TemporaryDocument).filter(models.TemporaryDocument.scheduled_for < today).all()
    entries.sort(key=lambda entry: (due_on(entry), entry.id))
    return {"today": today.isoformat(), "items": [serialize(entry, today) for entry in entries]}


@router.post("/ordinance")
def add_ordinance(payload: OrdinanceEntry, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, PERMISSION)
    _check_day(payload.scheduled_for)
    doc = db.query(models.Document).filter(models.Document.id == payload.document_id).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if standard_document_type(doc.document_type) != "Ordinance":
        raise HTTPException(status_code=400, detail="Only ordinances can be added as temporary documents")
    if doc.archived:
        raise HTTPException(status_code=400, detail="Archived documents cannot be set for SB Members")
    if db.query(models.TemporaryDocument.id).filter_by(scheduled_for=payload.scheduled_for, document_id=doc.id).first():
        raise HTTPException(status_code=409, detail="This ordinance is already set for that date")
    entry = models.TemporaryDocument(scheduled_for=payload.scheduled_for, document_id=doc.id, added_by_id=current_user.id)
    db.add(entry)
    db.flush()
    _audit(db, current_user, "TEMPORARY_DOCUMENT_ADDED", entry, f"{doc.tracking_number} set as a temporary document for {payload.scheduled_for.isoformat()}")
    db.commit()
    db.refresh(entry)
    return serialize(entry, lgu_today())


@router.post("/moa")
def add_moa(payload: MoaEntry, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, PERMISSION)
    _check_day(payload.scheduled_for)
    safe_name = os.path.basename(payload.tmp_name)
    tmp_path = os.path.join(TEMP_UPLOAD_DIR, safe_name)
    meta_path = f"{tmp_path}.meta.json"
    try:
        with open(meta_path, "r", encoding="utf-8") as handle:
            meta = json.load(handle)
    except Exception:
        meta = {}
    # Only the person who uploaded the file may use it.
    if not safe_name or not os.path.isfile(tmp_path) or meta.get("username") != current_user.username:
        raise HTTPException(status_code=404, detail="Uploaded file not found. Upload it again.")
    original_filename = os.path.basename(meta.get("original_filename") or safe_name)
    try:
        page_paths = _staged_pages(current_user, payload.page_tmp_names)
    except Exception:
        raise HTTPException(status_code=404, detail="Uploaded file not found. Upload it again.")
    size = os.path.getsize(tmp_path)
    if size == 0 or size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="The file is empty or larger than 25 MB")
    os.makedirs(TEMPORARY_DIR, exist_ok=True)
    if page_paths or _is_image(original_filename):
        # Photos or scans are stored as one PDF, as when registering a document.
        if not all(_is_image(name) for name in [original_filename, *(_staged_name(path) for path in page_paths)]):
            raise HTTPException(status_code=400, detail="Only photos or scans (JPG, PNG) of one MOA's pages can be joined into one PDF.")
        contents = []
        for path in [tmp_path, *page_paths]:
            with open(path, "rb") as handle:
                contents.append(handle.read())
        try:
            content = _images_to_pdf(contents)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        original_filename, size = _pdf_name(original_filename), len(content)
        stored_path = os.path.join(TEMPORARY_DIR, f"{secrets.token_hex(12)}.pdf")
        with open(stored_path, "wb") as handle:
            handle.write(content)
        _remove_staged([tmp_path, *page_paths, *(f"{path}.meta.json" for path in page_paths)])
    else:
        extension = os.path.splitext(original_filename.lower())[1]
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Use a PDF, Word file, or JPG or PNG photo")
        stored_path = os.path.join(TEMPORARY_DIR, f"{secrets.token_hex(12)}{extension}")
        os.replace(tmp_path, stored_path)
    try:
        os.remove(meta_path)
    except OSError:
        pass
    entry = models.TemporaryDocument(
        scheduled_for=payload.scheduled_for, title=payload.title.strip(), original_filename=original_filename,
        stored_path=stored_path, mime_type=mimetypes.guess_type(original_filename)[0], size=size, added_by_id=current_user.id,
    )
    db.add(entry)
    db.flush()
    _audit(db, current_user, "TEMPORARY_DOCUMENT_ADDED", entry, f"MOA \"{entry.title}\" uploaded for {payload.scheduled_for.isoformat()}")
    db.commit()
    db.refresh(entry)
    return serialize(entry, lgu_today())


@router.post("/{entry_id}/keep")
def keep_longer(entry_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, PERMISSION)
    entry = _entry(db, entry_id)
    today = lgu_today()
    if entry.scheduled_for >= today:
        raise HTTPException(status_code=400, detail="Only archived temporary documents can be kept longer")
    entry.kept_until = max(due_on(entry), today) + timedelta(days=TEMPORARY_KEEP_DAYS)
    _audit(db, current_user, "TEMPORARY_DOCUMENT_KEPT", entry, f"{entry_label(entry)} kept until {entry.kept_until.isoformat()}")
    db.commit()
    db.refresh(entry)
    return serialize(entry, today)


@router.delete("/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Takes an entry off today's or a later day's list, or deletes an archived one now."""
    require_permission(current_user, PERMISSION)
    entry = _entry(db, entry_id)
    stored_path = None if entry.document_id else entry.stored_path
    _audit(db, current_user, "TEMPORARY_DOCUMENT_DELETED", entry, f"{entry_label(entry)} for {entry.scheduled_for.isoformat()} deleted")
    db.delete(entry)
    db.commit()
    if stored_path:
        try:
            os.remove(stored_path)
        except OSError:
            pass
    return {"message": "Deleted", "id": entry_id}


@router.post("/{entry_id}/download-token")
def create_download_link(entry_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_permission(current_user, PERMISSION)
    moa_path(_entry(db, entry_id))
    token = create_download_token({"sub": current_user.username, "temporary_document_id": entry_id})
    return {"download_url": f"{_public_base_url()}/temporary-documents/{entry_id}/file?download_token={quote(token, safe='')}"}


@router.get("/{entry_id}/file")
def download_by_link(entry_id: int, download_token: str = Query(...), db: Session = Depends(get_db)):
    payload = decode_download_token(download_token)
    if payload.get("temporary_document_id") != entry_id:
        raise HTTPException(status_code=403, detail="Link does not match this file")
    user = db.query(models.User).filter(models.User.username == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="Link user not found")
    ensure_active_user(user)
    require_permission(user, PERMISSION)
    entry = _entry(db, entry_id)
    return FileResponse(str(moa_path(entry)), filename=entry.original_filename or "moa", media_type=entry.mime_type or "application/octet-stream")
