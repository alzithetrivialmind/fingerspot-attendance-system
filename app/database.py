from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Zona waktu diset di setiap sesi PostgreSQL: webhook mengirim jam setempat tanpa zona waktu,
# dan func.date() di server harus memakai zona yang sama. Variabel TZ/PGTZ di container tidak
# berlaku untuk koneksi dari Python.
if settings.DATABASE_URL.startswith("postgres"):
    connect_args = {"options": f"-c timezone={settings.TIMEZONE}"}
else:
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
