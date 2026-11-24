from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import date, datetime

class EmployeeBase(BaseModel):
    pin: str = Field(..., max_length=20)
    full_name: str = Field(..., max_length=150)
    nik: Optional[str] = Field(None, max_length=20)
    rfid: Optional[str] = Field(None, max_length=50)
    birth_date: Optional[date] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    company_id: Optional[int] = None
    join_date: Optional[date] = None
    contract_start_date: Optional[date] = None
    contract_end_date: Optional[date] = None
    is_active: bool = True

    device_access_ids: Optional[List[int]] = None

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeUpdate(BaseModel):
    pin: Optional[str] = Field(None, max_length=20)
    full_name: Optional[str] = Field(None, max_length=150)
    nik: Optional[str] = Field(None, max_length=20)
    rfid: Optional[str] = Field(None, max_length=50)
    birth_date: Optional[date] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    company_id: Optional[int] = None
    join_date: Optional[date] = None
    contract_start_date: Optional[date] = None
    contract_end_date: Optional[date] = None
    is_active: Optional[bool] = None
    device_access_ids: Optional[List[int]] = None

class DeviceAccessInfo(BaseModel):
    device_id: int
    sync_status: str
    last_error: Optional[str] = None
    failed_action: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class Employee(EmployeeBase):
    id: int
    photo_path: Optional[str] = None
    created_at: datetime
    updated_by: Optional[str] = None
    department_name: Optional[str] = None
    position_name: Optional[str] = None
    company_name: Optional[str] = None
    has_device_template: bool = False
    device_accesses: Optional[List[DeviceAccessInfo]] = None

    model_config = ConfigDict(from_attributes=True)

class PaginatedEmployee(BaseModel):
    data: List[Employee]
    total: int
    page: int
    limit: int
    total_pages: int

class BulkEmployeeStatusRequest(BaseModel):
    employee_ids: List[int]
    is_active: bool

class BulkEmployeeDeleteRequest(BaseModel):
    employee_ids: List[int]

