from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    tracking_number: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    document_type: Optional[str] = None
    category: Optional[str] = None
    originating_office: Optional[str] = None
    current_office: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = "Pending"
    priority: Optional[str] = "Medium"
    remarks: Optional[str] = None
    author: Optional[str] = None
    session: Optional[str] = None
    date_registered: Optional[str] = None
    attachment_name: Optional[str] = None
    qr_code_value: Optional[str] = None
    created_by: Optional[str] = None
    archived: bool = False


class DocumentRegistration(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    document_type: Optional[str] = None
    current_office: Optional[str] = None
    priority: Optional[str] = "Medium"
    tracking_number: Optional[str] = None


class DocumentUpdate(BaseModel):
    tracking_number: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    document_type: Optional[str] = None
    category: Optional[str] = None
    originating_office: Optional[str] = None
    current_office: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    remarks: Optional[str] = None
    author: Optional[str] = None
    session: Optional[str] = None
    date_registered: Optional[str] = None
    attachment_name: Optional[str] = None
    qr_code_value: Optional[str] = None
    created_by: Optional[str] = None
    archived: Optional[bool] = None


class DocumentResponse(BaseModel):
    id: int
    tracking_number: str
    title: str
    description: Optional[str] = None
    document_type: Optional[str] = None
    category: Optional[str] = None
    originating_office: Optional[str] = None
    current_office: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    remarks: Optional[str] = None
    author: Optional[str] = None
    session: Optional[str] = None
    date_registered: Optional[str] = None
    attachment_name: Optional[str] = None
    qr_code_value: Optional[str] = None
    created_by: Optional[str] = None
    created_by_id: Optional[int] = None
    document_type_id: Optional[int] = None
    category_id: Optional[int] = None
    originating_office_id: Optional[int] = None
    current_office_id: Optional[int] = None
    history_rows: Optional[list[dict]] = None
    attachments: Optional[list[dict]] = None
    archived: bool
    archived_at: Optional[datetime] = None
    archived_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

