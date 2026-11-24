def test_create_and_list_employee(client):
    # Setup master data first
    dept = client.post("/master-data/departments", json={"name": "IT"}).json()
    pos = client.post("/master-data/positions", json={"name": "Staff"}).json()
    comp = client.post("/master-data/companies", json={"name": "Company A"}).json()
    
    # Create an employee
    employee_data = {
        "pin": "1001",
        "nik": "EMP-1001",
        "full_name": "Budi Santoso",
        "department_id": dept["id"],
        "position_id": pos["id"],
        "company_id": comp["id"]
    }
    
    response = client.post("/employees/", json=employee_data)
    assert response.status_code == 201
    data = response.json()
    assert data["pin"] == "1001"
    assert data["full_name"] == "Budi Santoso"
    
    # Check if duplicate PIN is rejected
    response2 = client.post("/employees/", json=employee_data)
    assert response2.status_code == 400
    assert "already registered" in response2.json()["detail"]
    
    # List employees
    response_list = client.get("/employees/")
    assert response_list.status_code == 200
    res_json = response_list.json()
    assert res_json["total"] == 1
    assert len(res_json["data"]) == 1
    assert res_json["data"][0]["full_name"] == "Budi Santoso"

    # Update employee via PUT
    emp_id = data["id"]
    update_data = {
        "full_name": "Budi Santoso Updated",
        "nik": "EMP-1001-REV"
    }
    response_update = client.put(f"/employees/{emp_id}", json=update_data)
    assert response_update.status_code == 200
    updated_emp = response_update.json()
    assert updated_emp["full_name"] == "Budi Santoso Updated"
    assert updated_emp["nik"] == "EMP-1001-REV"

    # Update employee via PATCH (json body)
    response_patch = client.patch(f"/employees/{emp_id}", json={"full_name": "Budi Santoso Final"})
    assert response_patch.status_code == 200
    assert response_patch.json()["full_name"] == "Budi Santoso Final"


