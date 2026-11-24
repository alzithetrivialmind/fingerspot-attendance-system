import json
import logging
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.config import settings
from app.dependencies import get_db
from app.models.device import Device
from app.schemas.attendance import FingerspotWebhookItem
from app.services.attendance_service import process_webhook_attendance
from app.services import device_sync_service, live_scan_service, sync_engine
from app.services.device_sync_service import ADD, REMOVE, SYNCED, mark_failed, mark_synced
from app.models.employee_device_access import EmployeeDeviceAccess
from app.models.trans_log import FingerspotTransLog
from app.models.employee import Employee

router = APIRouter(
    prefix="/webhook",
    tags=["webhook"]
)

logger = logging.getLogger(__name__)

# Dokumentasi menyebut 1 = sukses dan 2 = gagal, tetapi mesin Revo terbukti menjawab "OK".
# Nilai gagal selain 2 belum pernah terlihat; yang tidak dikenal dibiarkan menunggu dan dicatat di log.
SUCCESS_STATUSES = {"1", "ok", "success", "true"}
FAILED_STATUSES = {"2", "fail", "failed", "error", "false"}


def _reject_reason(request: Request, db: Session, cloud_id) -> str:
    """Webhook publik tanpa login: hanya terima kiriman dari mesin yang terdaftar.
    Payload resmi fingerspot.io selalu membawa cloud_id mesin. WEBHOOK_TOKEN (opsional) menambah
    rahasia di URL: ?token=..."""
    if settings.WEBHOOK_TOKEN and not secrets.compare_digest(
            request.query_params.get("token", ""), settings.WEBHOOK_TOKEN):
        return "token salah / tidak ada"
    if not cloud_id:
        return "tanpa cloud_id"
    if not db.query(Device.id).filter(Device.cloud_id == str(cloud_id)).first():
        return "cloud_id tidak terdaftar di menu Mesin"
    return ""


def _apply_sync_result(db: Session, trans: FingerspotTransLog, cloud_id) -> None:
    """Terapkan jawaban mesin atas set_userinfo / delete_userinfo ke antrean karyawan."""
    pin = (trans.request_payload or {}).get("pin")
    device = db.query(Device).filter(Device.cloud_id == cloud_id).first()
    if not pin or not device:
        return
    eda = db.query(EmployeeDeviceAccess).filter_by(employee_pin=pin, device_id=device.id).first()
    if not eda:
        return
    wanted = ADD if trans.action_type == "set_userinfo" else REMOVE
    # Jawaban perintah lama tidak boleh menimpa keputusan yang lebih baru (mis. sudah diaktifkan kembali)
    if device_sync_service.intended_action(eda) != wanted:
        return
    if trans.status == 'FAILED':
        mark_failed(eda, "Mesin melaporkan perintah gagal dijalankan")
    elif trans.status == 'SUCCESS':
        if wanted == ADD:
            mark_synced(eda, func.now())
        else:
            db.delete(eda)
        sync_engine.forget(pin, device.id)


def _store_device_user(db: Session, data: dict, cloud_id) -> None:
    """Simpan jawaban get_userinfo. Nama di aplikasi dianggap lebih rapi, jadi tidak ditimpa nama mesin."""
    pin = str(data["pin"]).strip()
    emp = db.query(Employee).filter(Employee.pin == pin).first()
    if not emp:
        emp = Employee(pin=pin, full_name=data.get("name") or f"Karyawan PIN {pin}", is_active=True)
        db.add(emp)
    if not emp.full_name:
        emp.full_name = data.get("name")
    if data.get("rfid") and not emp.rfid:
        emp.rfid = str(data["rfid"])[:50]
    if data.get("template"):
        emp.fingerprint_template = data["template"]
    if data.get("privilege"):
        emp.device_privilege = str(data["privilege"])[:5]
    db.flush()

    # Mesin baru saja membuktikan PIN ini terdaftar padanya
    device = db.query(Device).filter(Device.cloud_id == cloud_id).first()
    if device and emp.is_active:
        exists = db.query(EmployeeDeviceAccess.id).filter_by(employee_pin=pin, device_id=device.id).first()
        if not exists:
            db.add(EmployeeDeviceAccess(employee_pin=pin, device_id=device.id, sync_status=SYNCED))
    db.commit()


def _log_received(db: Session, event_type, trans_id, cloud_id, data) -> None:
    """Catat setiap kiriman untuk melacak jawaban mesin. Hanya nama isian yang dicatat, bukan nilainya:
    data get_userinfo memuat template sidik jari dan password."""
    matched = bool(trans_id and trans_id != "0" and db.query(FingerspotTransLog.trans_id).filter(
        FingerspotTransLog.trans_id == trans_id).first())
    if isinstance(data, dict):
        fields = ",".join(sorted(str(k) for k in data))
        status = data.get("status")
    else:
        fields = type(data).__name__
        status = None
    logger.info("Webhook diterima type=%s trans_id=%s cocok=%s status=%s cloud_id=%s isian=%s",
                   event_type, trans_id, matched, status, cloud_id, fields)


