from app.models.employee_device_access import EmployeeDeviceAccess

def test_devices_crud_and_push_employees(client, db_session):
    # 1. Create a device
    res_dev = client.post("/devices/", json={
        "name": "Mesin Uji",
        "cloud_id": "TEST_CLOUD_001",
        "is_active": True
    })
    assert res_dev.status_code == 200
    device_id = res_dev.json()["id"]

    # 2. Get list of devices
    res_list = client.get("/devices/")
    assert res_list.status_code == 200
    assert any(d["cloud_id"] == "TEST_CLOUD_001" for d in res_list.json())

    # 3. Create employee
    res_emp = client.post("/employees/", json={
        "pin": "7788",
        "full_name": "Karyawan Push Test",
        "is_active": True
    })
    assert res_emp.status_code == 201
    emp_id = res_emp.json()["id"]

    # 4. Push employee to device
    res_push = client.post(f"/devices/{device_id}/push-employees", json={
        "employee_ids": [emp_id]
    })
    assert res_push.status_code == 200
    push_data = res_push.json()
    assert push_data["status"] == "success"
    assert push_data["queued"] == 1

    # Verify EmployeeDeviceAccess is recorded
    access = db_session.query(EmployeeDeviceAccess).filter_by(
        employee_pin="7788",
        device_id=device_id
    ).first()
    assert access is not None
    assert access.sync_status == "PENDING_ADD"
