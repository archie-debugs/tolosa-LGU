import secrets
import secrets
from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, CheckConstraint, Index, func, text
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
    office_code = Column(String(32), unique=True, index=True, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    users = relationship("User", back_populates="office", foreign_keys="User.office_id")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)


class DocumentType(Base):
    __tablename__ = "document_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    tracking_number = Column(String, unique=True, index=True, nullable=False)
    document_number = Column(String, nullable=True)
    series_year = Column(Integer, nullable=True)
    qr_token = Column(String(64), unique=True, index=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
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

    status = Column(String, nullable=False, default="Approved", index=True)
    priority = Column(String, nullable=False, default="Medium", index=True)
    is_public = Column(Boolean, nullable=False, default=False, index=True)
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
    archived_at = Column(DateTime, nullable=True, index=True)
    archived_by = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), index=True)


class DocumentOffice(Base):
    __tablename__ = "document_offices"
    __table_args__ = (
        UniqueConstraint("document_id", "office_id", name="uq_document_offices_document_office"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    office_id = Column(Integer, ForeignKey("offices.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    document = relationship("Document", foreign_keys=[document_id])
    office = relationship("Office", foreign_keys=[office_id])


class DocumentHandoff(Base):
    __tablename__ = "document_handoffs"
    __table_args__ = (
        CheckConstraint("sending_office_id <> receiving_office_id", name="ck_document_handoffs_sender_receiver_diff"),
        CheckConstraint("status IN ('Pending Receipt', 'Received')", name="ck_document_handoffs_status"),
        Index("ix_document_handoffs_document_id", "document_id"),
        Index("ix_document_handoffs_sending_office_id", "sending_office_id"),
        Index("ix_document_handoffs_receiving_office_id", "receiving_office_id"),
        Index("ix_document_handoffs_status", "status"),
        Index("ix_document_handoffs_sent_at", "sent_at"),
        Index("ix_document_handoffs_document_status", "document_id", "status"),
        Index(
            "uq_document_handoffs_pending_receipt",
            "document_id",
            unique=True,
            sqlite_where=text("status = 'Pending Receipt'"),
            postgresql_where=text("status = 'Pending Receipt'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    sending_office_id = Column(Integer, ForeignKey("offices.id", ondelete="CASCADE"), nullable=False)
    receiving_office_id = Column(Integer, ForeignKey("offices.id", ondelete="CASCADE"), nullable=False)
    sending_employee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    status = Column(String(50), nullable=False, default="Pending Receipt")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    document = relationship("Document", foreign_keys=[document_id])
    sending_office = relationship("Office", foreign_keys=[sending_office_id])
    receiving_office = relationship("Office", foreign_keys=[receiving_office_id])
    sending_employee = relationship("User", foreign_keys=[sending_employee_id])


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Super Administrator")
    full_name = Column(String, nullable=True)
    email = Column(String, nullable=True, index=True)
    office_id = Column(Integer, ForeignKey("offices.id"), nullable=True, index=True)
    office = relationship("Office", foreign_keys=[office_id], back_populates="users")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    permissions = Column(Text, nullable=True, default="[]")
    status = Column(String, nullable=False, default="Active", index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_login = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), index=True)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    last_activity = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoke_reason = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user = relationship("User", back_populates="sessions", foreign_keys=[user_id])


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


class DocumentTrackingNumberAlias(Base):
    __tablename__ = "document_tracking_number_aliases"
    __table_args__ = (
        UniqueConstraint("tracking_number", name="uq_tracking_number_alias_tracking_number"),
        UniqueConstraint("document_id", "tracking_number", name="uq_tracking_number_alias_document_tracking"),
    )

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    tracking_number = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DocumentReceipt(Base):
    __tablename__ = "document_receipts"
    __table_args__ = (
        UniqueConstraint("handoff_id", name="uq_document_receipts_handoff"),
        Index("ix_document_receipts_handoff_id", "handoff_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    office_id = Column(Integer, ForeignKey("offices.id", ondelete="CASCADE"), nullable=False, index=True)
    handoff_id = Column(Integer, ForeignKey("document_handoffs.id", ondelete="SET NULL"), nullable=True)
    confirmed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)
    status = Column(String, nullable=False, default="Received", index=True)
    confirmed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    document = relationship("Document", foreign_keys=[document_id])
    office = relationship("Office", foreign_keys=[office_id])
    handoff = relationship("DocumentHandoff", foreign_keys=[handoff_id])
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_user_id])


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


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True, index=True)
    value = Column(Text, nullable=False, default="{}")
    category = Column(String, nullable=False, default="system", index=True)
    description = Column(Text, nullable=True)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), index=True)


class StatusLookup(Base):
    __tablename__ = "status_lookup"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


class PriorityLookup(Base):
    __tablename__ = "priority_lookup"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