@router.post("/fingerspot")
async def receive_fingerspot_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        raw_payload = await request.json()
    except Exception:
        raw_payload = {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}

    reason = _reject_reason(request, db, raw_payload.get("cloud_id"))
    if reason:
        client_ip = request.client.host if request.client else "-"
        logger.warning("Webhook ditolak (%s) dari %s, type=%s", reason, client_ip, raw_payload.get("type"))
        return JSONResponse(status_code=403, content={"status": "rejected", "message": "Webhook ditolak"})

    # Manually extract fields to avoid 422 Strict Pydantic errors
    event_type = raw_payload.get("type")
    
    # Cast to string because Fingerspot might send trans_id as an integer (e.g., 5) 
    # and PostgreSQL strictly requires string for character varying comparisons.
    trans_id_raw = raw_payload.get("trans_id")
    trans_id = str(trans_id_raw) if trans_id_raw is not None else None
    
    cloud_id_raw = raw_payload.get("cloud_id")
    cloud_id = str(cloud_id_raw) if cloud_id_raw is not None else None
    
    payload_data = raw_payload.get("data", {})
    _log_received(db, event_type, trans_id, cloud_id, payload_data)

    
    # 1. Update Async Transaction Status if applicable
    if trans_id and trans_id != "0":
        trans = db.query(FingerspotTransLog).filter(FingerspotTransLog.trans_id == trans_id).first()
        if trans:
            # Check if payload_data contains status for set_time and restart_device
            if isinstance(payload_data, dict) and "status" in payload_data:
                result = str(payload_data["status"]).strip().lower()
                if result in SUCCESS_STATUSES:
                    trans.status = 'SUCCESS'
                elif result in FAILED_STATUSES:
                    trans.status = 'FAILED'
                else:
                    logger.warning("Status webhook tidak dikenal: %s (trans_id=%s)", payload_data["status"], trans_id)
            elif trans.action_type not in ["sync_users", "get_all_pin"]:
                # If it's not a sync_users action, and doesn't have an explicit status field,
                # we assume receiving the webhook means SUCCESS.
                trans.status = 'SUCCESS'
            
            if trans.action_type in ("set_userinfo", "delete_userinfo"):
                _apply_sync_result(db, trans, cloud_id)

            db.commit()

    if event_type == "attlog":
        # Sometimes Fingerspot sends data as a JSON string instead of an object
        data = payload_data
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                pass
                
        if isinstance(data, dict):
            # Sometimes data is a single dict instead of a list
            data = [data]
            
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # Map actual Fingerspot keys to our schema
                    mapped_item = {
                        "pin": item.get("pin", ""),
                        "scan_time": item.get("scan", ""),
                        "verify_mode": item.get("verify", 0),
                        "io_mode": item.get("status_scan", 0),
                        "sn": cloud_id or ""
                    }
                    try:
                        obj = FingerspotWebhookItem(**mapped_item)
                        process_webhook_attendance(db, obj, raw_payload, source="REALTIME")
                    except Exception as e:
                        logger.warning("Scan dilewati: %s", e)
                        db.rollback()
                        continue
                    # Layar monitor: semua scan tampil, termasuk PIN yang tidak terdaftar
                    try:
                        live_scan_service.record_scan(db, cloud_id, obj.pin, obj.scan_time, obj.verify_mode)
                    except Exception:
                        logger.exception("Gagal mencatat scan ke monitor")
                
    elif event_type == "get_userid_list":
        # Data contains total and pin_arr
        data = payload_data
        if isinstance(data, dict) and "pin_arr" in data:
            pin_arr = data["pin_arr"]
            
            trans = None
            if trans_id and trans_id != "0":
                trans = db.query(FingerspotTransLog).filter(FingerspotTransLog.trans_id == trans_id).first()
                
            # If trans_id is "0" or missing, fallback to the latest PENDING get_all_pin for this cloud_id
            if not trans and cloud_id:
                trans = db.query(FingerspotTransLog).filter(
                    FingerspotTransLog.cloud_id == cloud_id,
                    FingerspotTransLog.action_type == "get_all_pin",
                    FingerspotTransLog.status == "PENDING"
                ).order_by(FingerspotTransLog.created_at.desc()).first()

            if trans:
                trans.total_items = len(pin_arr)
                # We store the pin_arr in request_payload so the frontend can retrieve it and show the popup
                trans.request_payload = {"pin_arr": pin_arr}
                trans.status = 'SUCCESS'
                db.commit()
            
    elif event_type == "get_userinfo":
        data = payload_data
        if isinstance(data, dict) and "pin" in data:
            _store_device_user(db, data, cloud_id)

    return {"status": "success", "message": f"Webhook {event_type} processed."}
