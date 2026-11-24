"""Layar monitor: layar besar yang menampilkan scan terbaru dari mesin secara realtime.

Akses feed: login biasa (role apa pun, token dari aplikasi utama) atau, untuk PC monitor yang
menyala terus, kunci MONITOR_KEY di URL (/monitor?key=...) agar tidak perlu login ulang tiap 24 jam.
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.services import live_scan_service

router = APIRouter(prefix="/monitor", tags=["monitor"])
templates = Jinja2Templates(directory="app/templates")


def require_monitor_access(request: Request, db: Session = Depends(get_db)):
    key = request.query_params.get("key") or request.headers.get("X-Monitor-Key") or ""
    if settings.MONITOR_KEY and key:
        if secrets.compare_digest(key, settings.MONITOR_KEY):
            return
        raise HTTPException(status_code=401, detail="Kunci monitor salah")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else None
    get_current_user(request=request, token=token, db=db)


@router.get("", include_in_schema=False)
def monitor_page(request: Request):
    # Halaman tanpa data; data diambil lewat /monitor/feed yang dicek aksesnya.
    return templates.TemplateResponse(request=request, name="monitor.html",
                                      context={"app_name": settings.APP_NAME, "timezone": settings.TIMEZONE})


@router.get("/feed", dependencies=[Depends(require_monitor_access)])
def monitor_feed(
    cloud_id: Optional[str] = None,
    after: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return live_scan_service.get_feed(db, cloud_id=cloud_id or None, after=after, limit=limit)


@router.get("/devices", dependencies=[Depends(require_monitor_access)])
def monitor_devices(db: Session = Depends(get_db)):
    return live_scan_service.list_devices(db)
