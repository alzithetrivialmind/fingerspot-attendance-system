from app.models.activity_log import ActivityLog
from app.models.department import Department
from app.models.employee import Employee


def _logs(db, action):
    return db.query(ActivityLog).filter_by(action=action).all()


def test_list_filters_and_paginates(client, db_session):
    for i in range(5):
        db_session.add(ActivityLog(username="budi", action="LOGIN", details=f"login {i}"))
    db_session.add(ActivityLog(username="sari", action="IMPORT_ATTENDANCE", details="Import absensi (scan.xls)"))
    db_session.commit()

    body = client.get("/activity-logs/?limit=2").json()
    assert body["total"] == 6 and body["total_pages"] == 3 and len(body["data"]) == 2

    body = client.get("/activity-logs/?category=absensi").json()
    assert [d["username"] for d in body["data"]] == ["sari"]
    assert client.get("/activity-logs/?username=budi").json()["total"] == 5
    assert client.get("/activity-logs/?search=scan.xls").json()["total"] == 1
    assert client.get("/activity-logs/users").json() == ["budi", "sari"]


def test_employee_update_logs_old_and_new_values(client, db_session):
    db_session.add_all([Department(id=1, name="IT"), Department(id=2, name="HR")])
    db_session.add(Employee(id=1, pin="701", full_name="Andi", nik="20-001", department_id=1, is_active=True))
    db_session.commit()

    res = client.put("/employees/1", json={"nik": "20-099", "department_id": 2, "full_name": "Andi"})
    assert res.status_code == 200
    detail = _logs(db_session, "UPDATE_EMPLOYEE")[-1].details
    assert "NIK: 20-001 -> 20-099" in detail and "Departemen: IT -> HR" in detail
    assert "Nama" not in detail  # nilai sama tidak dicatat
