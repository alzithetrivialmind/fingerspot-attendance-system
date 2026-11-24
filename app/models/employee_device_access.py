from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum

class SyncStatusEnum(str, enum.Enum):
    PENDING_ADD = "PENDING_ADD"
    PENDING_REMOVE = "PENDING_REMOVE"
    SYNCED = "SYNCED"
    FAILED = "FAILED"

class EmployeeDeviceAccess(Base):
    __tablename__ = "employee_device_access"

    id = Column(Integer, primary_key=True, index=True)
    employee_pin = Column(String(20), ForeignKey("employees.pin", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    sync_status = Column(String(20), default=SyncStatusEnum.PENDING_ADD.value, nullable=False)
    last_sync_time = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, default=0, server_default="0", nullable=False)
    last_error = Column(String(255), nullable=True)
    failed_action = Column(String(20), nullable=True)  # PENDING_ADD / PENDING_REMOVE yang gagal
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", back_populates="device_accesses")
    device = relationship("Device")
