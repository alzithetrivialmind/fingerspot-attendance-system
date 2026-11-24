import asyncio
import logging
import uuid
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging_utils import log_activity
from app.database import SessionLocal
from app.dependencies import get_db, get_current_user, require_operator, require_administrator, require_super_admin
from app.models.device import Device
from app.models.employee import Employee
from app.models.employee_device_access import EmployeeDeviceAccess
from app.models.trans_log import FingerspotTransLog
from app.models.user import User
from app.schemas.device import DeviceCreate, DeviceInDB, SyncStatus
from app.services import device_sync_service, sync_engine
from app.services.fingerspot_api import (get_device_info, restart_device, set_device_time, trigger_get_all_pin,
                                         trigger_get_userinfo)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/devices",
    tags=["devices"],
    dependencies=[Depends(require_operator)] # operator ke atas
)

@router.get("/", response_model=List[DeviceInDB])
def get_devices(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Device).offset(skip).limit(limit).all()

@router.post("/", response_model=DeviceInDB, dependencies=[Depends(require_administrator)])
def create_device(device: DeviceCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_device = db.query(Device).filter(Device.cloud_id == device.cloud_id).first()
    if db_device:
        raise HTTPException(status_code=400, detail="Device with this cloud_id already exists")
    db_device = Device(**device.model_dump())
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    log_activity(db, current_user.username, "CREATE_DEVICE", f"Menambahkan mesin {db_device.name} ({db_device.cloud_id})")
    return db_device

@router.delete("/{device_id}", dependencies=[Depends(require_super_admin)])
def delete_device(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    info = f"{db_device.name} ({db_device.cloud_id})"
    db.delete(db_device)
    db.commit()
    log_activity(db, current_user.username, "DELETE_DEVICE", f"Menghapus mesin {info}")
    return {"ok": True}

@router.post("/{device_id}/fetch-data")
async def fetch_device_data(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    try:
        # Trigger background data sync from fingerspot cloud
        result = await trigger_get_all_pin(db, db_device.cloud_id)
        if result and "trans_id" in result:
            log_activity(db, current_user.username, "FETCH_DEVICE_USERS", f"Menarik data karyawan dari mesin {db_device.name} ({db_device.cloud_id})")
            return {"status": "sync_triggered", "trans_id": result["trans_id"]}
        else:
            raise HTTPException(status_code=500, detail="Failed to get trans_id from Fingerspot API")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/transactions/{trans_id}", response_model=SyncStatus)
def get_sync_status(trans_id: str, db: Session = Depends(get_db)):
    trans = db.query(FingerspotTransLog).filter(FingerspotTransLog.trans_id == trans_id).first()
    if not trans:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return {
        "trans_id": trans.trans_id,
        "status": trans.status,
        "total_items": trans.total_items,
        "processed_items": trans.processed_items,
        "data": trans.request_payload
    }


class SetTimeRequest(BaseModel):
    timezone: str = settings.TIMEZONE

@router.get("/{device_id}/info")
async def get_device_info_endpoint(device_id: int, db: Session = Depends(get_db)):
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    try:
        result = await get_device_info(db, db_device.cloud_id)
        if result and result.get("success"):
            return {"status": "success", "data": result.get("data", {})}
        else:
            raise HTTPException(status_code=500, detail="Failed to fetch device info")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{device_id}/set-time", dependencies=[Depends(require_administrator)])
async def set_device_time_endpoint(device_id: int, request: SetTimeRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    try:
        result = await set_device_time(db, db_device.cloud_id, request.timezone)
        if result and "trans_id" in result:
            log_activity(db, current_user.username, "SET_DEVICE_TIME", f"Menyetel jam mesin {db_device.name} ({db_device.cloud_id}) ke {request.timezone}")
            return {"status": "time_set_triggered", "trans_id": result["trans_id"]}
        else:
            raise HTTPException(status_code=500, detail="Failed to trigger set time")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{device_id}/restart", dependencies=[Depends(require_administrator)])
async def restart_device_endpoint(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    try:
        result = await restart_device(db, db_device.cloud_id)
        if result and "trans_id" in result:
            log_activity(db, current_user.username, "RESTART_DEVICE", f"Me-restart mesin {db_device.name} ({db_device.cloud_id})")
            return {"status": "restart_triggered", "trans_id": result["trans_id"]}
        else:
            raise HTTPException(status_code=500, detail="Failed to trigger restart")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SyncSelectedUsersRequest(BaseModel):
    pin_arr: List[str]

class PushEmployeesRequest(BaseModel):
    employee_ids: List[int]

def _increment_progress(db, parent_trans_id):
    if not parent_trans_id:
        return
    try:
        trans = db.query(FingerspotTransLog).filter(FingerspotTransLog.trans_id == parent_trans_id).first()
        if trans:
            trans.processed_items += 1
            db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Gagal memperbarui progres %s: %s", parent_trans_id, e)

async def sync_users_background_task(cloud_id: str, pin_arr: List[str], parent_trans_id: str):
    db = SessionLocal()
    failed = 0
    try:
        for pin in pin_arr:
            try:
                # Jawaban get_userinfo membawa nama, kartu, dan template sidik jari
                await trigger_get_userinfo(db, cloud_id, pin)
                await asyncio.sleep(0.5) # rate limit
            except Exception as e:
                failed += 1
                logger.warning("get_userinfo PIN %s gagal: %s", pin, e)
            finally:
                # Hitung juga yang gagal agar progres di UI tidak macet
                _increment_progress(db, parent_trans_id)
        if parent_trans_id:
            trans = db.query(FingerspotTransLog).filter(FingerspotTransLog.trans_id == parent_trans_id).first()
            if trans:
                trans.status = 'FAILED' if failed and failed == len(pin_arr) else 'SUCCESS'
                trans.request_payload = {"failed": failed}
                db.commit()
    finally:
        db.close()


@router.post("/{device_id}/sync-selected-users")
async def sync_selected_users(
    device_id: int, 
    request: SyncSelectedUsersRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    trans_id = str(uuid.uuid4())
    trans = FingerspotTransLog(
        trans_id=trans_id,
        cloud_id=db_device.cloud_id,
        action_type="sync_users",
        status="PENDING",
        total_items=len(request.pin_arr),
        processed_items=0
    )
    db.add(trans)
    db.commit()
    
    background_tasks.add_task(sync_users_background_task, db_device.cloud_id, request.pin_arr, trans_id)
    log_activity(db, current_user.username, "SYNC_DEVICE_USERS", f"Sinkron {len(request.pin_arr)} karyawan ke mesin {db_device.name} ({db_device.cloud_id})")
    return {"status": "sync_triggered", "trans_id": trans_id}

@router.post("/{device_id}/push-employees")
def push_employees_endpoint(
    device_id: int,
    request: PushEmployeesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Masukkan karyawan ke antrean. Pengiriman dan konfirmasinya ditangani sync_engine."""
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")

    employees = db.query(Employee).filter(Employee.id.in_(request.employee_ids), Employee.is_active.is_(True)).all()
    if not employees:
        raise HTTPException(status_code=400, detail="Tidak ada karyawan aktif yang dipilih")

    for emp in employees:
        eda = db.query(EmployeeDeviceAccess).filter_by(employee_pin=emp.pin, device_id=db_device.id).first()
        if not eda:
            db.add(EmployeeDeviceAccess(employee_pin=emp.pin, device_id=db_device.id, sync_status=device_sync_service.ADD))
        else:
            device_sync_service.mark_pending(eda, device_sync_service.ADD)
            sync_engine.forget(emp.pin, db_device.id)
    db.commit()

    log_activity(db, current_user.username, "PUSH_EMPLOYEES", f"Mengantrekan {len(employees)} karyawan ke mesin {db_device.name} ({db_device.cloud_id})")

    return {"status": "success", "queued": len(employees),
            "message": f"{len(employees)} karyawan masuk antrean kirim ke mesin. Hasilnya terlihat di kolom Sinkron karyawan."}


@router.get("/sync-summary")
def get_sync_summary(db: Session = Depends(get_db)):
    """Jumlah status antrean per mesin dan rincian yang gagal."""
    summary = {}
    for eda in db.query(EmployeeDeviceAccess).all():
        item = summary.setdefault(eda.device_id, {"synced": 0, "pending": 0, "failed": 0, "failures": []})
        if eda.sync_status == device_sync_service.SYNCED:
            item["synced"] += 1
        elif eda.sync_status == device_sync_service.FAILED:
            item["failed"] += 1
            item["failures"].append({
                "pin": eda.employee_pin,
                "name": eda.employee.full_name if eda.employee else None,
                "action": device_sync_service.intended_action(eda),
                "error": eda.last_error,
            })
        else:
            item["pending"] += 1
    return summary


@router.post("/{device_id}/retry-failed")
def retry_failed_sync(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")

    rows = db.query(EmployeeDeviceAccess).filter_by(device_id=device_id, sync_status=device_sync_service.FAILED).all()
    for eda in rows:
        device_sync_service.mark_pending(eda, device_sync_service.intended_action(eda))
        sync_engine.forget(eda.employee_pin, device_id)
    db.commit()

    log_activity(db, current_user.username, "RETRY_DEVICE_SYNC", f"Mengirim ulang {len(rows)} sinkron gagal ke mesin {db_device.name} ({db_device.cloud_id})")
    return {"retried": len(rows)}
