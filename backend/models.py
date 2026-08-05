from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Admin")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=True, index=True)
    target_id = Column(String, nullable=True, index=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class LegislativeItem(Base):
    __tablename__ = "legislative_items"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, index=True, nullable=True)
    tracking_uuid = Column(String, unique=True, index=True, nullable=True)
    title = Column(String, nullable=True)
    item_type = Column(String, nullable=True)
    current_status = Column(String, nullable=True, default="Registered")
    current_location = Column(String, nullable=True, default="Records Registry")
    source_filename = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class DocumentHistory(Base):
    __tablename__ = "document_history"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("legislative_items.id"), nullable=False, index=True)
    previous_location = Column(String, nullable=True)
    receiving_office = Column(String, nullable=True)
    new_location = Column(String, nullable=True)
    logged_in_user = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class LegislativeTrackingLog(Base):
    __tablename__ = "legislative_tracking_logs"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("legislative_items.id"), nullable=False, index=True)
    location_stamp = Column(String, nullable=True)
    action_taken = Column(String, nullable=True)
    scanned_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)