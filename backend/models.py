from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime, timezone
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Admin")


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

    id_type = Column(String, nullable=True)
    id_number = Column(String, nullable=True)
    id_file_path = Column(String, nullable=True)

    # store hashed password only
    hashed_password = Column(String, nullable=False)

    status = Column(String, nullable=False, default="Pending", index=True)
    rejection_reason = Column(Text, nullable=True)

    reviewed_by = Column(String, nullable=True, index=True)
    reviewed_at = Column(DateTime, nullable=True, index=True)

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
