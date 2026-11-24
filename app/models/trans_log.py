from sqlalchemy import Column, String, JSON, Enum, Integer
from sqlalchemy.sql import func
from app.database import Base
from sqlalchemy.types import TIMESTAMP

class FingerspotTransLog(Base):
    __tablename__ = "fingerspot_trans_logs"

    trans_id = Column(String(100), primary_key=True, index=True)
    cloud_id = Column(String(50), nullable=False)
    action_type = Column(String(50), nullable=False, comment='get_userid_list, get_userinfo, etc.')
    request_payload = Column(JSON, nullable=True)
    status = Column(Enum('PENDING', 'SUCCESS', 'FAILED', name='trans_status'), default='PENDING', server_default='PENDING')
    total_items = Column(Integer, default=0, server_default='0')
    processed_items = Column(Integer, default=0, server_default='0')
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())
