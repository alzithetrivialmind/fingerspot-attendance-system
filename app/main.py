import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import models  # noqa: F401  semua model terdaftar sebelum create_all
from app.config import settings
from app.core.security import get_password_hash
from app.database import Base, SessionLocal, engine
from app.models.user import User
from app.routers import (activity_logs, attendance, auth, backups, devices, employees, master_data, monitor, users,
                         webhook)
from app.services.backup_service import start_backup_scheduler
from app.services.sync_engine import start_sync_engine

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def init_default_user():
    """Buat super admin pertama, hanya jika belum ada pengguna sama sekali."""
    db = SessionLocal()
    try:
        if db.query(User.id).first():
            return
        password = settings.ADMIN_PASSWORD or secrets.token_urlsafe(12)
        db.add(User(username=settings.ADMIN_USERNAME, password_hash=get_password_hash(password),
                    full_name="Super Administrator", role="super admin", is_active=True))
        db.commit()
        if not settings.ADMIN_PASSWORD:
            logger.warning("Akun pertama dibuat. Username: %s  Password: %s  (segera ganti setelah login)",
                           settings.ADMIN_USERNAME, password)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    init_default_user()
    start_sync_engine()
    start_backup_scheduler()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

for module in (auth, users, employees, webhook, attendance, devices, master_data, activity_logs, backups, monitor):
    app.include_router(module.router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/images/logo.svg", media_type="image/svg+xml")


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html",
                                      context={"app_name": settings.APP_NAME, "timezone": settings.TIMEZONE})
