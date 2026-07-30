from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..core import (
    extract_text_from_file,
    parse_document_content,
    record_audit_log,
    load_workflow_steps,
    DEFAULT_WORKFLOW_STEPS,
)
import uuid

router = APIRouter()

@router.post("/legislative/parse")
async def parse_document(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        text = extract_text_from_file(file_bytes, file.filename)
        parsed_data = parse_document_content(text)
        return parsed_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing document: {str(e)}")


@router.post("/legislative/register")
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
        current_location="Records Registry",
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
        "current_location": new_item.current_location,
    }


@router.get("/legislative/list")
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
                "current_location": item.current_location or "Records Registry",
                "uuid": item.tracking_uuid,
            }
            for item in items
        ]
    }
