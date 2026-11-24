import asyncio
import logging
import time

from app.database import SessionLocal
from app.models.employee_device_access import EmployeeDeviceAccess, SyncStatusEnum
from app.models.device import Device
from app.services.device_sync_service import ADD, REMOVE, mark_failed
from app.services.fingerspot_api import trigger_get_userinfo, trigger_set_userinfo, trigger_delete_userinfo

logger = logging.getLogger(__name__)

# Jeda sebelum perintah yang sama dikirim ulang. Status baru jadi SYNCED saat webhook
# konfirmasi datang; tanpa jeda ini, perintah dikirim ulang setiap 10 detik.
RESEND_INTERVAL_SECONDS = 300
# Batas kirim tanpa konfirmasi (sekitar 30 menit) agar antrean tidak mengulang selamanya
MAX_SEND_ATTEMPTS = 6
# Waktu menunggu salinan sidik jari dari mesin sebelum mengubah atau menghapus data di mesin
BACKUP_WAIT_SECONDS = 60

_last_sent: dict = {}  # (employee_pin, device_id, sync_status) -> time.monotonic()
_backup_requested: dict = {}  # (employee_pin, device_id) -> time.monotonic()

# Dihentikan sementara selama restore database (backup_service)
paused = False


def forget(pin: str, device_id: int) -> None:
    """Lupakan jadwal kirim agar baris yang dikirim ulang pengguna segera diproses."""
    for status in (ADD, REMOVE):
        _last_sent.pop((pin, device_id, status), None)
    _backup_requested.pop((pin, device_id), None)


async def process_task(db, task, device) -> bool:
    """Proses satu baris antrean. True jika ada perintah yang dikirim ke fingerspot.io."""
    status = task.sync_status
    pin = task.employee_pin
    employee = task.employee
    send_key = (pin, task.device_id, status)
    backup_key = (pin, task.device_id)
    now = time.monotonic()
    counted = False

    last = _last_sent.get(send_key)
    if last is not None and now - last < RESEND_INTERVAL_SECONDS:
        return False

    if task.attempts >= MAX_SEND_ATTEMPTS:
        mark_failed(task, task.last_error or
                    f"Mesin tidak mengirim konfirmasi setelah {MAX_SEND_ATTEMPTS} kali kirim. "
                    "Periksa mesin online dan URL webhook di fingerspot.io.")
        db.commit()
        forget(pin, task.device_id)
        return False

    try:
        # set_userinfo tanpa template bisa menghapus sidik jari, dan delete_userinfo menghapusnya
        # dari mesin. Salin dulu template dari mesin agar karyawan bisa dikembalikan.
        # Hak di mesin ikut disalin agar admin tidak turun menjadi pengguna biasa.
        if not employee.fingerprint_template or not employee.device_privilege:
            asked = _backup_requested.get(backup_key)
            if asked is None:
                _backup_requested[backup_key] = now
                await trigger_get_userinfo(db, device.cloud_id, pin)
                return True
            if now - asked < BACKUP_WAIT_SECONDS:
                return False
            if status == REMOVE and not employee.fingerprint_template:
                mark_failed(task, "Mesin tidak menjawab permintaan salinan sidik jari, jadi tidak ada yang dihapus. "
                                  "Kemungkinan PIN ini memang tidak ada di mesin. Kalau ada, periksa mesin online "
                                  "dan URL webhook di fingerspot.io.")
                db.commit()
                forget(pin, task.device_id)
                return False

        _last_sent[send_key] = now
        task.attempts = (task.attempts or 0) + 1
        db.commit()
        counted = True
        if status == ADD:
            await trigger_set_userinfo(db, device.cloud_id, pin, employee.full_name,
                                       rfid=employee.rfid or "", template=employee.fingerprint_template or "",
                                       privilege=employee.device_privilege or "1")
        else:
            await trigger_delete_userinfo(db, device.cloud_id, pin)
        # Perintah diterima: alasan gagal dari percobaan sebelumnya tidak berlaku lagi
        task.last_error = None
        db.commit()
        return True
    except Exception as e:
        # Gangguan sementara: dicoba lagi pada giliran berikutnya sampai batas MAX_SEND_ATTEMPTS
        db.rollback()
        _last_sent[send_key] = time.monotonic()
        _backup_requested.pop(backup_key, None)
        if not counted:
            task.attempts = (task.attempts or 0) + 1
        task.last_error = str(e)[:255]
        db.commit()
        logger.warning("Sinkron PIN %s ke mesin %s gagal: %s", pin, device.cloud_id, task.last_error)
        return False


async def delete_pins_from_devices(pins: list, cloud_ids: list) -> None:
    """Untuk karyawan yang dihapus dari sistem: barisnya sudah tiada, jadi tidak lewat antrean."""
    db = SessionLocal()
    try:
        for cloud_id in cloud_ids:
            for pin in pins:
                try:
                    await trigger_delete_userinfo(db, cloud_id, pin)
                except Exception as e:
                    logger.warning("Gagal menghapus PIN %s dari mesin %s: %s", pin, cloud_id, e)
                await asyncio.sleep(0.5)
    finally:
        db.close()


async def process_sync_queue():
    while True:
        if paused:
            await asyncio.sleep(2)
            continue
        db = SessionLocal()
        try:
            pending_tasks = db.query(EmployeeDeviceAccess).filter(
                EmployeeDeviceAccess.sync_status.in_([SyncStatusEnum.PENDING_ADD.value, SyncStatusEnum.PENDING_REMOVE.value])
            ).all()

            for task in pending_tasks:
                device = db.query(Device).filter(Device.id == task.device_id).first()
                if not device or not task.employee:
                    continue
                # Status SYNCED hanya diberikan webhook. Jeda kecil agar tidak kena batas API.
                if await process_task(db, task, device):
                    await asyncio.sleep(1)
        except Exception:
            logger.exception("Antrean sinkron bermasalah")
        finally:
            db.close()

        await asyncio.sleep(10) # check every 10 seconds

def start_sync_engine():
    asyncio.create_task(process_sync_queue())
