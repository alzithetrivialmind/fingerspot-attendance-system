from sqlalchemy.orm import Session
from app.models.employee import Employee
from app.models.attendance import AttendanceLog
from app.schemas.attendance import FingerspotWebhookItem

SOURCE_HIERARCHY = {
    "REALTIME": 3,
    "PULLED": 2,
    "IMPORTED": 1,
}

def process_webhook_attendance(db: Session, item: FingerspotWebhookItem, raw_payload: dict, source: str = "REALTIME") -> bool:
    # 1. Hanya PIN yang terdaftar sebagai karyawan yang disimpan.
    pin_str = str(item.pin).strip()
    employee = db.query(Employee).filter(Employee.pin == pin_str).first()
    
    # Jika karyawan tidak terdaftar di database (misal belum dibuat atau sudah dihapus total),
    # data absensi TIDAK AKAN disimpan ke database.
    if not employee:
        return False

    department_id = employee.department_id
    incoming_priority = SOURCE_HIERARCHY.get(source.upper(), 1)

    # 2. Cek apakah ada data dengan PIN dan waktu scan yang sama persis (lintas sumber)
    existing = db.query(AttendanceLog).filter(
        AttendanceLog.employee_pin == employee.pin,
        AttendanceLog.scan_time == item.scan_time
    ).first()

    if not existing:
        new_log = AttendanceLog(
            employee_pin=employee.pin,
            device_sn=item.sn or "UNKNOWN",
            scan_time=item.scan_time,
            verify_mode=item.verify_mode,
            io_mode=item.io_mode,
            department_id_snapshot=department_id,
            source=source.upper(),
            raw_payload=raw_payload
        )
        db.add(new_log)
        db.commit()
        return True
    else:
        # 3. Hierarki sumber: REALTIME > PULLED > IMPORTED
        # Jika data yang masuk memiliki prioritas lebih tinggi dibanding yang sudah ada (misal data REALTIME menggantikan IMPORTED),
        # perbarui record tersebut ke sumber yang lebih tinggi tanpa membuat duplikasi data.
        existing_priority = SOURCE_HIERARCHY.get((existing.source or "").upper(), 1)
        if incoming_priority > existing_priority:
            existing.source = source.upper()
            if item.sn:
                existing.device_sn = item.sn
            existing.verify_mode = item.verify_mode
            existing.io_mode = item.io_mode
            existing.department_id_snapshot = department_id
            existing.raw_payload = raw_payload
            db.commit()
            return True
        
        # Jika data yang masuk sama atau lebih rendah prioritasnya, abaikan (mencegah double data)
        return False

