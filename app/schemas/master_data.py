from pydantic import BaseModel, ConfigDict

class DepartmentBase(BaseModel):
    name: str

class Department(DepartmentBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class PositionBase(BaseModel):
    name: str

class Position(PositionBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class CompanyBase(BaseModel):
    name: str

class Company(CompanyBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

