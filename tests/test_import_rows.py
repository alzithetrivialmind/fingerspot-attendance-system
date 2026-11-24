from app.models.device import Device
from app.models.employee import Employee
from app.models.employee_device_access import EmployeeDeviceAccess
from app.models.trans_log import FingerspotTransLog


def test_webhook_set_userinfo_confirmation_marks_synced(client, db_session):
    device = Device(name="Mesin Uji", cloud_id="CLOUD_TEST")
    db_session.add(device)
    db_session.add(Employee(pin="555", full_name="Karyawan Sync", is_active=True))
    db_session.commit()
    db_session.add(EmployeeDeviceAccess(employee_pin="555", device_id=device.id, sync_status="PENDING_ADD"))
    db_session.add(FingerspotTransLog(
        trans_id="trans-555", cloud_id="CLOUD_TEST", action_type="set_userinfo",
        request_payload={"pin": "555", "name": "Karyawan Sync"}
    ))
    db_session.commit()

    res = client.post("/webhook/fingerspot", json={
        "type": "set_userinfo", "cloud_id": "CLOUD_TEST", "trans_id": "trans-555", "data": {}
    })
    assert res.status_code == 200

    db_session.expire_all()
    eda = db_session.query(EmployeeDeviceAccess).filter_by(employee_pin="555").one()
    assert eda.sync_status == "SYNCED"
    assert eda.last_sync_time is not None
    trans = db_session.query(FingerspotTransLog).filter_by(trans_id="trans-555").one()
    assert trans.status == "SUCCESS"


def test_import_attendance_skips_in_file_duplicates_and_bad_rows(client):
    csv_content = """Tanggal scan,Tanggal,Jam,PIN,NIP,Nama,Perusahaan,Jabatan,Penempatan,Verifikasi,I/O,Workcode,SN,Mesin
"01-08-2026 08:00:12","01-08-2026","08:00:12","2001","N-2001","Andi","PT A","Staf","Produksi",1,1,0,"SN1","M1"
"01-08-2026 08:00:12","01-08-2026","08:00:12","2001","N-2001","Andi","PT A","Staf","Produksi",1,1,0,"SN1","M1"
"bukan-tanggal","01-08-2026","08:00:12","2001","N-2001","Andi","PT A","Staf","Produksi",1,1,0,"SN1","M1"
"01-08-2026 17:01:00","01-08-2026","17:01:00","2001","N-2001","Andi","PT A","Staf","Produksi",1,1,0,"SN1","M1"
"""
    res = client.post("/attendance/import", files={"file": ("dup.csv", csv_content.encode(), "text/csv")})
    assert res.status_code == 200
    data = res.json()
    assert data["new_records"] == 2
    assert data["errors"] == 1

    res_get = client.get("/attendance/?employee_pin=2001")
    assert res_get.json()["total"] == 2


def test_import_employees_duplicate_nik_does_not_abort_import(client):
    csv_content = """PIN,Full Name,NIK
3001,Satu,NIK-SAMA
3002,Dua,NIK-SAMA
3003,Tiga,NIK-3003
"""
    res = client.post("/employees/import", files={"file": ("emp.csv", csv_content.encode(), "text/csv")})
    assert res.status_code == 200
    data = res.json()
    assert data["created"] == 2
    assert data["errors"] == 1

    pins = {e["pin"] for e in client.get("/employees/?limit=100").json()["data"]}
    assert {"3001", "3003"} <= pins
    assert "3002" not in pins
