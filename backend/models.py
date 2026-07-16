from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class LegislativeItem(Base):
    __tablename__ = "legislative_items"

    id = Column(Integer, primary_key=True, index=True)
    tracking_uuid = Column(String, unique=True, index=True) # Data encoded into the physical QR code
    title = Column(String, index=True)                     # Title of the Ordinance or Resolution
    item_type = Column(String)                             # Ordinance, Resolution, Committee Report
    current_status = Column(String, default="First Reading") # First Reading, Committee Review, Approved, etc.
    assigned_committee = Column(String, nullable=True)     
    
    logs = relationship("LegislativeTrackingLog", back_populates="item")

class LegislativeTrackingLog(Base):
    __tablename__ = "legislative_tracking_logs"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("legislative_items.id"))
    location_stamp = Column(String)   # e.g., "Office of the Municipal Mayor", "Committee Room"
    action_taken = Column(String)     # e.g., "Signed", "Received for Review"
    scanned_by = Column(String)       # Accounts for who scanned the QR code via the tracking app
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    item = relationship("LegislativeItem", back_populates="logs")