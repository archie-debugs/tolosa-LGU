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
    routing_history: Optional[list[dict]] = None
    created_by: Optional[str] = None
    archived: bool = False


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
    routing_history: Optional[list[dict]] = None
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
    routing_history: Optional[list[dict]] = None
    created_by: Optional[str] = None
    archived: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
