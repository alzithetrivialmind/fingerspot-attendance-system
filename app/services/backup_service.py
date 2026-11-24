"""Backup & restore database PostgreSQL (pg_dump / pg_restore format custom).

Struktur folder BACKUP_DIR:
    harian/   7 terakhir      (dibuat otomatis tiap hari setelah jam BACKUP_HOUR)
    mingguan/ 5 terakhir      (salinan backup harian pertama di minggu itu)
    bulanan/  6 terakhir      (salinan backup harian pertama di bulan itu)
    manual/   10 terakhir     (tombol "Backup sekarang")
    sebelum-restore/ 5 terakhir (dibuat otomatis tepat sebelum restore)

Backup tertua di tiap folder dihapus otomatis, jadi tidak ada yang lebih tua dari ~6 bulan.
"""
import asyncio
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional


from app.config import settings
from app.core.timezone import LOCAL_TZ


logger = logging.getLogger(__name__)

KINDS = {
    "harian": {"label": "Harian", "keep": 7},
    "mingguan": {"label": "Mingguan", "keep": 5},
    "bulanan": {"label": "Bulanan", "keep": 6},
    "manual": {"label": "Manual", "keep": 10},
    "sebelum-restore": {"label": "Sebelum restore", "keep": 5},
}
FILE_RE = re.compile(r"^attendance_(?P<kind>[a-z-]+)_(?P<ts>\d{8}_\d{6})\.dump$")
DUMP_TIMEOUT = 600
# Kalau ada transaksi lain yang memegang kunci tabel, restore gagal (dan di-rollback)
# setelah jeda ini alih-alih menggantung sampai DUMP_TIMEOUT.
RESTORE_LOCK_TIMEOUT = "30s"

# Satu operasi backup/restore dalam satu waktu (uvicorn berjalan satu proses)
_lock = asyncio.Lock()


class BackupError(Exception):
    """Pesan siap ditampilkan ke pengguna."""


def backup_root() -> Path:
    return Path(settings.BACKUP_DIR)


def tools_available() -> bool:
    return bool(shutil.which("pg_dump") and shutil.which("pg_restore"))


def _now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _filename(kind: str, when: datetime) -> str:
    return f"attendance_{kind}_{when:%Y%m%d_%H%M%S}.dump"


def _run(cmd: List[str], env: Optional[dict] = None) -> None:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=DUMP_TIMEOUT,
                             env={**os.environ, **(env or {})})
    except FileNotFoundError:
        raise BackupError("pg_dump/pg_restore tidak terpasang di server aplikasi")
    except subprocess.TimeoutExpired:
        raise BackupError(f"Proses melebihi {DUMP_TIMEOUT // 60} menit dan dihentikan")
    if res.returncode != 0:
        # Pesan pg_* kadang memuat URL koneksi; jangan sampai password ikut tampil
        msg = re.sub(r"postgres(ql)?://\S+", "postgresql://***", (res.stderr or res.stdout or "").strip())
        raise BackupError(f"{Path(cmd[0]).name} gagal: {msg[-500:]}")


def list_files(kind: str) -> List[dict]:
    folder = backup_root() / kind
    if not folder.is_dir():
        return []
    files = []
    for p in folder.iterdir():
        m = FILE_RE.match(p.name)
        if m and p.is_file():
            files.append({
                "name": p.name,
                "kind": kind,
                "size": p.stat().st_size,
                "created_at": LOCAL_TZ.localize(datetime.strptime(m["ts"], "%Y%m%d_%H%M%S")).isoformat(),
            })
    return sorted(files, key=lambda f: f["name"], reverse=True)


def list_backups() -> List[dict]:
    return [
        {"kind": kind, "label": meta["label"], "keep": meta["keep"], "files": list_files(kind)}
        for kind, meta in KINDS.items()
    ]


