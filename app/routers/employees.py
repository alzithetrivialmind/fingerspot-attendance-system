from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Dict, List, Optional
import io
import math
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from app.dependencies import get_db, get_current_user, require_operator, require_administrator
from app.core.logging_utils import log_activity
from app.core.excel_utils import ExcelReadError, read_excel_rows
from app.models.user import User
from app.models.employee import Employee
from app.models.attendance import AttendanceLog
from app.models.department import Department
from app.models.position import Position
from app.models.company import Company
from app.models.device import Device
from app.models.employee_device_access import EmployeeDeviceAccess
from app.services import device_sync_service, sync_engine
from app.schemas.employee import (
    Employee as EmployeeSchema,
    EmployeeCreate,
    EmployeeUpdate,
    PaginatedEmployee,
    BulkEmployeeStatusRequest,
    BulkEmployeeDeleteRequest
)
from app.core.storage import save_photo

router = APIRouter(
    prefix="/employees",
    tags=["employees"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/", response_model=PaginatedEmployee)
def get_employees(
    department_id: Optional[int] = None,
    position_id: Optional[int] = None,
    company_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(Employee)
    if department_id is not None:
        query = query.filter(Employee.department_id == department_id)
    if position_id is not None:
        query = query.filter(Employee.position_id == position_id)
    if company_id is not None:
        query = query.filter(Employee.company_id == company_id)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    if search:
        query = query.filter(
            or_(
                Employee.full_name.ilike(f"%{search}%"),
                Employee.pin.ilike(f"%{search}%"),
                Employee.nik.ilike(f"%{search}%")
            )
        )
    
    total_count = query.count()
    query = query.order_by(func.length(Employee.pin).asc(), Employee.pin.asc())
    offset = (page - 1) * limit
    employees = query.offset(offset).limit(limit).all()
    total_pages = math.ceil(total_count / limit) if limit > 0 else 1

    return {
        "data": employees,
        "total": total_count,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }

@router.get("/export", dependencies=[Depends(require_operator)])
def export_employees(
    department_id: Optional[int] = None,
    position_id: Optional[int] = None,
    company_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Employee)
    if department_id is not None:
        query = query.filter(Employee.department_id == department_id)
    if position_id is not None:
        query = query.filter(Employee.position_id == position_id)
    if company_id is not None:
        query = query.filter(Employee.company_id == company_id)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    if search:
        query = query.filter(
            or_(
                Employee.full_name.ilike(f"%{search}%"),
                Employee.pin.ilike(f"%{search}%"),
                Employee.nik.ilike(f"%{search}%")
            )
        )
    
    query = query.order_by(func.length(Employee.pin).asc(), Employee.pin.asc())
    employees = query.all()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employees"
    
    # Write header
    headers = [
        "ID", "PIN", "NIK", "Full Name", "Birth Date", "Join Date",
        "Contract Start", "Contract End", "Department", "Position", "Company", "Status"
    ]
    ws.append(headers)
    
    # Styled header
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Write data
    for emp in employees:
        dept_name = emp.department.name if emp.department else ""
        pos_name = emp.position.name if emp.position else ""
        comp_name = emp.company.name if emp.company else ""
        
        ws.append([
            emp.id,
            emp.pin,
            emp.nik or "",
            emp.full_name,
            emp.birth_date.strftime("%Y-%m-%d") if emp.birth_date else "",
            emp.join_date.strftime("%Y-%m-%d") if emp.join_date else "",
            emp.contract_start_date.strftime("%Y-%m-%d") if emp.contract_start_date else "",
            emp.contract_end_date.strftime("%Y-%m-%d") if emp.contract_end_date else "",
            dept_name,
            pos_name,
            comp_name,
            "Active" if emp.is_active else "Inactive"
        ])
        
    # Auto adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
        
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    log_activity(db, current_user.username, "EXPORT_DATA", f"Unduh data karyawan ({ws.max_row - 1} karyawan)")
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=employees_export.xlsx"}
    )

@router.get("/import/template", dependencies=[Depends(require_operator)])
def download_import_template():
    """Download an Excel template for importing employees."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employee Import Template"
    
    headers = ["PIN", "Full Name", "NIK", "Status", "Contract Start", "Contract End", "Department", "Position", "Company"]
    ws.append(headers)
    
    # Add some sample data to make it clear
    ws.append(["1001", "Budi Santoso", "NIK-001", "Active", "2024-01-01", "2025-01-01", "IT", "Staff", "PT Contoh"])
    ws.append(["1002", "Siti Aminah", "NIK-002", "Inactive", "2023-05-15", "2024-05-15", "HR", "Manager", "PT Contoh"])
    
    # Optional: adjust column widths for better readability
    for col_letter in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']:
        ws.column_dimensions[col_letter].width = 15
        
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=employee_import_template.xlsx"}
    )

@router.post("/import", dependencies=[Depends(require_operator)])
async def import_employees(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Import employees from Excel (.xlsx) or CSV (.csv) file.
    PIN is the unique key. If PIN exists, update the employee. If not, create new.
    Department/Position/Company columns match by name (auto-created if missing).
    
    Expected columns: PIN, Full Name, NIK, Status (Active/Inactive), 
    Contract Start, Contract End, Department, Position, Company
    """
    filename = file.filename.lower()
    
    if filename.endswith(('.xlsx', '.xls')):
        return await _import_employees_excel(file, db, current_user)
    elif filename.endswith('.csv'):
        return await _import_employees_csv(file, db, current_user)
    else:
        raise HTTPException(status_code=400, detail="Only Excel (.xlsx) or CSV (.csv) files are supported")


def _resolve_master_data(db: Session, dept_name: str, pos_name: str, comp_name: str):
    """Find or create Department/Position/Company by name. Returns (dept_id, pos_id, comp_id)."""
    dept_id = None
    pos_id = None
    comp_id = None
    
    if dept_name:
        dept = db.query(Department).filter(Department.name == dept_name).first()
        if not dept:
            dept = Department(name=dept_name)
            db.add(dept)
            db.flush()
        dept_id = dept.id
        
    if pos_name:
        pos = db.query(Position).filter(Position.name == pos_name).first()
        if not pos:
            pos = Position(name=pos_name)
            db.add(pos)
            db.flush()
        pos_id = pos.id
        
    if comp_name:
        comp = db.query(Company).filter(Company.name == comp_name).first()
        if not comp:
            comp = Company(name=comp_name)
            db.add(comp)
            db.flush()
        comp_id = comp.id
        
    return dept_id, pos_id, comp_id


def _parse_date(val):
    """Try to parse a date value from various formats."""
    from datetime import datetime, date
    if val is None or str(val).strip() == '' or str(val).strip().lower() in ('none', 'null', '-', 'nan'):
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    val_str = str(val).strip()
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%m/%d/%Y', '%d.%m.%Y', '%Y.%m.%d', '%d-%m-%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue
    return None


def _parse_status(val):
    """Parse active status from various inputs."""
    if val is None:
        return True
    val_str = str(val).strip().lower()
    if val_str in ('inactive', 'false', '0', 'no', 'tidak aktif', 'nonaktif'):
        return False
    return True


def _upsert_employee(db: Session, pin: str, data: dict):
    """Insert or update an employee by PIN. Returns ('created'|'updated', employee)."""
    existing = db.query(Employee).filter(Employee.pin == pin).first()
    
    if existing:
        for key, value in data.items():
            if value is not None:
                setattr(existing, key, value)
        db.flush()
        return 'updated', existing
    else:
        new_emp = Employee(pin=pin, **{k: v for k, v in data.items() if v is not None})
        db.add(new_emp)
        db.flush()
        return 'created', new_emp


async def _import_employees_excel(file: UploadFile, db: Session, current_user: User):
    """Process Excel file for employee import."""
    contents = await file.read()
    try:
        rows = read_excel_rows(contents, file.filename)
    except ExcelReadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rows:
        raise HTTPException(status_code=400, detail="Excel file is empty")
    
    # First row is header
    header = [str(h).strip().lower() if h else '' for h in rows[0]]
    
    # Map column names to indices
    col_map = _build_column_map(header)
    if 'pin' not in col_map:
        raise HTTPException(status_code=400, detail="Column 'PIN' not found in header row. Required column.")
    
    created = 0
    updated = 0
    errors = []
    
    for row_idx, row in enumerate(rows[1:], start=2):
        try:
            pin = str(row[col_map['pin']]).strip() if row[col_map['pin']] else None
            if not pin:
                errors.append(f"Row {row_idx}: PIN is empty, skipped")
                continue
            
            # Savepoint per baris: error DB (mis. NIK duplikat) hanya membatalkan baris ini,
            # bukan membuat seluruh sesi invalid.
            with db.begin_nested():
                data = _extract_row_data(row, col_map, db)
                action, _ = _upsert_employee(db, pin, data)
            if action == 'created':
                created += 1
            else:
                updated += 1
        except Exception as e:
            errors.append(f"Row {row_idx}: {str(e)}")
            continue
    
    db.commit()

    log_activity(db, current_user.username, "IMPORT_EMPLOYEES", f"Berhasil import {created} karyawan baru ({updated} diperbarui) dari file Excel")
    
    return {
        "status": "success",
        "created": created,
        "updated": updated,
        "errors": len(errors),
        "error_details": errors[:20]
    }


async def _import_employees_csv(file: UploadFile, db: Session, current_user: User):
    """Process CSV file for employee import."""
    import csv
    from codecs import iterdecode
    
    reader = csv.reader(iterdecode(file.file, 'utf-8'))
    
    header_row = None
    for row in reader:
        if row and any(cell.strip() for cell in row):
            header_row = row
            break
    
    if not header_row:
        raise HTTPException(status_code=400, detail="CSV file is empty")
    
    header = [str(h).strip().lower() for h in header_row]
    col_map = _build_column_map(header)
    if 'pin' not in col_map:
        raise HTTPException(status_code=400, detail="Column 'PIN' not found in header row. Required column.")
    
    created = 0
    updated = 0
    errors = []
    
    for row_idx, row in enumerate(reader, start=2):
        if not row or not any(cell.strip() for cell in row):
            continue
        try:
            pin = row[col_map['pin']].strip() if col_map['pin'] < len(row) else None
            if not pin:
                errors.append(f"Row {row_idx}: PIN is empty, skipped")
                continue
            
            # Savepoint per baris: error DB (mis. NIK duplikat) hanya membatalkan baris ini,
            # bukan membuat seluruh sesi invalid.
            with db.begin_nested():
                data = _extract_row_data(row, col_map, db)
                action, _ = _upsert_employee(db, pin, data)
            if action == 'created':
                created += 1
            else:
                updated += 1
        except Exception as e:
            errors.append(f"Row {row_idx}: {str(e)}")
            continue
    
    db.commit()
    
    log_activity(db, current_user.username, "IMPORT_EMPLOYEES", f"Berhasil import {created} karyawan baru ({updated} diperbarui) dari file CSV")
    
    return {
        "status": "success",
        "created": created,
        "updated": updated,
        "errors": len(errors),
        "error_details": errors[:20]
    }


def _build_column_map(header):
    """Build a mapping from known field names to column indices."""
    aliases = {
        'pin': ['pin'],
        'full_name': ['full name', 'full_name', 'nama lengkap', 'nama', 'name', 'employee name'],
        'nik': ['nik', 'employee id', 'emp id', 'nomor induk'],
        'is_active': ['status', 'is_active', 'active', 'is active'],
        'contract_start': ['contract start', 'contract_start', 'contract_start_date', 'mulai kontrak', 'start date'],
        'contract_end': ['contract end', 'contract_end', 'contract_end_date', 'akhir kontrak', 'end date'],
        'department': ['department', 'dept', 'departemen', 'bagian'],
        'position': ['position', 'jabatan', 'pos', 'job title'],
        'company': ['company', 'perusahaan', 'comp', 'organization'],
    }
    
    col_map = {}
    for field, names in aliases.items():
        for idx, h in enumerate(header):
            if h in names:
                col_map[field] = idx
                break
    return col_map


def _get_cell(row, col_map, field):
    """Safely get a cell value from a row."""
    if field not in col_map:
        return None
    idx = col_map[field]
    if isinstance(row, (list, tuple)):
        if idx >= len(row):
            return None
        val = row[idx]
    else:
        val = row[idx]
    if val is None:
        return None
    return str(val).strip() if val != '' else None


def _extract_row_data(row, col_map, db):
    """Extract employee fields from a row using the column map."""
    full_name = _get_cell(row, col_map, 'full_name')
    nik = _get_cell(row, col_map, 'nik')
    status_val = _get_cell(row, col_map, 'is_active')
    contract_start = _get_cell(row, col_map, 'contract_start')
    contract_end = _get_cell(row, col_map, 'contract_end')
    dept_name = _get_cell(row, col_map, 'department')
    pos_name = _get_cell(row, col_map, 'position')
    comp_name = _get_cell(row, col_map, 'company')

    dept_id, pos_id, comp_id = _resolve_master_data(db, dept_name, pos_name, comp_name)
    
    data = {}
    if full_name:
        data['full_name'] = full_name
    if nik:
        data['nik'] = nik
    if status_val is not None:
        data['is_active'] = _parse_status(status_val)
    if contract_start:
        data['contract_start_date'] = _parse_date(contract_start)
    if contract_end:
        data['contract_end_date'] = _parse_date(contract_end)
    if dept_id is not None:
        data['department_id'] = dept_id
    if pos_id is not None:
        data['position_id'] = pos_id
    if comp_id is not None:
        data['company_id'] = comp_id
    
    return data


@router.post("/", response_model=EmployeeSchema, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_operator)])
def create_employee(
    employee: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_emp = db.query(Employee).filter(Employee.pin == employee.pin).first()
    if db_emp:
        raise HTTPException(status_code=400, detail="PIN already registered")
    
    new_emp = Employee(**employee.model_dump(exclude={"device_access_ids"}))
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)
    
    if employee.device_access_ids is not None:
        for did in employee.device_access_ids:
            new_eda = EmployeeDeviceAccess(employee_pin=new_emp.pin, device_id=did, sync_status="PENDING_ADD")
            db.add(new_eda)
        db.commit()
        db.refresh(new_emp)
        
    log_activity(db, current_user.username, "CREATE_EMPLOYEE", f"Menambahkan karyawan baru: {new_emp.full_name}")
        
    return new_emp

