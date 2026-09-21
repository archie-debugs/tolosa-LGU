from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..auth_jwt import get_current_user
from ..core import record_audit_log, require_permission
from ..database import get_db

router = APIRouter(prefix="/reference-data", tags=["reference-data"])


class DefinitionPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class DefinitionUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    is_active: bool | None = None


def _definition_query(db: Session, kind: str):
    if kind == "categories":
        return models.Category
    if kind == "document-types":
        return models.DocumentType
    raise HTTPException(status_code=404, detail="Unknown definition type")


def _serialize(item):
    return {"id": item.id, "name": item.name, "is_active": bool(item.is_active)}


def _require_admin(current_user):
    if (getattr(current_user, "role", "") or "").strip().lower() != "super administrator":
        raise HTTPException(status_code=403, detail="Super Administrator access required")


@router.get("/{kind}")
def list_definitions(kind: str, active_only: bool = Query(False), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _require_admin(current_user)
    model = _definition_query(db, kind)
    query = db.query(model)
    if active_only:
        query = query.filter(model.is_active.is_(True))
    return [_serialize(item) for item in query.order_by(model.name.asc()).all()]


@router.post("/{kind}")
def create_definition(kind: str, payload: DefinitionPayload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _require_admin(current_user)
    model = _definition_query(db, kind)
    name = payload.name.strip()
    existing = db.query(model).filter(model.name.ilike(name)).first()
    if existing:
        raise HTTPException(status_code=409, detail="A definition with this name already exists")
    item = model(name=name, is_active=True)
    db.add(item)
    db.commit()
    db.refresh(item)
    record_audit_log(db, actor=current_user.username, action="REFERENCE_DEFINITION_CREATED", target_type=kind, target_id=str(item.id), details=f"Created {kind[:-1]} {name}")
    return _serialize(item)


@router.put("/{kind}/{definition_id}")
def update_definition(kind: str, definition_id: int, payload: DefinitionUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _require_admin(current_user)
    model = _definition_query(db, kind)
    item = db.query(model).filter(model.id == definition_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Definition not found")
    name = payload.name.strip()
    duplicate = db.query(model).filter(model.name.ilike(name), model.id != definition_id).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="A definition with this name already exists")
    item.name = name
    if payload.is_active is not None:
        item.is_active = payload.is_active
    db.commit()
    db.refresh(item)
    record_audit_log(db, actor=current_user.username, action="REFERENCE_DEFINITION_UPDATED", target_type=kind, target_id=str(item.id), details=f"Updated {kind[:-1]} {name}; active={bool(item.is_active)}")
    return _serialize(item)
