import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..core import TEMP_UPLOAD_DIR, UPLOAD_DIR, require_permission, require_user_management_permission
from ..database import get_db
from ..routes.analytics import _storage_information

router = APIRouter()


class TempCleanupRequest(BaseModel):
    confirm: bool = False
    max_age_hours: int = 24


def _iter_files(directory: str, excluded_dirs: set[str] | None = None) -> list[str]:
    excluded = {name.lower() for name in (excluded_dirs or set())}
    if not os.path.isdir(directory):
        return []
    files: list[str] = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [name for name in dirs if name.lower() not in excluded]
        for filename in filenames:
            path = os.path.join(root, filename)
            if os.path.isfile(path):
                files.append(os.path.abspath(path))
    return sorted(files)


@router.get("/storage/diagnostics")
def get_storage_diagnostics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("modify_system_settings")),
):
    require_permission(current_admin, "modify_system_settings")

    attachment_rows = db.query(models.Attachment).all()
    valid_paths = set()
    missing_files = []
    for attachment in attachment_rows:
        if not attachment.stored_path:
            continue
        normalized = os.path.abspath(str(attachment.stored_path))
        valid_paths.add(normalized)
        if not os.path.exists(normalized):
            document = db.query(models.Document).filter(models.Document.id == attachment.document_id).first()
            missing_files.append({
                "attachment_id": attachment.id,
                "document_id": attachment.document_id,
                "tracking_number": document.tracking_number if document else None,
                "original_filename": attachment.original_filename,
                "stored_path": normalized,
            })

    orphan_files = []
    for path in _iter_files(UPLOAD_DIR, {"tmp", "qr"}):
        if path in valid_paths:
            continue
        try:
            stat_result = os.stat(path)
            orphan_files.append({
                "path": path,
                "size": stat_result.st_size,
                "modified_at": datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat(),
            })
        except OSError:
            orphan_files.append({"path": path, "size": None, "modified_at": None})

    temp_files = []
    for path in _iter_files(TEMP_UPLOAD_DIR):
        try:
            stat_result = os.stat(path)
            temp_files.append({
                "path": path,
                "size": stat_result.st_size,
                "modified_at": datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat(),
            })
        except OSError:
            temp_files.append({"path": path, "size": None, "modified_at": None})

    return {
        "status": "ok",
        "storage": _storage_information(),
        "missing_files": missing_files,
        "orphan_files": orphan_files,
        "temporary_files": temp_files,
        "summary": {
            "attachment_count": len(attachment_rows),
            "missing_files_count": len(missing_files),
            "orphan_files_count": len(orphan_files),
            "temporary_files_count": len(temp_files),
        },
    }


@router.post("/storage/cleanup-temp")
def cleanup_temp_uploads(
    payload: TempCleanupRequest,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("modify_system_settings")),
):
    require_permission(current_admin, "modify_system_settings")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation is required to delete temporary files")

    max_age_hours = max(0, int(payload.max_age_hours or 24))
    removed = []
    now = datetime.now(timezone.utc)

    for path in _iter_files(TEMP_UPLOAD_DIR):
        try:
            timestamp = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
            age_hours = (now - timestamp).total_seconds() / 3600.0
            if age_hours < max_age_hours:
                continue
            os.remove(path)
            removed.append(path)
        except OSError:
            continue

    return {
        "message": "Temporary upload cleanup complete",
        "confirmed": True,
        "max_age_hours": max_age_hours,
        "removed_files": removed,
        "removed_count": len(removed),
    }