_CHANGE_LABELS = {
    'pin': 'PIN', 'full_name': 'Nama', 'nik': 'NIK', 'rfid': 'RFID', 'birth_date': 'Tgl lahir',
    'department_id': 'Departemen', 'position_id': 'Jabatan', 'company_id': 'Perusahaan',
    'join_date': 'Tgl masuk', 'contract_start_date': 'Mulai kontrak', 'contract_end_date': 'Akhir kontrak',
    'is_active': 'Status',
}
_CHANGE_MODELS = {'department_id': Department, 'position_id': Position, 'company_id': Company}


def _describe_changes(db: Session, emp: Employee, update_data: dict) -> str:
    """Ringkasan 'Field: lama -> baru' untuk log aktivitas (dipanggil sebelum nilai diubah)."""
    def show(field, value):
        if value is None or value == '':
            return '-'
        if field in _CHANGE_MODELS:
            obj = db.get(_CHANGE_MODELS[field], value)
            return obj.name if obj else str(value)
        if field == 'is_active':
            return 'aktif' if value else 'nonaktif'
        return str(value)

    parts = []
    for field, new in update_data.items():
        old = getattr(emp, field, None)
        if field in _CHANGE_LABELS and old != new:
            parts.append(f"{_CHANGE_LABELS[field]}: {show(field, old)} -> {show(field, new)}")
    return '; '.join(parts) or 'tanpa perubahan data'


