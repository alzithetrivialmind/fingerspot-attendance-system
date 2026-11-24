
def test_webhook_attendance(client, webhook_device):
    # 1. Register employees first (as attendance strictly requires registered PIN)
    client.post("/employees/", json={"pin": "1001", "full_name": "Karyawan 1001", "is_active": True})
    client.post("/employees/", json={"pin": "1002", "full_name": "Karyawan 1002", "is_active": True})

    # Simulate a webhook payload from Fingerspot
    payload = {
        "type": "attlog",
        "cloud_id": "CLOUD_OK",
        "data": [
            {
                "pin": "1001",
                "scan": "2026-08-18 08:00:00",
                "verify": 1,
                "status_scan": 0,
                "sn": "SN12345"
            },
            {
                "pin": "1002",
                "scan": "2026-08-18 08:15:00",
                "verify": 1,
                "status_scan": 0,
                "sn": "SN12345"
            }
        ]
    }
    
    response = client.post("/webhook/fingerspot", json=payload)
    assert response.status_code == 200
    
    # Check if attendance is saved
    response_get = client.get("/attendance/")
    assert response_get.status_code == 200
    data = response_get.json()
    assert len(data["data"]) == 2
    
    # Simulate duplicate webhook (should ignore gracefully)
    response_dup = client.post("/webhook/fingerspot", json=payload)
    assert response_dup.status_code == 200 # Still returns 200 so Cloud stops retrying
    
    # Verify no duplicates were added
    response_get_after = client.get("/attendance/")
    data_after = response_get_after.json()
    assert len(data_after["data"]) == 2

def test_import_attendance_csv(client):
    csv_content = """DateTime,Date,Time,ID,PIN,Name,Company,Position,Dept,verify_mode,io_mode,status,SN,Device Name
"2026-01-23 07:15:00","2026-01-23","07:15:00","1","1001","Budi","A","Staff","IT","Face","In","Valid","SN999","Main Door"
"2026-01-23 17:05:00","2026-01-23","17:05:00","1","1001","Budi","A","Staff","IT","Face","Out","Valid","SN999","Main Door"
"""
    file_bytes = csv_content.encode("utf-8")
    response = client.post(
        "/attendance/import",
        files={"file": ("test.csv", file_bytes, "text/csv")}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_processed"] == 2
    
    # Verify data in DB
    response_get = client.get("/attendance/")
    data_db = response_get.json()
    assert len(data_db["data"]) == 2
    assert data_db["data"][0]["employee_pin"] == "1001"
