"""Printable list of Ordinances, Resolutions and Letter Requests: Title, date approved, proponents.

One table per type, grouped by month, for a year or one month of it. Served as a print-ready page
through a short-lived link, so the viewer's browser can open it and print or save it as PDF.

Date approved: an ordinance's Approved stage, a resolution's Adopted stage (its latest such entry,
only while the measure is still enacted); a letter request's date received (date_registered).
A measure not yet enacted is listed as Pending under its registration year, and only when no
month is picked.
"""

import html
import secrets
from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models, stages
from ..auth_jwt import create_download_token, decode_download_token
from ..authentication import ensure_active_user, get_current_user
from ..core import lgu_today, require_permission
from ..database import get_db
from ..tracking_numbers import DOCUMENT_TYPES, TYPE_PLURALS, standard_document_type
from .documents import _public_base_url

router = APIRouter(prefix="/print-list", tags=["print-list"])

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
DATE_LABEL = {"Ordinance": "Date Approved", "Resolution": "Date Adopted", "Letter Request": "Date Received"}


class PrintListRequest(BaseModel):
    year: int = Field(..., ge=1900, le=2999)
    month: int | None = Field(default=None, ge=1, le=12)
    types: list[str] = Field(default_factory=lambda: list(DOCUMENT_TYPES))


