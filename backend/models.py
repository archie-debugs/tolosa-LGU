from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


class Office(Base):
    __tablename__ = "offices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


class DocumentType(Base):
    __tablename__ = "document_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    tracking_number = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # legacy free-text columns (kept for backfill compatibility)
    document_type = Column(String, nullable=True, index=True)
    category = Column(String, nullable=True, index=True)
    originating_office = Column(String, nullable=True, index=True)
    current_office = Column(String, nullable=True, index=True)
    assigned_to = Column(String, nullable=True, index=True)

    # normalized FK columns (new)
    document_type_id = Column(Integer, ForeignKey("document_types.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    originating_office_id = Column(Integer, ForeignKey("offices.id"), nullable=True, index=True)
    current_office_id = Column(Integer, ForeignKey("offices.id"), nullable=True, index=True)

    document_type_rel = relationship("DocumentType", foreign_keys=[document_type_id])
    category_rel = relationship("Category", foreign_keys=[category_id])
    originating_office_rel = relationship("Office", foreign_keys=[originating_office_id])
    current_office_rel = relationship("Office", foreign_keys=[current_office_id])

    status = Column(String, nullable=False, default="Pending", index=True)
    priority = Column(String, nullable=False, default="Medium", index=True)
    remarks = Column(Text, nullable=True)
    author = Column(String, nullable=True, index=True)
    session = Column(String, nullable=True, index=True)
    date_registered = Column(String, nullable=True, index=True)
    attachment_name = Column(String, nullable=True)
    qr_code_value = Column(String, nullable=True, index=True)

    # new attachment relation will be defined via Attachment model

    # user references: keep legacy `created_by` string, but add FK to users
    created_by = Column(String, nullable=True, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    created_by_rel = relationship("User", foreign_keys=[created_by_id])
    assigned_to_rel = relationship("User", foreign_keys=[assigned_to_id])

    archived = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), index=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Super Administrator")
    full_name = Column(String, nullable=True)
    email = Column(String, nullable=True, index=True)
    permissions = Column(Text, nullable=True, default="[]")
    status = Column(String, nullable=False, default="Active", index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), index=True)


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    original_filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    mime_type = Column(String, nullable=True)
    size = Column(Integer, nullable=True)
    checksum = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class DocumentHistory(Base):
    __tablename__ = "document_history"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    actor = Column(String, nullable=True, index=True)
    from_office = Column(String, nullable=True)
    to_office = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"

    id = Column(Integer, primary_key=True, index=True)
    registration_reference = Column(String, unique=True, index=True, nullable=False)

    first_name = Column(String, nullable=False)
    middle_name = Column(String, nullable=True)
    last_name = Column(String, nullable=False)
    suffix = Column(String, nullable=True)

    contact_number = Column(String, nullable=True)
    email = Column(String, nullable=False, index=True)
    username = Column(String, nullable=False, index=True)

    office = Column(String, nullable=True)
    position = Column(String, nullable=True)
    requested_access = Column(String, nullable=True)
    assigned_role = Column(String, nullable=True)

    id_type = Column(String, nullable=True)
    id_number = Column(String, nullable=True)
    id_file_path = Column(String, nullable=True)

    # store hashed password only
    hashed_password = Column(String, nullable=False)

    status = Column(String, nullable=False, default="Pending", index=True)
    rejection_reason = Column(Text, nullable=True)

    reviewed_by = Column(String, nullable=True, index=True)
    reviewed_at = Column(DateTime, nullable=True, index=True)
    approved_by = Column(String, nullable=True, index=True)
    approved_at = Column(DateTime, nullable=True, index=True)
    rejected_by = Column(String, nullable=True, index=True)
    rejected_at = Column(DateTime, nullable=True, index=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=True, index=True)
    target_id = Column(String, nullable=True, index=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class StatusLookup(Base):
    __tablename__ = "status_lookup"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


class PriorityLookup(Base):
    __tablename__ = "priority_lookup"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
