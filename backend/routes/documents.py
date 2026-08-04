from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
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
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import io
import os
import qrcode
import re
import uuid

router = APIRouter()


def _build_qr_image(url: str):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def _build_batch_qr_pdf_bytes(items: list[models.LegislativeItem]) -> bytes:
    styles = getSampleStyleSheet()
    story = []
    styles["Body"].fontName = "Helvetica"
    styles["Body"].fontSize = 8
    styles["Heading2"].fontName = "Helvetica-Bold"
    styles["Heading2"].fontSize = 9

    sticker_width = 150
    sticker_height = 170
    page_items = list(items)
    item_index = 0

    while item_index < len(page_items):
        page_slice = page_items[item_index : item_index + 9]
        rows = []
        for row in range(3):
            row_cells = []
            for col in range(3):
                idx = row * 3 + col
                item = page_slice[idx] if idx < len(page_slice) else None
                if item is None:
                    row_cells.append(Paragraph("", styles["Body"]))
                else:
                    title = (item.title or "Untitled").strip()
                    short_title = title[:30] + ("..." if len(title) > 30 else "")
                    qr_url = f"https://192.168.1.4:8002/scan?uuid={item.tracking_uuid}"
                    cell_content = [
                        Paragraph("<b>STICKER</b>", styles["Heading2"]),
                        Spacer(1, 3),
                        Paragraph(f"{item.item_type or 'Measure'}", styles["Body"]),
                        Spacer(1, 3),
                        Paragraph(f"{item.current_status or '-'}", styles["Body"]),
                        Spacer(1, 4),
                        Paragraph(f"UUID: {item.tracking_uuid[:8].upper()}", styles["Body"]),
                        Spacer(1, 4),
                        Paragraph(short_title, styles["Body"]),
                        Spacer(1, 6),
                        Paragraph("", styles["Body"]),
                    ]
                    cell_content.append(Image(_build_qr_image(qr_url), width=70, height=70))
                    row_cells.append(cell_content)
            rows.append(row_cells)

        table = Table(
            rows,
            colWidths=[sticker_width, sticker_width, sticker_width],
            rowHeights=[sticker_height, sticker_height, sticker_height],
            hAlign="LEFT",
            repeatRows=0,
        )
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.8, colors.black),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(table)
        if item_index + 9 < len(page_items):
            story.append(PageBreak())
        item_index += 9

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="Batch QR Stickers")
    doc.build(story)
    return buffer.getvalue()


def _build_agenda_pdf_bytes(items: list[models.LegislativeItem]) -> bytes:
    styles = getSampleStyleSheet()
    story = []
    title_style = styles["Title"]
    title_style.fontName = "Helvetica-Bold"
    title_style.fontSize = 18
    body_style = styles["Body"]
    body_style.fontName = "Helvetica"
    body_style.fontSize = 10

    story.append(Paragraph("ORDER OF BUSINESS - Sangguniang Bayan Tolosa", title_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Prepared on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}", body_style))
    story.append(Spacer(1, 12))

    def stage_key(status: str | None) -> str:
        value = (status or "").strip().lower()
        if "1st" in value:
            return "1st Reading"
        if "2nd" in value:
            return "2nd Reading"
        if "3rd" in value:
            return "3rd Reading"
        if "committee report" in value:
            return "Committee Report Submitted"
        return status or "Other"

    grouped: dict[str, list[models.LegislativeItem]] = {}
    for item in items:
        key = stage_key(item.current_status)
        grouped.setdefault(key, []).append(item)

    ordered_stages = [
        "1st Reading",
        "2nd Reading",
        "3rd Reading",
        "Committee Report Submitted",
    ]
    for stage in ordered_stages:
        if stage not in grouped:
            continue
        story.append(Paragraph(stage, styles["Heading2"]))
        story.append(Spacer(1, 6))
        table_data = [["No.", "Measure", "Type", "Committee"]]
        for index, item in enumerate(grouped[stage], start=1):
            table_data.append([
                str(index),
                (item.title or "Untitled")[:90],
                item.item_type or "-",
                item.assigned_committee or "-",
            ])
        table = Table(table_data, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 12))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="Order of Business")
    doc.build(story)
    return buffer.getvalue()


def _resolve_measure_number(db: Session, item_type: str, year: int | None = None) -> str:
    base_year = year or datetime.utcnow().year
    normalized_type = (item_type or "").strip()
    if "resolution" in normalized_type.lower():
        prefix = "Draft Res. No."
    elif "ordinance" in normalized_type.lower():
        prefix = "Draft Ord. No."
    else:
        prefix = "Draft Measure No."

    pattern = re.compile(rf"{base_year}-(\d{{1,3}})")
    highest_sequence = 0

    items = db.query(models.LegislativeItem).filter(models.LegislativeItem.item_type == normalized_type).all()
    for item in items:
        title = item.title or ""
        match = pattern.search(title)
        if match:
            sequence = int(match.group(1))
            highest_sequence = max(highest_sequence, sequence)

    next_sequence = highest_sequence + 1
    return f"{prefix} {base_year}-{next_sequence:03d}"


class BatchQrPayload(BaseModel):
    item_ids: list[int]


class RegisterPayload(BaseModel):
    title: str
    item_type: str
    committee: str


@router.post("/documents/batch-qr-pdf")
def batch_qr_pdf(payload: BatchQrPayload, db: Session = Depends(get_db)):
    if not payload.item_ids:
        raise HTTPException(status_code=400, detail="No item IDs were provided")

    items = db.query(models.LegislativeItem).filter(models.LegislativeItem.id.in_(payload.item_ids)).all()
    if not items:
        raise HTTPException(status_code=404, detail="No matching legislative items found")

    pdf_bytes = _build_batch_qr_pdf_bytes(items)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=batch_qr_stickers.pdf"},
    )


@router.get("/documents/next-number")
def next_measure_number(item_type: str, year: int | None = None, db: Session = Depends(get_db)):
    if not item_type:
        raise HTTPException(status_code=400, detail="item_type is required")
    return {"next_number": _resolve_measure_number(db, item_type, year)}


@router.get("/documents/generate-agenda")
def generate_agenda(db: Session = Depends(get_db)):
    eligible_statuses = {
        "1st Reading",
        "2nd Reading",
        "3rd Reading",
        "Committee Report Submitted",
    }
    items = (
        db.query(models.LegislativeItem)
        .filter(models.LegislativeItem.current_status.in_(eligible_statuses))
        .order_by(models.LegislativeItem.id.asc())
        .all()
    )
    pdf_bytes = _build_agenda_pdf_bytes(items)
    filename = f"session_agenda_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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
def register_item(payload: RegisterPayload, db: Session = Depends(get_db)):
    title = (payload.title or "").strip()
    item_type = (payload.item_type or "").strip()
    committee = (payload.committee or "").strip()

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
