import io
from datetime import datetime

import openpyxl

from app.core.excel_utils import read_excel_rows
from app.core.timezone import LOCAL_TZ
from app.models.attendance import AttendanceLog
from app.models.employee import Employee

HEADER = ["Tanggal scan", "Tanggal", "Jam", "PIN", "NIP", "Nama", "Perusahaan", "Jabatan",
          "Penempatan", "Verifikasi", "I/O", "Workcode", "SN", "Mesin"]


def _export_like_xlsx(rows):
    """Meniru export scan log Fingerspot: baris pertama kosong, header di baris ke-2."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None] * len(HEADER))
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_skips_scan_already_received_via_webhook_with_other_sn(client, db_session):
    db_session.add(Employee(pin="2001", full_name="Andi", is_active=True))
    # Webhook menyimpan cloud_id sebagai device_sn
    db_session.add(AttendanceLog(
        employee_pin="2001", device_sn="CLOUD_OK", source="REALTIME",
        scan_time=LOCAL_TZ.localize(datetime(2026, 8, 1, 8, 0, 12))
    ))
    db_session.commit()

    content = _export_like_xlsx([
        ["01-08-2026 08:00:12", "01-08-2026", "08:00:12", "2001", "N-2001", "Andi", "PT A", "Staf", "Produksi", 1, 1, 0, "SN0001", "Mesin 1"],
        ["01-08-2026 17:01:00", "01-08-2026", "17:01:00", "2001", "N-2001", "Andi", "PT A", "Staf", "Produksi", 1, 1, 0, "SN0001", "Mesin 1"],
    ])
    res = client.post("/attendance/import", files={"file": ("scan.xlsx", content, "application/octet-stream")})
    assert res.status_code == 200
    body = res.json()
    assert body["errors"] == 0 and body["total_processed"] == 2
    assert body["new_records"] == 1  # hanya scan pulang yang baru

    logs = db_session.query(AttendanceLog).filter_by(employee_pin="2001").all()
    assert len(logs) == 2
    assert {l.source for l in logs} == {"REALTIME", "IMPORTED"}


def test_read_excel_rows_xlsx_keeps_values():
    content = _export_like_xlsx([["01-08-2026 08:00:12", "01-08-2026", "08:00:12", "1", "EMP-001", "Budi"]])
    rows = read_excel_rows(content, "scan.xlsx")
    assert rows[1][:4] == ["Tanggal scan", "Tanggal", "Jam", "PIN"]
    assert rows[2][3] == "1" and rows[2][4] == "EMP-001"


def test_import_rejects_corrupt_xls_with_clear_message(client):
    res = client.post("/attendance/import", files={"file": ("rusak.xls", b"bukan file excel", "application/octet-stream")})
    assert res.status_code == 400
    assert "65.536 baris" in res.json()["detail"]


def test_import_warns_when_file_hits_xls_row_limit(client, monkeypatch):
    from app.core import excel_utils
    from app.routers import attendance as attendance_router
    monkeypatch.setattr(excel_utils, "XLS_MAX_ROWS", 3)
    rows = [HEADER, ["01-08-2026 08:00:12", "01-08-2026", "08:00:12", "3001", "N-3001", "Budi", "PT A", "Staf", "Produksi", 1, 1, 0, "SN1", "Mesin 1"]]
    monkeypatch.setattr(attendance_router, "read_excel_rows", lambda c, f: rows + [[None] * len(HEADER)])
    res = client.post("/attendance/import", files={"file": ("besar.xlsx", b"x", "application/octet-stream")})
    assert res.status_code == 200
    body = res.json()
    assert body["new_records"] == 1
    assert len(body["warnings"]) == 1 and "terpotong" in body["warnings"][0]


def test_import_small_file_has_no_warning(client):
    content = _export_like_xlsx([["01-08-2026 08:00:12", "01-08-2026", "08:00:12", "3002", "N-3002", "Cici", "PT A", "Staf", "Produksi", 1, 1, 0, "SN1", "Mesin 1"]])
    res = client.post("/attendance/import", files={"file": ("kecil.xlsx", content, "application/octet-stream")})
    assert res.status_code == 200 and res.json()["warnings"] == []


def test_attendance_and_employee_import_open_to_operator(client):
    from app.main import app
    from app.dependencies import get_current_user
    from app.models.user import User

    content = _export_like_xlsx([["01-08-2026 08:00:12", "01-08-2026", "08:00:12", "3003", "N-3003", "Dedi", "PT A", "Staf", "Produksi", 1, 1, 0, "SN1", "Mesin 1"]])
    for role, expected in [("operator", 200), ("administrator", 200), ("view-only", 403), ("monitor", 403)]:
        app.dependency_overrides[get_current_user] = lambda r=role: User(id=9, username=f"u_{r}", role=r, is_active=True)
        res = client.post("/attendance/import", files={"file": ("scan.xlsx", content, "application/octet-stream")})
        assert res.status_code == expected, role
        wb = openpyxl.Workbook()
        wb.active.append(["PIN", "Nama", "NIK"])
        wb.active.append([f"77{len(role)}", "Karyawan Uji", None])
        buf = io.BytesIO()
        wb.save(buf)
        res = client.post("/employees/import", files={"file": ("emp.xlsx", buf.getvalue(), "application/octet-stream")})
        assert res.status_code == expected, role
