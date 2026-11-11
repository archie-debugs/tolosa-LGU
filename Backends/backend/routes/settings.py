import base64
import html
import io
import json
import os
import secrets
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import Any

import qrcode
from PIL import Image
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..core import DEFAULT_SYSTEM_SETTINGS, SYSTEM_SETTING_TYPES, get_current_admin_user, record_audit_log
from ..authentication import get_current_user
from ..database import get_db

router = APIRouter()


# The smallest and largest value each number setting may have.
SETTING_RANGES = {"session_timeout_minutes": (5, 1440), "upload_max_size_mb": (1, 100)}
SETTING_NAMES = {"session_timeout_minutes": "Session timeout (minutes)", "upload_max_size_mb": "Max upload size (MB)"}


class SystemSettingsUpdate(BaseModel):
    settings: dict[str, Any]


def _coerce_setting_value(key: str, value: Any) -> Any:
    expected_type = SYSTEM_SETTING_TYPES.get(key)
    if expected_type is None:
        raise HTTPException(status_code=400, detail=f"Unknown system setting: {key}")

    if expected_type is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "false"}:
                return normalized == "true"
        raise HTTPException(status_code=400, detail=f"Setting '{key}' must be a boolean value")

    if expected_type is int:
        if isinstance(value, bool):
            raise HTTPException(status_code=400, detail=f"Setting '{key}' must be an integer")
        if isinstance(value, str):
            try:
                value = int(value)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Setting '{key}' must be an integer") from exc
        if not isinstance(value, int):
            raise HTTPException(status_code=400, detail=f"Setting '{key}' must be an integer")
        low, high = SETTING_RANGES.get(key, (None, None))
        if low is not None and not low <= value <= high:
            raise HTTPException(status_code=400, detail=f"{SETTING_NAMES[key]} must be {low} to {high}")
        return value

    if expected_type is str:
        if value is None:
            raise HTTPException(status_code=400, detail=f"Setting '{key}' cannot be empty")
        return str(value)

    if expected_type is list:
        if not isinstance(value, list):
            raise HTTPException(status_code=400, detail=f"Setting '{key}' must be a list")
        if key == "homepage_announcements":
            return _clean_announcements(value)
        return value

    if expected_type is dict:
        if not isinstance(value, dict):
            raise HTTPException(status_code=400, detail=f"Setting '{key}' must be an object")
        if key == "retention_months":
            return _clean_retention(value)
        return value

    return value


# At most 100 years; anything longer should be kept permanently.
MAX_RETENTION_MONTHS = 1200


def _clean_retention(value: dict) -> dict[str, int | None]:
    """Every document type's retention in months, None for permanent; types left out keep their default."""
    cleaned = dict(DEFAULT_SYSTEM_SETTINGS["retention_months"])
    for document_type, months in value.items():
        if document_type not in cleaned:
            raise HTTPException(status_code=400, detail=f"Unknown document type: {document_type}")
        if months is None:
            cleaned[document_type] = None
            continue
        if isinstance(months, bool) or not isinstance(months, int) or not 1 <= months <= MAX_RETENTION_MONTHS:
            raise HTTPException(status_code=400, detail=f"{document_type} retention must be 1 to {MAX_RETENTION_MONTHS} months, or permanent")
        cleaned[document_type] = months
    return cleaned


MAX_ANNOUNCEMENTS = 10
ANNOUNCEMENT_FIELD_LIMITS = {"category": 40, "title": 120, "date": 40, "details": 300}


def _clean_announcements(items: list) -> list[dict[str, str]]:
    if len(items) > MAX_ANNOUNCEMENTS:
        raise HTTPException(status_code=400, detail=f"The homepage can show at most {MAX_ANNOUNCEMENTS} announcements")
    cleaned = []
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"Announcement {number} must be an object")
        announcement = {}
        for field, limit in ANNOUNCEMENT_FIELD_LIMITS.items():
            text = str(item.get(field) or "").strip()
            if len(text) > limit:
                raise HTTPException(status_code=400, detail=f"Announcement {number}: {field} must be at most {limit} characters")
            announcement[field] = text
        if not announcement["title"]:
            raise HTTPException(status_code=400, detail=f"Announcement {number} needs a title")
        cleaned.append(announcement)
    return cleaned


def _decode_stored_value(key: str, raw_value: Any) -> Any:
    if raw_value is None:
        return DEFAULT_SYSTEM_SETTINGS[key]
    if isinstance(raw_value, str):
        try:
            decoded = json.loads(raw_value)
        except Exception:
            decoded = raw_value
        return _coerce_setting_value(key, decoded)
    return _coerce_setting_value(key, raw_value)


def _load_settings(db: Session) -> dict[str, Any]:
    settings = dict(DEFAULT_SYSTEM_SETTINGS)
    for row in db.query(models.SystemSetting).all():
        if row.key in settings:
            try:
                settings[row.key] = _decode_stored_value(row.key, row.value)
            except HTTPException:
                settings[row.key] = DEFAULT_SYSTEM_SETTINGS.get(row.key)
    return settings


def max_upload_bytes(db: Session) -> int:
    """The Max Upload Size setting, in bytes."""
    return _load_settings(db)["upload_max_size_mb"] * 1024 * 1024


def too_large(db: Session) -> str:
    return f"The file is larger than the {_load_settings(db)['upload_max_size_mb']} MB upload limit."


