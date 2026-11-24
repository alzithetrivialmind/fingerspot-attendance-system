from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime

class AttendanceLogBase(BaseModel):
    employee_pin: str = Field(..., max_length=20)
    device_sn: str = Field(..., max_length=50)
    scan_time: datetime
    verify_mode: Optional[int] = None
    io_mode: Optional[int] = None
    department_id_snapshot: Optional[int] = None
    source: Optional[str] = "REALTIME"

class AttendanceLog(AttendanceLogBase):
    id: int
    employee_name: Optional[str] = None
    employee_nik: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Satu scan dari webhook attlog atau get_attlog
class FingerspotWebhookItem(BaseModel):
    pin: str
    scan_time: datetime
    verify_mode: Optional[int] = None
    io_mode: Optional[int] = None
    sn: str

class PullAttendanceRequest(BaseModel):
    cloud_id: str
    start_date: str
    end_date: str

class PaginatedAttendance(BaseModel):
    data: List[AttendanceLog]
    total: int
    page: int
    limit: int
    total_pages: int
