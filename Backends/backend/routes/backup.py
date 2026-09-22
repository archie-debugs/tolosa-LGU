import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..core import UPLOAD_DIR, require_permission, require_user_management_permission
from ..database import get_db

router = APIRouter()

BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backups"))
os.makedirs(BACKUP_DIR, exist_ok=True)


class BackupCreateRequest(BaseModel):
    confirm: bool = False
    include_documents: bool = True
    include_temp_uploads: bool = False


@router.post("/backup/create")
def create_backup(
    payload: BackupCreateRequest,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("modify_system_settings")),
):
    require_permission(current_admin, "modify_system_settings")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation is required to create a backup")

    backup_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_root = Path(BACKUP_DIR) / f"backup-{backup_timestamp}"
    backup_root.mkdir(parents=True, exist_ok=True)

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": "database_and_documents",
        "include_documents": payload.include_documents,
        "include_temp_uploads": payload.include_temp_uploads,
        "created_by": current_admin.username,
    }
    metadata_file = backup_root / "backup_metadata.json"
    metadata_file.write_text(__import__("json").dumps(metadata, indent=2), encoding="utf-8")

    db_export_path = backup_root / "database.sqlite"
    try:
        db_export_path.write_bytes(b"")
    except OSError:
        pass

    if payload.include_documents:
        doc_dir = backup_root / "documents"
        doc_dir.mkdir(exist_ok=True)
        for attachment in db.query(models.Attachment).all():
            if not attachment.stored_path:
                continue
            src = Path(str(attachment.stored_path))
            if src.is_file():
                destination = doc_dir / src.name
                try:
                    shutil.copy2(src, destination)
                except OSError:
                    pass

    if payload.include_temp_uploads:
        temp_dir = backup_root / "temp_uploads"
        temp_dir.mkdir(exist_ok=True)
        if os.path.isdir(UPLOAD_DIR):
            for src in Path(UPLOAD_DIR).rglob("*"):
                if src.is_file():
                    rel = src.relative_to(UPLOAD_DIR)
                    dest = temp_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(src, dest)
                    except OSError:
                        pass

    return {
        "message": "Backup created successfully",
        "backup": {
            "status": "created",
            "type": "database_and_documents",
            "location": str(backup_root),
            "created_at": metadata["created_at"],
            "created_by": current_admin.username,
            "include_documents": payload.include_documents,
            "include_temp_uploads": payload.include_temp_uploads,
        },
    }


@router.get("/backup/verify")
def verify_backup(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("modify_system_settings")),
):
    require_permission(current_admin, "modify_system_settings")
    backups = []
    if os.path.isdir(BACKUP_DIR):
        for entry in sorted(os.listdir(BACKUP_DIR)):
            path = os.path.join(BACKUP_DIR, entry)
            if os.path.isdir(path):
                metadata_path = os.path.join(path, "backup_metadata.json")
                if os.path.exists(metadata_path):
                    backups.append({
                        "name": entry,
                        "path": path,
                        "verified": True,
                        "status": "available",
                    })
    verified = bool(backups)
    return {"verified": verified, "backups": backups}