def _parse_day(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def list_rows(db: Session, year: int, month: int | None, types: list[str]) -> dict[str, list[dict]]:
    """Each chosen type's rows for the year (and month), sorted by date, pending ones last."""
    rows = {document_type: [] for document_type in DOCUMENT_TYPES if document_type in types}
    enacted_on = {}  # (document_id, stage) -> latest effective_on
    for document_id, stage, effective_on in (
        db.query(models.DocumentStageChange.document_id, models.DocumentStageChange.stage, models.DocumentStageChange.effective_on)
        .filter(models.DocumentStageChange.stage.in_(list(stages.ENACTED.values())))
        .order_by(models.DocumentStageChange.effective_on, models.DocumentStageChange.id)
    ):
        enacted_on[(document_id, stage)] = effective_on
    for doc in db.query(models.Document).all():
        document_type = standard_document_type(doc.document_type)
        if document_type not in rows:
            continue
        kind = stages.measure_kind(document_type)
        if kind:
            day = enacted_on.get((doc.id, stages.ENACTED[kind])) if stages.is_enacted(kind, doc.stage) else None
        else:
            day = _parse_day(doc.date_registered)
        listed_year = day.year if day else (_parse_day(doc.date_registered) or _parse_day(doc.created_at) or date.min).year
        if listed_year != year or (month and (not day or day.month != month)):
            continue
        rows[document_type].append({
            "number": doc.document_number,
            "series_year": doc.series_year or year,
            "title": doc.title,
            "date": day,
            "authors": [name.strip() for name in (doc.author or "").replace("\n", ";").split(";") if name.strip()],
        })
    for items in rows.values():
        items.sort(key=lambda row: (row["date"] or date.max, row["number"] or ""))
    return rows


STYLE = """
* { box-sizing: border-box; }
body { margin:0; background:#e9ecef; color:#111; font:13px/1.4 "Segoe UI", Arial, sans-serif; }
.bar { position:sticky; top:0; background:#fff; border-bottom:1px solid #ccd; padding:10px 16px; text-align:center; }
.bar button { background:#1f4e8c; color:#fff; border:0; border-radius:6px; padding:8px 20px; font-weight:600; cursor:pointer; }
.sheet { background:#fff; width:210mm; min-height:297mm; margin:20px auto; padding:18mm 16mm; box-shadow:0 2px 10px rgba(0,0,0,.15); }
.letterhead { text-align:center; line-height:1.25; margin-bottom:14px; }
.letterhead .small { font-size:12px; }
.letterhead .office { font-weight:700; font-size:14px; letter-spacing:.5px; margin-top:4px; }
.letterhead h1 { font-size:16px; margin:12px 0 2px; text-transform:uppercase; }
.letterhead .sub { color:#555; font-size:12px; }
table { width:100%; border-collapse:collapse; }
th, td { border:1px solid #bbb; padding:5px 7px; vertical-align:top; text-align:left; }
th { background:#f2f4f7; font-size:11.5px; text-transform:uppercase; letter-spacing:.3px; }
td.num, th.num { width:34px; text-align:center; }
td.date { white-space:nowrap; width:110px; }
tr.month td { background:#e4e8ee; font-weight:700; font-size:12px; }
.muted { color:#555; font-style:italic; }
.empty { text-align:center; color:#555; margin-top:40px; }
h2 { font-size:14px; margin:18px 0 6px; padding-bottom:3px; border-bottom:2px solid #111; text-transform:uppercase; }
h2 span { font-weight:400; color:#555; text-transform:none; }
.signatures { display:flex; justify-content:space-between; gap:40px; margin-top:42px; break-inside:avoid; }
.signatures div { flex:1; }
.signatures .line { border-top:1px solid #111; margin-top:36px; padding-top:3px; }
.signatures .role { text-align:center; font-size:12px; color:#555; }
.footer { margin-top:18px; font-size:11px; color:#555; display:flex; justify-content:space-between; }
@media (max-width: 900px) { .sheet { width:auto; margin:12px; padding:16px; min-height:0; } }
@page { size: A4 portrait; margin: 14mm; }
@media print {
  body { background:#fff; }
  .bar { display:none; }
  .sheet { margin:0; box-shadow:none; width:auto; min-height:0; padding:0; }
  thead { display:table-header-group; }
  tr { break-inside:avoid; }
}
"""


def _format_day(day: date | None) -> str:
    return f"{MONTHS[day.month - 1]} {day.day}, {day.year}" if day else ""


def render_page(rows: dict[str, list[dict]], year: int, month: int | None, nonce: str) -> str:
    e = html.escape
    sections = []
    for document_type, items in rows.items():
        if not items:
            continue
        body, current_month = [], None
        for index, row in enumerate(items, start=1):
            row_month = f"{MONTHS[row['date'].month - 1]} {row['date'].year}" if row["date"] else "Not yet approved"
            if not month and row_month != current_month:
                current_month = row_month
                body.append(f'<tr class="month"><td colspan="4">{e(row_month)}</td></tr>')
            heading = "" if document_type == "Letter Request" or not row["number"] else f"<b>No. {e(row['number'])}</b>, s. {e(str(row['series_year']))}<br>"
            day = e(_format_day(row["date"])) if row["date"] else '<span class="muted">Pending</span>'
            authors = "<br>".join(e(name) for name in row["authors"]) or '<span class="muted">Not recorded</span>'
            body.append(f'<tr><td class="num">{index}</td><td>{heading}{e(row["title"] or "")}</td><td class="date">{day}</td><td>{authors}</td></tr>')
        sections.append(
            f'<h2>{TYPE_PLURALS[document_type]} <span>({len(items)})</span></h2>'
            f'<table><thead><tr><th class="num">#</th><th>Title</th><th>{DATE_LABEL[document_type]}</th>'
            f'<th style="width:28%">Proponent / Author</th></tr></thead><tbody>{"".join(body)}</tbody></table>'
        )
    period = f"{MONTHS[month - 1]} {year}" if month else f"Series of {year}"
    content = "".join(sections) or '<p class="empty">No documents for this period.</p>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>List of Ordinances, Resolutions and Letter Requests - {e(period)}</title><style>{STYLE}</style></head>
<body><div class="bar"><button id="print">Print</button></div>
<div class="sheet">
<div class="letterhead"><div class="small">Republic of the Philippines</div><div class="small">Province of Leyte</div>
<div class="small">Municipality of Tolosa</div><div class="office">OFFICE OF THE SANGGUNIANG BAYAN</div>
<h1>List of Ordinances, Resolutions and Letter Requests</h1><div class="sub">{e(period)}</div></div>
{content}
<div class="signatures">
<div><div class="role">Prepared by:</div><div class="line"></div><div class="role">SB Secretariat Staff</div></div>
<div><div class="role">Certified correct:</div><div class="line"></div><div class="role">Secretary to the Sangguniang Bayan</div></div></div>
<div class="footer"><span>Generated by SB Tolosa Document Tracking</span><span>Printed {e(_format_day(lgu_today()))}</span></div>
</div>
<script nonce="{nonce}">document.getElementById("print").onclick = () => window.print();</script>
</body></html>"""


@router.post("/link")
def create_print_list_link(payload: PrintListRequest, current_user: models.User = Depends(get_current_user)):
    """A short-lived link to the printable list, for the viewer's browser to open."""
    require_permission(current_user, "print_documents")
    types = [document_type for document_type in DOCUMENT_TYPES if document_type in payload.types]
    if not types:
        raise HTTPException(status_code=400, detail="Choose at least one document type.")
    token = create_download_token({"sub": current_user.username, "print_list": {"year": payload.year, "month": payload.month, "types": types}})
    return {"url": f"{_public_base_url()}/print-list/page?download_token={quote(token, safe='')}"}


@router.get("/page", response_class=HTMLResponse)
def print_list_page(download_token: str = Query(...), db: Session = Depends(get_db)):
    payload = decode_download_token(download_token)
    options = payload.get("print_list")
    if not isinstance(options, dict):
        raise HTTPException(status_code=403, detail="Link is not a print list link")
    user = db.query(models.User).filter(models.User.username == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="Link user not found")
    ensure_active_user(user)
    require_permission(user, "print_documents")
    request = PrintListRequest(**options)
    nonce = secrets.token_urlsafe(16)
    page = render_page(list_rows(db, request.year, request.month, request.types), request.year, request.month, nonce)
    # The app-wide CSP blocks inline style and script; this page is self-contained.
    return HTMLResponse(page, headers={
        "Content-Security-Policy": f"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; base-uri 'none'; frame-ancestors 'none'",
        "Cache-Control": "no-store",
    })
