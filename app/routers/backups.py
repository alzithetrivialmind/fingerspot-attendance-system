import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging_utils import log_activity
from app.database import SessionLocal, engine
from app.dependencies import get_current_user, get_db, require_super_admin
from app.models.user import User
from app.services import backup_service, sync_engine
from app.services.backup_service import BackupError

router = APIRouter(
    prefix="/backups",
    tags=["backups"],
    dependencies=[Depends(require_super_admin)],
)


class RestoreRequest(BaseModel):
    kind: str
    name: str
    confirm: str


def _busy():
    if backup_service._lock.locked():
        raise HTTPException(status_code=409, detail="Backup atau restore lain sedang berjalan, coba lagi sebentar")


@router.get("/")
def list_backups():
    return {
        "tools_available": backup_service.tools_available(),
        "backup_hour": settings.BACKUP_HOUR,
        "busy": backup_service._lock.locked(),
        "groups": backup_service.list_backups(),
    }


@router.post("/run")
async def run_backup(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _busy()
    try:
        async with backup_service._lock:
            result = await asyncio.to_thread(backup_service.create_backup, "manual")
    except BackupError as e:
        raise HTTPException(status_code=500, detail=str(e))
    log_activity(db, current_user.username, "BACKUP_MANUAL", f"Backup manual: {result['name']}")
    return result


@router.get("/{kind}/{name}/download")
def download_backup(kind: str, name: str, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    try:
        path = backup_service.resolve(kind, name)
    except BackupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_activity(db, current_user.username, "EXPORT_DATA", f"Unduh file backup {kind}/{name}")
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@router.post("/restore")
async def restore(req: RestoreRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if req.confirm.strip() != req.name:
        raise HTTPException(status_code=400, detail="Ketik nama file backup persis untuk konfirmasi")
    try:
        path = backup_service.resolve(req.kind, req.name)
    except BackupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    _busy()

    async with backup_service._lock:
        sync_engine.paused = True
        try:
            # Kondisi sekarang diamankan dulu, supaya restore yang salah pilih bisa dibatalkan
            safety = await asyncio.to_thread(backup_service.create_backup, "sebelum-restore")
            # Sesi request ini (dipakai cek login) masih membuka transaksi yang memegang kunci
            # tabel users; tanpa ditutup, pg_restore menunggu dirinya sendiri selamanya.
            db.close()
            engine.dispose()
            await asyncio.to_thread(backup_service.restore_backup, path)
        except BackupError as e:
            raise HTTPException(status_code=500, detail=f"Restore dibatalkan, data tidak berubah. {e}")
        finally:
            # Koneksi lama di pool menunjuk ke tabel yang sudah diganti
            engine.dispose()
            sync_engine.paused = False

    # Dicatat setelah restore agar tidak ikut tertimpa isi backup
    db = SessionLocal()
    try:
        log_activity(db, current_user.username, "RESTORE_DATABASE",
                     f"Restore database dari {req.kind}/{req.name} (kondisi sebelumnya disimpan di sebelum-restore/{safety['name']})")
    finally:
        db.close()
    return {"success": True, "restored": req.name, "safety_backup": safety["name"]}