def _update_employee(employee_id: int, employee: EmployeeUpdate, db: Session, current_user: User) -> Employee:
    db_emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    was_active, old_name, old_pin = db_emp.is_active, db_emp.full_name, db_emp.pin
    # Muat baris antrean sebelum PIN berubah: relasinya terhubung lewat PIN
    list(db_emp.device_accesses)
    update_data = employee.model_dump(exclude_unset=True, exclude={"device_access_ids"})
    changes = _describe_changes(db, db_emp, update_data)
    for key, value in update_data.items():
        setattr(db_emp, key, value)

    note = device_sync_service.after_employee_update(db, db_emp, was_active, old_name, old_pin, employee.device_access_ids)
    if note:
        changes = f"{changes}; {note}"

    db.commit()
    db.refresh(db_emp)

    log_activity(db, current_user.username, "UPDATE_EMPLOYEE", f"Mengubah data karyawan {db_emp.full_name} (PIN {db_emp.pin}): {changes}")

    return db_emp


@router.patch("/{employee_id}", response_model=EmployeeSchema, dependencies=[Depends(require_operator)])
def update_employee(
    employee_id: int,
    employee: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return _update_employee(employee_id, employee, db, current_user)


@router.put("/{employee_id}", response_model=EmployeeSchema, dependencies=[Depends(require_operator)])
def update_employee_json(
    employee_id: int,
    employee: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return _update_employee(employee_id, employee, db, current_user)

@router.post("/{employee_id}/photo", response_model=EmployeeSchema, dependencies=[Depends(require_operator)])
def upload_employee_photo(
    employee_id: int,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    try:
        photo_path = save_photo(photo, employee_id)
        db_emp.photo_path = photo_path
        db.commit()
        db.refresh(db_emp)
        log_activity(db, current_user.username, "UPDATE_EMPLOYEE_PHOTO", f"Mengunggah foto karyawan: {db_emp.full_name}")
        return db_emp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

HAS_SCANS_MSG = ("punya riwayat scan absensi sehingga tidak bisa dihapus. Untuk karyawan yang keluar, "
                 "nonaktifkan saja: riwayat absensinya tetap tersimpan.")


def _scan_counts(db: Session, pins: List[str]) -> Dict[str, int]:
    rows = db.query(AttendanceLog.employee_pin, func.count(AttendanceLog.id)).filter(
        AttendanceLog.employee_pin.in_(pins)).group_by(AttendanceLog.employee_pin).all()
    return {pin: n for pin, n in rows}


def _schedule_device_delete(db: Session, background_tasks: BackgroundTasks, pins: List[str]) -> None:
    cloud_ids = [d.cloud_id for d in db.query(Device.cloud_id).filter(Device.is_active.is_(True)).all()]
    if pins and cloud_ids:
        background_tasks.add_task(sync_engine.delete_pins_from_devices, pins, cloud_ids)


@router.delete("/{employee_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_administrator)])
def delete_employee(
    employee_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Hapus permanen karyawan yang TIDAK punya scan (mis. salah input). Riwayat absensi tidak pernah ikut
    dihapus; karyawan yang sudah punya scan cukup dinonaktifkan."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")

    pin = emp.pin
    name = emp.full_name
    scans = _scan_counts(db, [pin]).get(pin, 0)
    if scans:
        raise HTTPException(status_code=409, detail=f"{name} {HAS_SCANS_MSG} ({scans} scan)")

    db.query(EmployeeDeviceAccess).filter(EmployeeDeviceAccess.employee_pin == pin).delete(synchronize_session=False)
    db.delete(emp)
    db.commit()
    _schedule_device_delete(db, background_tasks, [pin])

    log_activity(db, current_user.username, "DELETE_EMPLOYEE",
                 f"Menghapus karyawan permanen (tanpa riwayat scan): {name} (PIN: {pin})")
    return {"success": True, "message": f"Karyawan {name} (PIN: {pin}) dihapus permanen."}

@router.post("/bulk-status", status_code=status.HTTP_200_OK, dependencies=[Depends(require_operator)])
def bulk_update_employee_status(
    payload: BulkEmployeeStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Bulk update active status for selected employees."""
    if not payload.employee_ids:
        raise HTTPException(status_code=400, detail="Tidak ada karyawan yang dipilih")

    employees = db.query(Employee).filter(Employee.id.in_(payload.employee_ids)).all()
    if not employees:
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")

    pins = [e.pin for e in employees]
    changed_pins = [e.pin for e in employees if e.is_active != payload.is_active]
    for emp in employees:
        emp.is_active = payload.is_active

    # Hanya yang statusnya benar-benar berubah; dinonaktifkan = hapus, diaktifkan kembali = kirim lagi
    device_sync_service.queue_on_all_devices(
        db, changed_pins, device_sync_service.ADD if payload.is_active else device_sync_service.REMOVE)

    db.commit()

    status_str = "Aktif" if payload.is_active else "Nonaktif"
    log_activity(
        db,
        current_user.username,
        "BULK_UPDATE_EMPLOYEE_STATUS",
        f"Mengubah status {len(employees)} karyawan menjadi {status_str} (PIN: {', '.join(pins[:10])}{'...' if len(pins) > 10 else ''})"
    )

    return {
        "success": True,
        "updated_count": len(employees),
        "message": f"Berhasil mengubah status {len(employees)} karyawan menjadi {status_str}."
    }

@router.post("/bulk-delete", status_code=status.HTTP_200_OK, dependencies=[Depends(require_administrator)])
def bulk_delete_employees(
    payload: BulkEmployeeDeleteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Hapus permanen karyawan terpilih yang TIDAK punya scan. Yang punya scan dilewati (nonaktifkan saja);
    riwayat absensi tidak pernah ikut dihapus."""
    if not payload.employee_ids:
        raise HTTPException(status_code=400, detail="Tidak ada karyawan yang dipilih")

    employees = db.query(Employee).filter(Employee.id.in_(payload.employee_ids)).all()
    if not employees:
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")

    scans = _scan_counts(db, [e.pin for e in employees])
    deletable = [e for e in employees if not scans.get(e.pin)]
    skipped = [e for e in employees if scans.get(e.pin)]
    pins = [e.pin for e in deletable]

    if deletable:
        db.query(EmployeeDeviceAccess).filter(EmployeeDeviceAccess.employee_pin.in_(pins)).delete(synchronize_session=False)
        db.query(Employee).filter(Employee.id.in_([e.id for e in deletable])).delete(synchronize_session=False)
        db.commit()
        _schedule_device_delete(db, background_tasks, pins)
        log_activity(db, current_user.username, "BULK_DELETE_EMPLOYEES",
                     f"Menghapus {len(deletable)} karyawan permanen tanpa riwayat scan "
                     f"(PIN: {', '.join(pins[:10])}{'...' if len(pins) > 10 else ''}); {len(skipped)} dilewati karena punya scan")

    message = f"{len(deletable)} karyawan dihapus permanen."
    if skipped:
        names = ", ".join(e.full_name or e.pin for e in skipped[:5]) + ("..." if len(skipped) > 5 else "")
        message += (f" {len(skipped)} karyawan tidak dihapus karena punya riwayat scan ({names}); "
                    "nonaktifkan saja agar riwayat absensinya tetap tersimpan.")
    return {
        "success": True,
        "deleted_count": len(deletable),
        "skipped_count": len(skipped),
        "skipped": [{"id": e.id, "pin": e.pin, "nama": e.full_name, "scan": scans[e.pin]} for e in skipped],
        "message": message,
    }
