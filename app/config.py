from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Nama yang tampil di UI dan dokumentasi API
    APP_NAME: str = "Fingerspot Attendance Hub"
    # Zona waktu mesin absensi: Asia/Jakarta (WIB), Asia/Makassar (WITA), Asia/Jayapura (WIT)
    TIMEZONE: str = "Asia/Jakarta"

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/attendance_db"
    STORAGE_PATH: str = "storage/photos"

    # Kosong = dibuat acak setiap aplikasi start (semua sesi login berakhir saat restart)
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Akun super admin pertama. ADMIN_PASSWORD kosong = dibuat acak dan ditulis sekali ke log.
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""

    # Fingerspot Developer API (https://developer.fingerspot.io)
    FINGERSPOT_API_URL: str = "https://developer.fingerspot.io/api"
    FINGERSPOT_API_KEY: str = ""
    # Opsional: bila diisi, URL webhook di dashboard fingerspot.io wajib ...?token=<nilai ini>
    WEBHOOK_TOKEN: str = ""
    # Opsional: kunci untuk layar monitor tanpa login, buka /monitor?key=<nilai ini>
    MONITOR_KEY: str = ""

    # Backup database (lihat app/services/backup_service.py)
    BACKUP_DIR: str = "backups"
    BACKUP_HOUR: int = 23  # backup harian dibuat setelah jam ini


settings = Settings()
