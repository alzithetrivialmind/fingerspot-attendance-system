from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.sql import func
from app.database import Base
from sqlalchemy.types import TIMESTAMP

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    cloud_id = Column(String(50), nullable=False, unique=True, index=True)
    sn = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())
