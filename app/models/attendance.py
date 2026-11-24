from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, ForeignKey, Index, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, index=True)
    employee_pin = Column(String(20), nullable=False)
    device_sn = Column(String(50), nullable=False)
    scan_time = Column(DateTime(timezone=True), nullable=False)
    verify_mode = Column(SmallInteger)
    io_mode = Column(SmallInteger)
    department_id_snapshot = Column(Integer, ForeignKey("departments.id"))
    source = Column(String(20), default="REALTIME", nullable=False, index=True) # REALTIME, PULLED, IMPORTED
    raw_payload = Column(JSON)

    __table_args__ = (
        UniqueConstraint('employee_pin', 'device_sn', 'scan_time', name='uix_attendance_pin_sn_time'),
        Index('idx_attendance_pin_time', 'employee_pin', 'scan_time'),
        Index('idx_attendance_time', 'scan_time'),
        Index('idx_attendance_source', 'source'),
    )

    department_snapshot = relationship("Department")
    employee = relationship("Employee", primaryjoin="foreign(AttendanceLog.employee_pin) == Employee.pin", uselist=False, viewonly=True)

    @property
    def employee_name(self):
        return self.employee.full_name if self.employee else None

    @property
    def employee_nik(self):
        return self.employee.nik if self.employee else None
