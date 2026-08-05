from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Admin")

class LegislativeItem(Base):
    __tablename__ = "legislative_items"

    id = Column(Integer, primary_key=True, index=True)
    tracking_uuid = Column(String, unique=True, index=True) # Data encoded into the physical QR code
    title = Column(String, index=True)                     # Title of the Ordinance or Resolution
    item_type = Column(String)                             # Ordinance, Resolution, Committee Report
    current_status = Column(String, default="First Reading") # First Reading, Committee Review, Approved, etc.
    current_location = Column(String, nullable=False, default="Records Registry")
    assigned_committee = Column(String, nullable=True)     
    source_filename = Column(String, nullable=True)
    
    logs = relationship("LegislativeTrackingLog", back_populates="item")
    history = relationship("DocumentHistory", back_populates="item", cascade="all, delete-orphan")

class LegislativeTrackingLog(Base):
    __tablename__ = "legislative_tracking_logs"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("legislative_items.id"))
    location_stamp = Column(String)   # e.g., "Office of the Municipal Mayor", "Committee Room"
    action_taken = Column(String)     # e.g., "Signed", "Received for Review"
    scanned_by = Column(String)       # Accounts for who scanned the QR code via the tracking app
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    item = relationship("LegislativeItem", back_populates="logs")


class DocumentHistory(Base):
    __tablename__ = "document_history"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("legislative_items.id"), nullable=False)
    previous_location = Column(String, nullable=False)
    receiving_office = Column(String, nullable=False)
    new_location = Column(String, nullable=False)
    logged_in_user = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    item = relationship("LegislativeItem", back_populates="history")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=True, index=True)
    target_id = Column(String, nullable=True, index=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)