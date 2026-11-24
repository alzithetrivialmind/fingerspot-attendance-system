import os

# Diset sebelum modul app diimpor: tes tidak boleh menyentuh database sungguhan atau membaca .env lokal.
os.environ.update({
    "DATABASE_URL": "sqlite:///:memory:",
    "JWT_SECRET_KEY": "kunci-khusus-tes-yang-cukup-panjang-untuk-hs256",
    "ADMIN_PASSWORD": "password-khusus-tes",
    "FINGERSPOT_API_KEY": "",
    "WEBHOOK_TOKEN": "",
    "MONITOR_KEY": "",
    "TIMEZONE": "Asia/Jakarta",
})

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database

# Satu koneksi SQLite di memori untuk semua sesi, termasuk yang dibuka lifespan dan proses latar
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
database.engine = engine
database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app import dependencies, main
from app.database import Base
from app.models.device import Device
from app.models.user import User

main.start_sync_engine = lambda: None
main.init_default_user = lambda: None
app = main.app


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """Client dengan akun super admin; pengecekan role asli bisa dipakai dengan menghapus override."""
    admin = User(id=1, username="admin", role="super admin", is_active=True)
    app.dependency_overrides[dependencies.get_db] = lambda: db_session
    app.dependency_overrides[dependencies.get_current_user] = lambda: admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def webhook_device(db_session):
    """Mesin terdaftar: webhook hanya menerima payload dengan cloud_id yang ada di tabel devices."""
    device = Device(name="Mesin 01", cloud_id="CLOUD_OK")
    db_session.add(device)
    db_session.commit()
    return device