def require_public_portal(db: Session = Depends(get_db)) -> None:
    """The public pages' data is closed while Public Portal Enabled is off; staff login and QR scanning stay open."""
    if not _load_settings(db)["public_portal_enabled"]:
        raise HTTPException(status_code=503, detail="The public portal is closed for now.")


def retention_months(db: Session) -> dict[str, int | None]:
    """Months each document type is kept after it is archived; None keeps it permanently."""
    return _load_settings(db)["retention_months"]


@router.get("/system-settings")
def get_system_settings(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user),
):
    settings = _load_settings(db)
    return {"settings": settings}


@router.put("/system-settings")
def update_system_settings(
    payload: SystemSettingsUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user),
):
    if not isinstance(payload.settings, dict):
        raise HTTPException(status_code=400, detail="Settings payload must be an object")

    settings = _load_settings(db)
    for key, value in payload.settings.items():
        normalized = _coerce_setting_value(key, value)
        settings[key] = normalized

        existing = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
        raw_value = normalized if SYSTEM_SETTING_TYPES[key] is str else json.dumps(normalized)
        if existing is None:
            db.add(models.SystemSetting(key=key, value=raw_value, category="system", description=f"System setting: {key}", updated_by=current_admin.username))
        else:
            existing.value = raw_value
            existing.updated_by = current_admin.username
            existing.category = "system"
            existing.description = f"System setting: {key}"

        record_audit_log(
            db,
            actor=current_admin.username,
            action="SYSTEM_SETTINGS_UPDATED",
            target_type="SystemSetting",
            target_id=key,
            details=f"Updated {key} to {raw_value}",
            commit=False,
        )

    db.commit()
    return {"message": "System settings updated", "settings": settings}


@router.get("/public/site", tags=["public"])
def get_public_site(db: Session = Depends(get_db)):
    """What the login page and public pages show before anyone signs in: the names, and whether the portal is open."""
    settings = _load_settings(db)
    return {key: settings[key] for key in ("organization_name", "system_name", "public_portal_enabled")}


@router.get("/public/announcements", tags=["public"], dependencies=[Depends(require_public_portal)])
def get_public_announcements(db: Session = Depends(get_db)):
    """The homepage's announcements; anyone may read them."""
    return {"announcements": _load_settings(db)["homepage_announcements"]}


def _system_link() -> str:
    """The address people open the system at: FRONTEND_PUBLIC_URL, or this computer's LAN address in development."""
    link = os.getenv("FRONTEND_PUBLIC_URL", "").strip().rstrip("/")
    if not link:
        raise HTTPException(status_code=503, detail="The system's public link is not configured (FRONTEND_PUBLIC_URL).")
    return link


def _qr_png(text: str) -> bytes:
    out = io.BytesIO()
    qrcode.make(text, box_size=12, border=4).save(out, format="PNG")
    return out.getvalue()


@router.get("/system-link")
def get_system_link(current_user: models.User = Depends(get_current_user)):
    """The system's link and its QR code, for sharing it from Settings."""
    from .documents import _public_base_url  # documents imports this module, so not at the top

    link = _system_link()
    return {"url": link, "qr_png_base64": base64.b64encode(_qr_png(link)).decode("ascii"),
            "qr_image_url": f"{_public_base_url()}/system-link/qr"}


ASSETS = Path(__file__).resolve().parents[3] / "frontend" / "frontend_public" / "assets"
QR_PAGE = Path(__file__).resolve().parents[1] / "system_qr_page.html"


@lru_cache(maxsize=None)
def _asset_data_uri(name: str, side: int, kind: str) -> str | None:
    """A shrunk copy of a login-page image as a data URI, made once; None when the image is missing."""
    try:
        image = Image.open(ASSETS / name).convert("RGB")
    except OSError:
        return None
    image.thumbnail((side, side))
    out = io.BytesIO()
    image.save(out, kind, quality=70) if kind == "JPEG" else image.save(out, kind, optimize=True)
    return f"data:image/{kind.lower()};base64,{base64.b64encode(out.getvalue()).decode('ascii')}"


@router.get("/system-link/qr", tags=["public"], response_class=HTMLResponse)
def get_system_link_qr_page():
    """The QR code on a page in the system's look, with the link, to copy, save or print. It only holds the public link."""
    nonce = secrets.token_urlsafe(16)
    seal = _asset_data_uri("login_seal.png", 176, "PNG")
    building = _asset_data_uri("login_municipal_building.png", 900, "JPEG")
    page = Template(QR_PAGE.read_text(encoding="utf-8")).safe_substitute(
        link=html.escape(_system_link()),
        nonce=nonce,
        seal=f'<div class="seal"><img src="{seal}" alt="Seal of the Sangguniang Bayan of Tolosa"></div>' if seal else "",
        building=f"url({building})" if building else "none",
    )
    # The app's default policy (main.py) refuses inline styles, scripts and data: images; this page needs
    # its own style and script (by nonce), its embedded seal and photo, and Google Fonts, and nothing else.
    policy = (
        f"default-src 'none'; style-src 'nonce-{nonce}' https://fonts.googleapis.com; script-src 'nonce-{nonce}'; "
        "img-src 'self' data:; font-src https://fonts.gstatic.com; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'"
    )
    return HTMLResponse(page, headers={"Content-Security-Policy": policy})


@router.get("/system-link/qr.png", tags=["public"])
def get_system_link_qr():
    """The QR image on its own, opened in a browser tab to copy or save. It only holds the public link."""
    return Response(_qr_png(_system_link()), media_type="image/png",
                    headers={"Content-Disposition": 'inline; filename="sb-tolosa-system-qr.png"'})