def test_employee_import_template_and_import(client):
    import io
    import openpyxl

    # Test template download
    res_template = client.get("/employees/import/template")
    assert res_template.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res_template.headers["content-type"]

    # Test import via Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["PIN", "Full Name", "NIK", "Status", "Contract Start", "Contract End", "Department", "Position", "Company"])
    ws.append(["2001", "Siti Aminah", "NIK-2001", "Active", "2024-01-01", "2025-01-01", "Finance", "Manager", "PT ABC"])
    ws.append(["2002", "Dedi Kurniawan", "NIK-2002", "Inactive", "2023-01-01", "2024-01-01", "Operations", "Supervisor", "PT ABC"])

    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)

    files = {
        "file": ("employees_test.xlsx", excel_buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    res_import = client.post("/employees/import", files=files)
    assert res_import.status_code == 200
    import_data = res_import.json()
    assert import_data["status"] == "success"
    assert import_data["created"] == 2

    # Test import via CSV
    csv_content = (
        "PIN,Full Name,NIK,Status,Department,Position,Company\n"
        "2001,Siti Aminah Rev,NIK-2001-REV,Active,Finance,Senior Manager,PT ABC\n"
        "2003,Eko Prasetyo,NIK-2003,Active,IT,Staff,PT ABC\n"
    )
    files_csv = {
        "file": ("employees_test.csv", csv_content.encode("utf-8"), "text/csv")
    }
    res_csv = client.post("/employees/import", files=files_csv)
    assert res_csv.status_code == 200
    csv_data = res_csv.json()
    assert csv_data["status"] == "success"
    assert csv_data["created"] == 1  # 2003 created
    assert csv_data["updated"] == 1  # 2001 updated

    # Test export employees and verify names instead of IDs
    res_export = client.get("/employees/export")
    assert res_export.status_code == 200
    export_wb = openpyxl.load_workbook(io.BytesIO(res_export.content))
    export_ws = export_wb.active
    rows = list(export_ws.iter_rows(values_only=True))
    assert rows[0] == ("ID", "PIN", "NIK", "Full Name", "Birth Date", "Join Date", "Contract Start", "Contract End", "Department", "Position", "Company", "Status")
    
    # Check that Department is "Finance", Position is "Senior Manager", Company is "PT ABC" for PIN 2001
    pin_2001_row = next((r for r in rows[1:] if r[1] == "2001"), None)
    assert pin_2001_row is not None
    assert pin_2001_row[8] == "Finance"
    assert pin_2001_row[9] == "Senior Manager"
    assert pin_2001_row[10] == "PT ABC"
    assert pin_2001_row[11] == "Active"

def test_delete_employee_keeps_attendance(client, webhook_device):
    """Karyawan yang punya scan tidak bisa dihapus (nonaktifkan saja); yang tanpa scan bisa."""
    with_scan = client.post("/employees/", json={"pin": "5555", "full_name": "Punya Scan", "nik": "NIK-5555",
                                                 "is_active": True}).json()["id"]
    no_scan = client.post("/employees/", json={"pin": "5556", "full_name": "Salah Input", "nik": "NIK-5556",
                                               "is_active": True}).json()["id"]
    scan = {"pin": "5555", "scan": "2026-08-14 08:00:00", "verify": 1, "status_scan": 0}
    assert client.post("/webhook/fingerspot", json={"type": "attlog", "cloud_id": "CLOUD_OK", "data": [scan]}).status_code == 200

    res = client.delete(f"/employees/{with_scan}")
    assert res.status_code == 409 and "nonaktifkan" in res.json()["detail"]
    assert len(client.get("/attendance/?employee_pin=5555").json()["data"]) == 1  # riwayat tetap ada

    res = client.delete(f"/employees/{no_scan}")
    assert res.status_code == 200 and res.json()["success"] is True
    assert "5556" not in [e["pin"] for e in client.get("/employees/").json()["data"]]

    # Scan dengan PIN yang sudah dihapus tetap ditolak
    scan2 = {**scan, "pin": "5556"}
    client.post("/webhook/fingerspot", json={"type": "attlog", "cloud_id": "CLOUD_OK", "data": [scan2]})
    assert client.get("/attendance/?employee_pin=5556").json()["data"] == []

def test_bulk_employee_status_and_delete(client, webhook_device):
    # 1. Create multiple employees
    res1 = client.post("/employees/", json={"pin": "7001", "full_name": "Bulk 1", "is_active": True})
    res2 = client.post("/employees/", json={"pin": "7002", "full_name": "Bulk 2", "is_active": True})
    assert res1.status_code == 201
    assert res2.status_code == 201
    id1 = res1.json()["id"]
    id2 = res2.json()["id"]

    # 2. Bulk deactivate
    bulk_status_res = client.post("/employees/bulk-status", json={
        "employee_ids": [id1, id2],
        "is_active": False
    })
    assert bulk_status_res.status_code == 200
    assert bulk_status_res.json()["updated_count"] == 2

    # Verify both are inactive
    emp_list = client.get("/employees/?is_active=false").json()["data"]
    inactive_pins = [e["pin"] for e in emp_list]
    assert "7001" in inactive_pins
    assert "7002" in inactive_pins

    # 3. Bulk activate
    bulk_status_res2 = client.post("/employees/bulk-status", json={
        "employee_ids": [id1, id2],
        "is_active": True
    })
    assert bulk_status_res2.status_code == 200
    assert bulk_status_res2.json()["updated_count"] == 2

    # 4. Hanya 7001 punya scan
    client.post("/webhook/fingerspot", json={
        "type": "attlog", "cloud_id": "CLOUD_OK",
        "data": [{"pin": "7001", "scan": "2026-08-14 08:00:00", "verify": 1, "status_scan": 0, "sn": "SN01"}]
    })

    # 5. Bulk delete: yang punya scan dilewati, riwayatnya tetap ada
    body = client.post("/employees/bulk-delete", json={"employee_ids": [id1, id2]}).json()
    assert body["deleted_count"] == 1 and body["skipped_count"] == 1 and body["skipped"][0]["pin"] == "7001"
    pins = [e["pin"] for e in client.get("/employees/").json()["data"]]
    assert "7001" in pins and "7002" not in pins
    assert len(client.get("/attendance/?employee_pin=7001").json()["data"]) == 1


