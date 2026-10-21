from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    tracking_number: str = Field(..., min_length=1)
    document_number: Optional[str] = None
    series_year: int = Field(..., ge=1000, le=9999)
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    document_type: Optional[str] = None
    category: Optional[str] = None
    originating_office: Optional[str] = None
    current_office: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = "Approved"
    priority: Optional[str] = "Medium"
    is_public: bool = False
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
    document_number: Optional[str] = None
    series_year: int = Field(..., ge=1000, le=9999)
    description: Optional[str] = None
    document_type: Optional[str] = None
    current_office: Optional[str] = None
    priority: Optional[str] = "Medium"
    tracking_number: Optional[str] = None


class DocumentUpdate(BaseModel):
    tracking_number: Optional[str] = None
    document_number: Optional[str] = None
    series_year: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    document_type: Optional[str] = None
    category: Optional[str] = None
    originating_office: Optional[str] = None
    current_office: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    is_public: Optional[bool] = None
    remarks: Optional[str] = None
    author: Optional[str] = None
    session: Optional[str] = None
    date_registered: Optional[str] = None
    attachment_name: Optional[str] = None
    qr_code_value: Optional[str] = None
    created_by: Optional[str] = None
    due_date: Optional[str] = None
    # Archiving goes through the archive/restore routes, which check their own permissions.


class DocumentResponse(BaseModel):
    id: int
    tracking_number: str
    qr_token: Optional[str] = None
    canonical_qr_url: Optional[str] = None
    document_number: Optional[str] = None
    series_year: Optional[int] = None
    title: str
    description: Optional[str] = None
    document_type: Optional[str] = None
    category: Optional[str] = None
    originating_office: Optional[str] = None
    current_office: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    is_public: bool = False
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
    due_date: Optional[date] = None
    archived_by: Optional[str] = None
    office_receipt_status: Optional[str] = None
    office_receipt_confirmed_at: Optional[datetime] = None
    in_transit_to: Optional[str] = None
    in_transit_since: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaginatedDocumentResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    available_years: list[int] = Field(default_factory=list)
    available_statuses: list[str] = Field(default_factory=list)
    available_archivers: list[str] = Field(default_factory=list)
    summary: Optional[dict] = None


class DocumentHandoffCreate(BaseModel):
    receiving_office_id: int = Field(..., gt=0)


class DocumentHandoffClose(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class DocumentHandoffResponse(BaseModel):
    id: int
    document_id: int
    sending_office_id: int
    receiving_office_id: int
    sending_employee_id: int
    sent_at: datetime
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    sending_office_name: Optional[str] = None
    receiving_office_name: Optional[str] = None
    sending_employee_name: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentActionCreate(BaseModel):
    action_type: Literal["Received", "Signed", "Reviewed", "Approved", "Noted", "Other"]
    notes: Optional[str] = None


class DocumentActionResponse(BaseModel):
    id: int
    document_id: int
    office_id: int
    employee_id: Optional[int] = None
    handoff_id: int
    action_type: str
    notes: Optional[str] = None
    office_name: Optional[str] = None
    employee_name: Optional[str] = None
    performed_at: datetime
    created_at: datetime
    message: Optional[str] = None


class OfficeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    office_code: str = Field(..., min_length=1, max_length=32)
    is_active: bool = True


class OfficeUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    office_code: str = Field(..., min_length=1, max_length=32)
    is_active: bool
