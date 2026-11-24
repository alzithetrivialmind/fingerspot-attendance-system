from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    pin = Column(String(20), unique=True, nullable=False, index=True)
    full_name = Column(String(150), nullable=False)
    nik = Column(String(20), unique=True)
    birth_date = Column(Date)
    department_id = Column(Integer, ForeignKey("departments.id"))
    join_date = Column(Date)
    photo_path = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(String(100))

    contract_start_date = Column(Date)
    contract_end_date = Column(Date)
    position_id = Column(Integer, ForeignKey("positions.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    rfid = Column(String(50), nullable=True)
    fingerprint_template = Column(String, nullable=True)
    device_privilege = Column(String(5), nullable=True)  # Hak di mesin dari get_userinfo: 1 pengguna, 2 admin, 3 subadmin

    department = relationship("Department", back_populates="employees")
    position = relationship("Position")
    company = relationship("Company")
    device_accesses = relationship("EmployeeDeviceAccess", back_populates="employee", cascade="all, delete-orphan")

    @property
    def has_device_template(self):
        return bool(self.fingerprint_template)

    @property
    def department_name(self):
        return self.department.name if self.department else None

    @property
    def position_name(self):
        return self.position.name if self.position else None

    @property
    def company_name(self):
        return self.company.name if self.company else None
