from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class DeviceBase(BaseModel):
    name: str
    cloud_id: str
    sn: Optional[str] = None
    is_active: bool = True

class DeviceCreate(DeviceBase):
    pass

class DeviceInDB(DeviceBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class SyncStatus(BaseModel):
    trans_id: str
    status: str
    total_items: int
    processed_items: int
    data: Optional[dict] = None
