"""Aturan antrean karyawan ke mesin (tabel employee_device_access). Pengirimannya di sync_engine."""
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.employee import Employee
from app.models.employee_device_access import EmployeeDeviceAccess, SyncStatusEnum

ADD = SyncStatusEnum.PENDING_ADD.value
REMOVE = SyncStatusEnum.PENDING_REMOVE.value
SYNCED = SyncStatusEnum.SYNCED.value
FAILED = SyncStatusEnum.FAILED.value


def mark_pending(eda: EmployeeDeviceAccess, status: str) -> None:
    eda.sync_status = status
    eda.attempts = 0
    eda.last_error = None
    eda.failed_action = None


def mark_failed(eda: EmployeeDeviceAccess, error: str) -> None:
    if eda.sync_status in (ADD, REMOVE):
        eda.failed_action = eda.sync_status
    eda.sync_status = FAILED
    eda.last_error = (error or "")[:255] or None


def mark_synced(eda: EmployeeDeviceAccess, when=None) -> None:
    eda.sync_status = SYNCED
    eda.attempts = 0
    eda.last_error = None
    eda.failed_action = None
    if when is not None:
        eda.last_sync_time = when


def intended_action(eda: EmployeeDeviceAccess) -> Optional[str]:
    """Tujuan baris ini: tambah atau hapus dari mesin. Baris FAILED lama belum menyimpan failed_action."""
    if eda.sync_status in (ADD, REMOVE):
        return eda.sync_status
    if eda.sync_status == FAILED:
        if eda.failed_action:
            return eda.failed_action
        return ADD if eda.employee is None or eda.employee.is_active else REMOVE
    return None


def active_device_ids(db: Session) -> List[int]:
    return [d.id for d in db.query(Device.id).filter(Device.is_active.is_(True)).all()]


def queue_on_all_devices(db: Session, pins: Iterable[str], status: str) -> None:
    """Antrekan PIN ke semua mesin aktif, termasuk PIN yang belum punya baris antrean."""
    pins = list(pins)
    device_ids = active_device_ids(db)
    if not pins or not device_ids:
        return
    rows = db.query(EmployeeDeviceAccess).filter(EmployeeDeviceAccess.employee_pin.in_(pins)).all()
    existing = {(r.employee_pin, r.device_id): r for r in rows}
    for row in rows:
        if row.sync_status != status:
            mark_pending(row, status)
    for pin in pins:
        for device_id in device_ids:
            if (pin, device_id) not in existing:
                db.add(EmployeeDeviceAccess(employee_pin=pin, device_id=device_id, sync_status=status))


def _apply_device_selection(db: Session, emp: Employee, selected: List[int]) -> None:
    rows = {eda.device_id: eda for eda in emp.device_accesses}
    for device_id in selected:
        row = rows.get(device_id)
        if row is None:
            db.add(EmployeeDeviceAccess(employee_pin=emp.pin, device_id=device_id, sync_status=ADD))
        elif row.sync_status == REMOVE or row.sync_status == FAILED:
            # Menyimpan form sekaligus mencoba ulang yang gagal
            mark_pending(row, ADD)
    for device_id, row in rows.items():
        if device_id not in selected and row.sync_status != REMOVE:
            mark_pending(row, REMOVE)


def after_employee_update(db: Session, emp: Employee, was_active: bool, old_name: Optional[str], old_pin: str,
                          selected_devices: Optional[List[int]]) -> Optional[str]:
    """Sesuaikan antrean sesudah data karyawan berubah. Mengembalikan catatan untuk log aktivitas."""
    note = None
    if not emp.is_active:
        if was_active:
            queue_on_all_devices(db, [emp.pin], REMOVE)
        else:
            for eda in emp.device_accesses:
                mark_pending(eda, REMOVE)
        return note

    if not was_active:
        # Aktif kembali: dikembalikan ke semua mesin, bersama sidik jari yang sudah tersalin
        queue_on_all_devices(db, [emp.pin], ADD)
    elif selected_devices is not None:
        _apply_device_selection(db, emp, selected_devices)

    pin_changed = emp.pin != old_pin
    if pin_changed or emp.full_name != old_name:
        # Hanya untuk mesin yang diketahui memuat karyawan ini
        for eda in emp.device_accesses:
            if eda.sync_status == SYNCED:
                mark_pending(eda, ADD)
    if pin_changed:
        # PIN lama tidak dihapus otomatis: penukaran PIN bisa memakai PIN lama itu lagi
        note = f"PIN lama {old_pin} tetap ada di mesin, hapus lewat mesin bila sudah tidak dipakai"
    return note