def resolve(kind: str, name: str) -> Path:
    """Path file backup yang valid; menolak nama aneh (path traversal)."""
    m = FILE_RE.match(name or "")
    if kind not in KINDS or not m or m["kind"] != kind:
        raise BackupError("File backup tidak valid")
    path = backup_root() / kind / name
    if not path.is_file():
        raise BackupError("File backup tidak ditemukan")
    return path


def prune(kind: str) -> List[str]:
    removed = []
    for f in list_files(kind)[KINDS[kind]["keep"]:]:
        (backup_root() / kind / f["name"]).unlink(missing_ok=True)
        removed.append(f["name"])
    return removed


def create_backup(kind: str, when: Optional[datetime] = None) -> dict:
    """pg_dump ke folder jenisnya, lalu buang yang melebihi retensi. Sinkron (jalankan di thread)."""
    if kind not in KINDS:
        raise BackupError("Jenis backup tidak dikenal")
    when = when or _now()
    folder = backup_root() / kind
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / _filename(kind, when)
    tmp = target.with_suffix(".part")
    try:
        _run(["pg_dump", "--format=custom", "--no-owner", "--file", str(tmp), "--dbname", settings.DATABASE_URL])
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    prune(kind)
    return {"name": target.name, "kind": kind, "size": target.stat().st_size}


def _copy_as(src: Path, kind: str, when: datetime) -> str:
    folder = backup_root() / kind
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / _filename(kind, when)
    shutil.copy2(src, target)
    prune(kind)
    return target.name


def _has_file(kind: str, prefix: str) -> bool:
    return any(f["name"].split("_")[-2].startswith(prefix) for f in list_files(kind))


def run_scheduled(now: Optional[datetime] = None) -> List[str]:
    """Backup otomatis: harian sekali sehari setelah BACKUP_HOUR; mingguan/bulanan disalin dari
    backup harian pertama di minggu/bulan itu. Mengembalikan daftar file yang dibuat."""
    now = now or _now()
    if now.hour < settings.BACKUP_HOUR or _has_file("harian", f"{now:%Y%m%d}"):
        return []
    daily = create_backup("harian", now)
    src = backup_root() / "harian" / daily["name"]
    made = [daily["name"]]

    iso_year, iso_week, _ = now.isocalendar()
    week_done = any(
        datetime.strptime(f["name"].split("_")[-2], "%Y%m%d").isocalendar()[:2] == (iso_year, iso_week)
        for f in list_files("mingguan")
    )
    if not week_done:
        made.append(_copy_as(src, "mingguan", now))
    if not _has_file("bulanan", f"{now:%Y%m}"):
        made.append(_copy_as(src, "bulanan", now))
    return made


def restore_backup(path: Path) -> None:
    """pg_restore dalam satu transaksi: kalau gagal di tengah, database tidak berubah."""
    _run([
        "pg_restore", "--clean", "--if-exists", "--no-owner", "--single-transaction",
        "--dbname", settings.DATABASE_URL, str(path),
    ], env={"PGOPTIONS": f"-c lock_timeout={RESTORE_LOCK_TIMEOUT}"})


async def scheduler_loop(interval_seconds: int = 600) -> None:
    from app.core.logging_utils import log_activity
    from app.database import SessionLocal

    if not tools_available():
        logger.warning("pg_dump/pg_restore tidak ditemukan, backup otomatis tidak aktif")
        return
    while True:
        try:
            if not _lock.locked():
                async with _lock:
                    made = await asyncio.to_thread(run_scheduled)
                if made:
                    db = SessionLocal()
                    try:
                        log_activity(db, "sistem", "BACKUP_AUTO", "Backup otomatis: " + ", ".join(made))
                    finally:
                        db.close()
        except Exception as e:  # jangan sampai loop mati
            logger.error("Gagal backup otomatis: %s", e)
        await asyncio.sleep(interval_seconds)


def start_backup_scheduler() -> None:
    if not settings.DATABASE_URL.startswith("postgres"):
        return  # pg_dump hanya untuk PostgreSQL (tes memakai SQLite)
    asyncio.create_task(scheduler_loop())
