from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from ..database import get_db
from .. import models
from ..core import (
    UPLOAD_DIR,
    BACKEND_PUBLIC_URL,
    SCANNER_PUBLIC_URL,
    extract_text_from_file,
    record_audit_log,
    load_workflow_steps,
    DEFAULT_WORKFLOW_STEPS,
    validate_scanner_session,
)
from urllib.parse import quote as urlquote
import io
import os
import qrcode

router = APIRouter()


def _update_document_location(*, item: models.LegislativeItem, receiving_office: str, logged_in_user: str, db: Session):
    previous_location = item.current_location or "Records Registry"
    new_location = receiving_office.strip() or previous_location

    item.current_location = new_location

    history_entry = models.DocumentHistory(
        item_id=item.id,
        previous_location=previous_location,
        receiving_office=receiving_office.strip() or new_location,
        new_location=new_location,
        logged_in_user=logged_in_user.strip() or "system",
    )
    db.add(history_entry)
    db.commit()
    db.refresh(item)
    db.refresh(history_entry)

    record_audit_log(
        db,
        actor=logged_in_user.strip() or "system",
        action="DOCUMENT_RECEIVED",
        target_type="LegislativeItem",
        target_id=str(item.id),
        details=f"{previous_location} -> {new_location}",
    )

    return previous_location, new_location, history_entry


@router.post("/documents/receive/{tracking_uuid}")
def receive_document(
    tracking_uuid: str,
    receiving_office: str,
    logged_in_user: str = "system",
    scanner_token: str | None = None,
    db: Session = Depends(get_db),
):
    item = db.query(models.LegislativeItem).filter(models.LegislativeItem.tracking_uuid == tracking_uuid).first()
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")

    if scanner_token:
        session = validate_scanner_session(scanner_token)
        logged_in_user = str(session.get("username", logged_in_user))

    previous_location, new_location, history_entry = _update_document_location(
        item=item,
        receiving_office=receiving_office,
        logged_in_user=logged_in_user,
        db=db,
    )

    return {
        "message": f"Received by {new_location}",
        "document_title": item.title,
        "previous_location": previous_location,
        "new_location": new_location,
        "current_location": item.current_location,
        "timestamp": history_entry.timestamp.isoformat() if history_entry.timestamp else None,
    }


@router.get("/scanner/mobile")
def mobile_scanner_page(api_base: str | None = None, uuid: str | None = None):
    target_url = f"{SCANNER_PUBLIC_URL}/scanner/mobile"
    if api_base:
        target_url = f"{target_url}?api_base={urlquote(api_base)}"
    if uuid:
        separator = "&" if "?" in target_url else "?"
        target_url = f"{target_url}{separator}uuid={urlquote(uuid)}"
    return RedirectResponse(url=target_url, status_code=307)


@router.get("/documents/history/{tracking_uuid}")
def get_document_history(tracking_uuid: str, db: Session = Depends(get_db)):
    item = db.query(models.LegislativeItem).filter(models.LegislativeItem.tracking_uuid == tracking_uuid).first()
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")

    history_items = (
        db.query(models.DocumentHistory)
        .filter(models.DocumentHistory.item_id == item.id)
        .order_by(models.DocumentHistory.timestamp.asc(), models.DocumentHistory.id.asc())
        .all()
    )

    return {
        "document": {
            "id": item.id,
            "title": item.title,
            "uuid": item.tracking_uuid,
            "current_location": item.current_location or "Records Registry",
        },
        "items": [
            {
                "id": history.id,
                "previous_location": history.previous_location,
                "receiving_office": history.receiving_office,
                "new_location": history.new_location,
                "logged_in_user": history.logged_in_user,
                "timestamp": history.timestamp.isoformat() if history.timestamp else None,
            }
            for history in history_items
        ],
    }


@router.delete("/legislative/delete/{tracking_uuid}")
def delete_legislative_item(tracking_uuid: str, actor: str = "system", location: str = "Admin Dashboard", db: Session = Depends(get_db)):
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


@router.get("/uploads/{filename:path}")
def get_uploaded_file(filename: str):
    joined_path = os.path.join(UPLOAD_DIR, filename)
    full_path = os.path.realpath(joined_path)
    if not os.path.exists(full_path) or os.path.commonpath([full_path, UPLOAD_DIR]) != UPLOAD_DIR:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path, media_type="application/octet-stream", filename=os.path.basename(full_path))


@router.get("/legislative/preview/{filename}")
def preview_uploaded_file(filename: str):
    joined_path = os.path.join(UPLOAD_DIR, filename)
    full_path = os.path.realpath(joined_path)
    if not os.path.exists(full_path) or os.path.commonpath([full_path, UPLOAD_DIR]) != UPLOAD_DIR:
        raise HTTPException(status_code=404, detail="File not found")

    if filename.lower().endswith('.pdf'):
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

    raise HTTPException(status_code=400, detail="Unsupported file type for preview")


@router.get("/legislative/qrcode/{tracking_uuid}")
def get_qrcode(tracking_uuid: str):
    try:
        scanner_url = f"{SCANNER_PUBLIC_URL}/scanner/mobile?uuid={urlquote(tracking_uuid)}&api_base={urlquote(BACKEND_PUBLIC_URL)}"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(scanner_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"QR generation failed: {exc}")


@router.post("/legislative/track/{tracking_uuid}")
def track_item(tracking_uuid: str, location: str, action: str, scanned_by: str, db: Session = Depends(get_db)):
    item = db.query(models.LegislativeItem).filter(models.LegislativeItem.tracking_uuid == tracking_uuid).first()
    if not item:
        raise HTTPException(status_code=404, detail="Legislative record not found")

    item.current_status = action

    previous_location, new_location, history_entry = _update_document_location(
        item=item,
        receiving_office=location,
        logged_in_user=scanned_by,
        db=db,
    )

    log_entry = models.LegislativeTrackingLog(
        item_id=item.id,
        location_stamp=location,
        action_taken=action,
        scanned_by=scanned_by,
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
        "current_stage": item.current_status,
        "previous_location": previous_location,
        "current_location": new_location,
        "history_timestamp": history_entry.timestamp.isoformat() if history_entry.timestamp else None,
    }


@router.post("/legislative/advance/{tracking_uuid}")
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
    current_index = workflow_steps.index(current_stage) if current_stage in workflow_steps else -1
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


@router.get("/audit/logs")
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
