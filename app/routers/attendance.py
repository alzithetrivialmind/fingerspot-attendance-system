import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from datetime import datetime, date

from app.core.timezone import LOCAL_TZ
from app.dependencies import get_db, get_current_user, require_operator
from app.core.logging_utils import log_activity
from app.core.excel_utils import ExcelReadError, read_excel_rows, is_blank_row, truncation_warning
from app.models.user import User
from app.models.attendance import AttendanceLog
from app.models.employee import Employee
from app.models.device import Device
from app.models.department import Department
from app.models.position import Position
from app.models.company import Company
from app.schemas.attendance import PullAttendanceRequest, FingerspotWebhookItem, PaginatedAttendance
from sqlalchemy import or_, func
import math
import csv

from app.services.fingerspot_api import pull_attendance_log
from app.services.attendance_service import process_webhook_attendance

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/attendance",
    tags=["attendance"],
    dependencies=[Depends(get_current_user)] # Every route needs at least view-only access
)

@router.get("/", response_model=PaginatedAttendance)
def get_attendance(
    employee_pin: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    search: Optional[str] = None,
    department_id: Optional[int] = None,
    position_id: Optional[int] = None,
    company_id: Optional[int] = None,
    source: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(AttendanceLog)
    query = query.outerjoin(Employee, AttendanceLog.employee_pin == Employee.pin)
    
    if employee_pin:
        query = query.filter(AttendanceLog.employee_pin == employee_pin)
    if from_date:
        query = query.filter(AttendanceLog.scan_time >= from_date)
    if to_date:
        query = query.filter(AttendanceLog.scan_time <= to_date)
        
    if search:
        query = query.filter(
            or_(
                Employee.full_name.ilike(f"%{search}%"),
                Employee.pin.ilike(f"%{search}%"),
                Employee.nik.ilike(f"%{search}%"),
                AttendanceLog.device_sn.ilike(f"%{search}%")
            )
        )
        
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if position_id:
        query = query.filter(Employee.position_id == position_id)
    if company_id:
        query = query.filter(Employee.company_id == company_id)
    if source:
        query = query.filter(AttendanceLog.source == source)
        
    total_count = query.count()
    query = query.order_by(
        func.length(AttendanceLog.employee_pin).asc(),
        AttendanceLog.employee_pin.asc(),
        AttendanceLog.scan_time.asc()
    )
    
    offset = (page - 1) * limit
    attendance = query.offset(offset).limit(limit).all()
    total_pages = math.ceil(total_count / limit) if limit > 0 else 1
    
    return {
        "data": attendance,
        "total": total_count,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }

@router.get("/export", dependencies=[Depends(require_operator)])
def export_attendance(
    employee_pin: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    search: Optional[str] = None,
    department_id: Optional[int] = None,
    position_id: Optional[int] = None,
    company_id: Optional[int] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(AttendanceLog)
    query = query.outerjoin(Employee, AttendanceLog.employee_pin == Employee.pin)
    
    if employee_pin:
        query = query.filter(AttendanceLog.employee_pin == employee_pin)
    if from_date:
        query = query.filter(AttendanceLog.scan_time >= from_date)
    if to_date:
        query = query.filter(AttendanceLog.scan_time <= to_date)
        
    if search:
        query = query.filter(
            or_(
                Employee.full_name.ilike(f"%{search}%"),
                Employee.pin.ilike(f"%{search}%"),
                Employee.nik.ilike(f"%{search}%"),
                AttendanceLog.device_sn.ilike(f"%{search}%")
            )
        )
        
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if position_id:
        query = query.filter(Employee.position_id == position_id)
    if company_id:
        query = query.filter(Employee.company_id == company_id)
    if source:
        query = query.filter(AttendanceLog.source == source)
        
    query = query.order_by(
        func.length(AttendanceLog.employee_pin).asc(),
        AttendanceLog.employee_pin.asc(),
        AttendanceLog.scan_time.asc()
    )
    attendance = query.all()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data Presensi"
    
    # Styled Headers
    headers = ["ID Database", "PIN Mesin", "NIP / NIK", "Nama Karyawan", "Waktu Scan", "Verifikasi", "SN Mesin", "Sumber Data"]
    ws.append(headers)
    
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Write data
    for log in attendance:
        emp_name = log.employee.full_name if log.employee else ""
        emp_nik = log.employee.nik if (log.employee and log.employee.nik) else ""
        
        ws.append([
            log.id,
            log.employee_pin,
            emp_nik,
            emp_name,
            log.scan_time.strftime("%Y-%m-%d %H:%M:%S") if log.scan_time else "",
            log.verify_mode,
            log.device_sn,
            log.source or "REALTIME"
        ])
        
    # Auto adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    periode = f" {from_date:%Y-%m-%d} s/d {to_date:%Y-%m-%d}" if from_date and to_date else ""
    log_activity(db, current_user.username, "EXPORT_DATA", f"Unduh data absensi{periode} ({ws.max_row - 1} scan)")
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=attendance_export.xlsx"}
    )

@router.post("/pull", dependencies=[Depends(require_operator)])
async def pull_attendance(request: PullAttendanceRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        s_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        e_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        if (e_date - s_date).days > 2:
            raise HTTPException(status_code=400, detail="Date range cannot exceed 2 days per request")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")

    try:
        response_data = await pull_attendance_log(
            db,
            cloud_id=request.cloud_id,
            start_date=request.start_date,
            end_date=request.end_date
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    if not response_data.get("success"):
        raise HTTPException(status_code=400, detail=response_data.get("message", "API Pull Failed"))
    
    att_data = response_data.get("data", [])
    
    device = db.query(Device).filter(Device.cloud_id == request.cloud_id).first()
    actual_sn = device.sn if (device and device.sn) else request.cloud_id

    processed_count = 0
    errors = []
    for item in att_data:
        try:
            scan_str = item.get("scan_date") or item.get("scan")
            if not scan_str:
                continue
                
            dt = LOCAL_TZ.localize(datetime.strptime(scan_str, "%Y-%m-%d %H:%M:%S"))
            webhook_item = FingerspotWebhookItem(
                pin=str(item.get("pin")),
                scan_time=dt,
                verify_mode=item.get("verify"),
                io_mode=item.get("status_scan") or item.get("io_mode"),
                sn=actual_sn 
            )
            process_webhook_attendance(db, webhook_item, item, source="PULLED")
            processed_count += 1
        except Exception as e:
            errors.append(str(e))
            continue
            
    if errors:
        logger.warning("Tarik scan %s: %s baris dilewati, contoh: %s", request.cloud_id, len(errors), errors[0])

    log_activity(db, current_user.username, "PULL_ATTENDANCE", f"Menarik log dari API, berhasil: {processed_count}, error: {len(errors)}")

    return {"status": "success", "total_pulled": len(att_data), "total_processed": processed_count, "errors": len(errors)}

@router.get("/import/template", dependencies=[Depends(require_operator)])
def download_attendance_import_template(format: str = Query("xlsx", pattern="^(xlsx|csv)$")):
    """Download a real Excel (.xlsx) or CSV template for importing attendance."""
    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        headers = ["Tanggal scan", "Tanggal", "Jam", "PIN", "NIP", "Nama", "Perusahaan", "Jabatan", "Penempatan", "Verifikasi", "I/O", "Workcode", "SN", "Mesin"]
        writer.writerow(headers)
        writer.writerow(["01-08-2026 08:00:12", "01-08-2026", "08:00:12", "1001", "EMP-001", "Budi Santoso", "PT Contoh", "Staf", "IT", 1, 1, 0, "SN0001", "Mesin 1"])
        writer.writerow(["01-08-2026 17:05:00", "01-08-2026", "17:05:00", "1001", "EMP-001", "Budi Santoso", "PT Contoh", "Staf", "IT", 1, 1, 0, "SN0001", "Mesin 1"])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=attendance_import_template.csv"}
        )

    # Excel format (.xlsx)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template Import Absensi"
    
    headers = [
        "Tanggal scan", "Tanggal", "Jam", "PIN", "NIP", "Nama", 
        "Perusahaan", "Jabatan", "Penempatan", "Verifikasi", "I/O", "Workcode", "SN", "Mesin"
    ]
    ws.append(headers)
    
    # Styling Header
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    # Sample Rows
    samples = [
        ["01-08-2026 08:00:12", "01-08-2026", "08:00:12", "1001", "EMP-001", "Budi Santoso", "PT Contoh", "Staf", "IT", 1, 1, 0, "SN0001", "Mesin 1"],
        ["01-08-2026 17:05:00", "01-08-2026", "17:05:00", "1001", "EMP-001", "Budi Santoso", "PT Contoh", "Staf", "IT", 1, 1, 0, "SN0001", "Mesin 1"],
        ["01-08-2026 07:55:30", "01-08-2026", "07:55:30", "1002", "EMP-002", "Siti Aminah", "PT Contoh", "Staf", "HR", 1, 1, 0, "SN0001", "Mesin 1"],
    ]
    for s in samples:
        ws.append(s)
        
    # Set proper column widths
    widths = [22, 14, 12, 10, 16, 22, 26, 22, 22, 12, 10, 12, 20, 20]
    for idx, width in enumerate(widths, start=1):
        col_letter = openpyxl.utils.get_column_letter(idx)
        ws.column_dimensions[col_letter].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=attendance_import_template.xlsx"}
    )

def _parse_scan_time(val):
    if isinstance(val, datetime):
        # If already timezone-aware, convert to LOCAL_TZ; otherwise localize as LOCAL_TZ
        if val.tzinfo is not None:
            return val.astimezone(LOCAL_TZ)
        return LOCAL_TZ.localize(val)
    if isinstance(val, date):
        naive_dt = datetime.combine(val, datetime.min.time())
        return LOCAL_TZ.localize(naive_dt)
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            naive_dt = datetime.strptime(s, fmt)
            return LOCAL_TZ.localize(naive_dt)  # Treat all incoming scan times as LOCAL_TZ
        except ValueError:
            continue
    return None

def _to_int(val, default: int) -> int:
    try:
        return int(float(str(val).strip()))
    except (TypeError, ValueError):
        return default

@router.post("/import", dependencies=[Depends(require_operator)])
async def import_attendance(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    filename = file.filename.lower()
    if not filename.endswith(('.xlsx', '.xls', '.csv', '.txt')):
        raise HTTPException(status_code=400, detail="Only Excel (.xlsx, .xls) and CSV (.csv, .txt) files are supported")
    
    rows_data = []
    warnings = []

    try:
        content = await file.read()
        if filename.endswith(('.xlsx', '.xls')):
            all_rows = read_excel_rows(content, filename)
            warning = truncation_warning(all_rows)
            if warning:
                warnings.append(warning)
            rows_data = [r for r in all_rows if not is_blank_row(r)]
        else:
            text_str = content.decode('utf-8-sig', errors='replace')
            reader = csv.reader(io.StringIO(text_str))
            for r in reader:
                if r and any(c.strip() != '' for c in r):
                    rows_data.append(r)
    except ExcelReadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    if not rows_data or len(rows_data) < 2:
        raise HTTPException(status_code=400, detail="File is empty or contains only header")

    # Header parsing & column index mapping
    raw_header = [str(c).strip().lower().replace('\ufeff', '') for c in rows_data[0]]
    
    def find_col_idx(aliases, default_idx):
        for alias in aliases:
            for i, h in enumerate(raw_header):
                if alias in h:
                    return i
        return default_idx if default_idx < len(raw_header) else None

    idx_scan = find_col_idx(["tanggal scan", "scan time", "datetime", "waktu scan"], 0)
    idx_pin = find_col_idx(["pin"], 3)
    idx_nip = find_col_idx(["nip", "nik", "employee id", "no induk"], 4)
    idx_nama = find_col_idx(["nama", "name", "full name", "employee name"], 5)
    idx_comp = find_col_idx(["perusahaan", "company"], 6)
    idx_pos = find_col_idx(["jabatan", "position"], 7)
    idx_dept = find_col_idx(["penempatan", "departemen", "department", "dept"], 8)
    idx_ver = find_col_idx(["verifikasi", "verify", "verify mode"], 9)
    idx_io = find_col_idx(["i/o", "io mode", "status scan", "status"], 10)
    idx_sn = find_col_idx(["sn", "device sn", "serial number"], 12)
    idx_mesin = find_col_idx(["mesin", "device name", "nama mesin"], 13)

    processed_count = 0
    created_count = 0
    errors = []
    
    # Cache master data & employees in memory for fast batch lookup
    dept_cache = {d.name.lower(): d.id for d in db.query(Department).all()}
    pos_cache = {p.name.lower(): p.id for p in db.query(Position).all()}
    comp_cache = {c.name.lower(): c.id for c in db.query(Company).all()}
    emp_cache = {e.pin: e for e in db.query(Employee).all()}
    # Kunci (pin, scan_time) yang sudah ditambahkan dari file ini. Session memakai
    # autoflush=False, jadi query `existing` di bawah tidak melihat baris pending.
    seen_keys = set()

    for row_idx, row in enumerate(rows_data[1:], start=2):
        # Snapshot cache: jika savepoint baris ini di-rollback, entri baru di cache
        # akan menunjuk ke ID yang tidak pernah tersimpan.
        cache_snapshot = (dict(dept_cache), dict(pos_cache), dict(comp_cache), dict(emp_cache))
        try:
            # continue -> savepoint di-commit; exception -> savepoint di-rollback
            with db.begin_nested():
                scan_val = row[idx_scan] if idx_scan is not None and idx_scan < len(row) else None
                dt = _parse_scan_time(scan_val)
                if not dt:
                    errors.append(f"Row {row_idx}: Format tanggal scan tidak valid '{scan_val}'")
                    continue
                
                pin_raw = row[idx_pin] if idx_pin is not None and idx_pin < len(row) else None
                if not pin_raw or str(pin_raw).strip() == '':
                    errors.append(f"Row {row_idx}: Kolom PIN kosong")
                    continue
                pin = str(pin_raw).strip()
            
                nip = str(row[idx_nip]).strip() if (idx_nip is not None and idx_nip < len(row) and row[idx_nip] is not None) else None
                nama = str(row[idx_nama]).strip() if (idx_nama is not None and idx_nama < len(row) and row[idx_nama] is not None) else None
                comp_name = str(row[idx_comp]).strip() if (idx_comp is not None and idx_comp < len(row) and row[idx_comp] is not None) else None
                pos_name = str(row[idx_pos]).strip() if (idx_pos is not None and idx_pos < len(row) and row[idx_pos] is not None) else None
                dept_name = str(row[idx_dept]).strip() if (idx_dept is not None and idx_dept < len(row) and row[idx_dept] is not None) else None
            
                # Resolve Master Data
                dept_id = None
                if dept_name:
                    d_key = dept_name.lower()
                    if d_key not in dept_cache:
                        new_d = Department(name=dept_name)
                        db.add(new_d)
                        db.flush()
                        dept_cache[d_key] = new_d.id
                    dept_id = dept_cache[d_key]

                pos_id = None
                if pos_name:
                    p_key = pos_name.lower()
                    if p_key not in pos_cache:
                        new_p = Position(name=pos_name)
                        db.add(new_p)
                        db.flush()
                        pos_cache[p_key] = new_p.id
                    pos_id = pos_cache[p_key]

                comp_id = None
                if comp_name:
                    c_key = comp_name.lower()
                    if c_key not in comp_cache:
                        new_c = Company(name=comp_name)
                        db.add(new_c)
                        db.flush()
                        comp_cache[c_key] = new_c.id
                    comp_id = comp_cache[c_key]

                # Upsert / Link Employee
                if pin in emp_cache:
                    emp = emp_cache[pin]
                    if nama and (not emp.full_name or emp.full_name.startswith("Karyawan PIN")):
                        emp.full_name = nama
                    if nip and not emp.nik:
                        emp.nik = nip
                    if dept_id and not emp.department_id:
                        emp.department_id = dept_id
                    if pos_id and not emp.position_id:
                        emp.position_id = pos_id
                    if comp_id and not emp.company_id:
                        emp.company_id = comp_id
                else:
                    emp = Employee(
                        pin=pin,
                        full_name=nama or f"Karyawan PIN {pin}",
                        nik=nip,
                        department_id=dept_id,
                        position_id=pos_id,
                        company_id=comp_id,
                        is_active=True
                    )
                    db.add(emp)
                    db.flush()
                    emp_cache[pin] = emp

                # Verify & IO mode
                ver_raw = row[idx_ver] if idx_ver is not None and idx_ver < len(row) else 1
                io_raw = row[idx_io] if idx_io is not None and idx_io < len(row) else 0
            
                # Export .xls Fingerspot menyimpan angka sebagai teks "30.0"
                verify_mode = _to_int(ver_raw, 1)
                io_mode = _to_int(io_raw, 0)
                
                sn_raw = row[idx_sn] if idx_sn is not None and idx_sn < len(row) else "IMPORTED"
                sn = str(sn_raw).strip() if sn_raw else "IMPORTED"
                mesin_name = str(row[idx_mesin]).strip() if (idx_mesin is not None and idx_mesin < len(row) and row[idx_mesin]) else ""

                # Dedup per (PIN, waktu scan) lintas mesin/sumber, sama seperti webhook:
                # webhook menyimpan cloud_id sebagai device_sn, export file memakai SN mesin,
                # jadi scan yang sama punya device_sn berbeda.
                key = (pin, dt)
                existing = key in seen_keys or db.query(AttendanceLog).filter(
                    AttendanceLog.employee_pin == pin,
                    AttendanceLog.scan_time == dt
                ).first()

                if not existing:
                    new_log = AttendanceLog(
                        employee_pin=pin,
                        device_sn=sn,
                        scan_time=dt,
                        verify_mode=verify_mode,
                        io_mode=io_mode,
                        department_id_snapshot=dept_id or emp.department_id,
                        source="IMPORTED",
                        raw_payload={
                            "source": "IMPORTED",
                            "file": file.filename,
                            "nip": nip,
                            "nama": nama,
                            "mesin": mesin_name
                        }
                    )
                    db.add(new_log)
                    db.flush()
                    seen_keys.add(key)
                    created_count += 1

                processed_count += 1

            # Commit in batches (di luar savepoint)
            if processed_count % 1000 == 0:
                db.commit()

        except Exception as e:
            dept_cache, pos_cache, comp_cache, emp_cache = cache_snapshot
            errors.append(f"Row {row_idx}: {str(e)}")
            continue

    db.commit()
    log_activity(db, current_user.username, "IMPORT_ATTENDANCE", f"Import absensi ({file.filename}): total {processed_count}, baru {created_count}, gagal {len(errors)}")

    return {
        "status": "success",
        "total_processed": processed_count,
        "new_records": created_count,
        "errors": len(errors),
        "error_details": errors[:10],
        "warnings": warnings
    }
