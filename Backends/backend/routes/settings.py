import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..core import DEFAULT_SYSTEM_SETTINGS, SYSTEM_SETTING_TYPES, record_audit_log, require_user_management_permission
from ..database import get_db

router = APIRouter()


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
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Setting '{key}' must be an integer") from exc
        raise HTTPException(status_code=400, detail=f"Setting '{key}' must be an integer")

    if expected_type is str:
        if value is None:
            raise HTTPException(status_code=400, detail=f"Setting '{key}' cannot be empty")
        return str(value)

    if expected_type is list:
        if not isinstance(value, list):
            raise HTTPException(status_code=400, detail=f"Setting '{key}' must be a list")
        return value

    return value


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


@router.get("/system-settings")
def get_system_settings(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("modify_system_settings")),
):
    settings = _load_settings(db)
    return {"settings": settings}


@router.put("/system-settings")
def update_system_settings(
    payload: SystemSettingsUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_user_management_permission("modify_system_settings")),
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
        )

    db.commit()
    return {"message": "System settings updated", "settings": settings}
