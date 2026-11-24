"""Feed scan realtime untuk layar monitor (halaman /monitor).

Webhook attlog memanggil record_scan() untuk SETIAP scan, termasuk PIN yang tidak terdaftar
(scan itu tidak disimpan ke attendance_logs, tapi petugas tetap perlu melihat bahwa orangnya
sudah tap dan PIN-nya belum terdaftar). Feed disimpan di memori: aplikasi berjalan dengan satu
proses uvicorn. Setelah restart, feed diisi ulang dari scan REALTIME hari ini di database.
"""
import threading
from collections import deque
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.core.timezone import LOCAL_TZ
from app.models.attendance import AttendanceLog
from app.models.device import Device
from app.models.employee import Employee


MAX_EVENTS = 2000
# Scan kedua oleh PIN yang sama dalam jarak ini ditandai "scan ulang" (bukan orang lain).
REPEAT_WINDOW = timedelta(minutes=5)

# Kode verifikasi mesin Fingerspot (field "verify" pada webhook attlog).
VERIFY_LABELS = {1: "Sidik jari", 2: "Password", 3: "Kartu", 4: "Wajah", 5: "GPS", 6: "Vena"}

_lock = threading.Lock()
_events: deque = deque(maxlen=MAX_EVENTS)
_seq = 0
_seeded = False


def _now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _to_local(dt: datetime) -> datetime:
    # Webhook mengirim jam mesin tanpa zona waktu; mesin diset ke zona waktu setempat.
    if dt.tzinfo is None:
        return LOCAL_TZ.localize(dt)
    return dt.astimezone(LOCAL_TZ)


def _employee_info(emp: Employee | None) -> dict:
    if not emp:
        return {"registered": False, "name": None, "nik": None, "department": None,
                "position": None, "company": None, "active": None}
    return {
        "registered": True,
        "name": emp.full_name,
        "nik": emp.nik,
        "department": emp.department.name if emp.department else None,
        "position": emp.position.name if emp.position else None,
        "company": emp.company.name if emp.company else None,
        "active": bool(emp.is_active),
    }


def _append(cloud_id: str, pin: str, scan_time: datetime, verify_mode, info: dict,
            received_at: datetime | None) -> dict | None:
    """Tambah satu kejadian ke feed. Kiriman ulang webhook (PIN + waktu sama) diabaikan."""
    global _seq
    scan_time = _to_local(scan_time)
    with _lock:
        repeat_of = None
        for ev in reversed(_events):
            if ev["pin"] != pin:
                continue
            if ev["_scan"] == scan_time:
                return None
            if timedelta(0) < scan_time - ev["_scan"] <= REPEAT_WINDOW:
                repeat_of = ev["seq"]
            break
        _seq += 1
        event = {
            "seq": _seq,
            "_scan": scan_time,
            "cloud_id": cloud_id,
            "pin": pin,
            "scan_time": scan_time.isoformat(),
            "received_at": received_at.isoformat() if received_at else None,
            # Jeda mesin → server; besar berarti data cloud terlambat (antrian/internet mesin).
            "lag_seconds": round((received_at - scan_time).total_seconds()) if received_at else None,
            "verify_mode": verify_mode,
            "verify_label": VERIFY_LABELS.get(verify_mode) if verify_mode is not None else None,
            "repeat": repeat_of is not None,
            **info,
        }
        _events.append(event)
        return event


def record_scan(db: Session, cloud_id: str, pin: str, scan_time: datetime, verify_mode=None) -> dict | None:
    _seed_from_db(db)
    pin = str(pin).strip()
    emp = (db.query(Employee)
           .options(joinedload(Employee.department), joinedload(Employee.position),
                    joinedload(Employee.company))
           .filter(Employee.pin == pin).first())
    return _append(cloud_id or "", pin, scan_time, verify_mode, _employee_info(emp), _now())


def _seed_from_db(db: Session) -> None:
    """Sekali setelah start: isi feed dari scan REALTIME hari ini (webhook menyimpan device_sn = cloud_id)."""
    global _seeded
    with _lock:
        if _seeded:
            return
        _seeded = True
    start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    logs = (db.query(AttendanceLog)
            .filter(AttendanceLog.source == "REALTIME", AttendanceLog.scan_time >= start)
            .order_by(AttendanceLog.scan_time.asc())
            .limit(MAX_EVENTS).all())
    if not logs:
        return
    pins = {log.employee_pin for log in logs}
    emps = {e.pin: e for e in (db.query(Employee)
                               .options(joinedload(Employee.department), joinedload(Employee.position),
                                        joinedload(Employee.company))
                               .filter(Employee.pin.in_(pins)).all())}
    for log in logs:
        _append(log.device_sn, log.employee_pin, log.scan_time, log.verify_mode,
                _employee_info(emps.get(log.employee_pin)), None)


def _public(ev: dict) -> dict:
    return {k: v for k, v in ev.items() if not k.startswith("_")}


def get_feed(db: Session, cloud_id: str | None = None, after: int = 0, limit: int = 30) -> dict:
    _seed_from_db(db)
    # Monitor hanya untuk hari ini: scan kemarin (termasuk kiriman antrian yang terlambat) tidak tampil.
    today = _now().date()
    with _lock:
        today_events = [ev for ev in _events
                        if ev["_scan"].date() == today and (not cloud_id or ev["cloud_id"] == cloud_id)]
        last_seq = _seq
    new_events = [ev for ev in today_events if ev["seq"] > after][-limit:]
    last_received = next((ev["received_at"] for ev in reversed(today_events) if ev["received_at"]), None)
    return {
        "server_time": _now().isoformat(),
        "date": today.isoformat(),
        "last_seq": last_seq,
        # Terbaru di depan
        "events": [_public(ev) for ev in reversed(new_events)],
        "today": {
            "scans": len(today_events),
            "people": len({ev["pin"] for ev in today_events}),
            "unregistered": sum(1 for ev in today_events if not ev["registered"]),
        },
        "last_received_at": last_received,
    }


def list_devices(db: Session) -> list[dict]:
    with _lock:
        last = {}
        for ev in _events:
            if ev["received_at"]:
                last[ev["cloud_id"]] = ev["received_at"]
    return [{"cloud_id": d.cloud_id, "name": d.name, "last_received_at": last.get(d.cloud_id)}
            for d in db.query(Device).filter(Device.is_active.is_(True)).order_by(Device.name).all()]


def reset() -> None:
    """Untuk tes."""
    global _seq, _seeded
    with _lock:
        _events.clear()
        _seq = 0
        _seeded = False
