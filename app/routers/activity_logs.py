import math
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_operator
from app.models.activity_log import ActivityLog

router = APIRouter(
    prefix="/activity-logs",
    tags=["activity-logs"],
    # Jejak audit: siapa mengubah/menarik apa dan kapan. View-only tidak perlu melihatnya.
    dependencies=[Depends(require_operator)],
)

# Kategori filter di halaman Log aktivitas -> kode aksi yang dicatat log_activity()
ACTION_CATEGORIES = {
    "login": ["LOGIN", "LOGIN_FAILED", "CHANGE_PASSWORD", "CHANGE_PASSWORD_FAILED"],
    "karyawan": ["CREATE_EMPLOYEE", "UPDATE_EMPLOYEE", "UPDATE_EMPLOYEE_PHOTO", "DELETE_EMPLOYEE",
                 "BULK_DELETE_EMPLOYEES", "BULK_UPDATE_EMPLOYEE_STATUS", "IMPORT_EMPLOYEES"],
    "absensi": ["PULL_ATTENDANCE", "IMPORT_ATTENDANCE"],
    "export": ["EXPORT_DATA"],
    "master": ["CREATE_MASTER_DATA", "UPDATE_MASTER_DATA", "DELETE_MASTER_DATA"],
    "mesin": ["CREATE_DEVICE", "DELETE_DEVICE", "FETCH_DEVICE_USERS", "SET_DEVICE_TIME", "RESTART_DEVICE",
              "SYNC_DEVICE_USERS", "PUSH_EMPLOYEES", "RETRY_DEVICE_SYNC"],
    "pengguna": ["CREATE_USER", "UPDATE_USER", "DELETE_USER"],
    "backup": ["BACKUP_AUTO", "BACKUP_MANUAL", "RESTORE_DATABASE"],
}


def _serialize(log: ActivityLog) -> dict:
    return {
        "id": log.id,
        "timestamp": log.timestamp,
        "username": log.username,
        "action": log.action,
        "details": log.details,
    }


@router.get("/")
def get_logs(
    page: int = 1,
    limit: int = 50,
    username: Optional[str] = None,
    category: Optional[str] = None,
    action: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    page = max(page, 1)
    limit = min(max(limit, 1), 500)
    query = db.query(ActivityLog)

    if username:
        query = query.filter(ActivityLog.username == username)
    if action:
        query = query.filter(ActivityLog.action == action)
    elif category in ACTION_CATEGORIES:
        query = query.filter(ActivityLog.action.in_(ACTION_CATEGORIES[category]))
    if from_date:
        query = query.filter(ActivityLog.timestamp >= datetime.combine(from_date, time.min))
    if to_date:
        query = query.filter(ActivityLog.timestamp < datetime.combine(to_date + timedelta(days=1), time.min))
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(ActivityLog.details.ilike(term), ActivityLog.username.ilike(term)))

    total = query.count()
    logs = (
        query.order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "data": [_serialize(log) for log in logs],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total else 0,
    }


@router.get("/users")
def get_log_users(db: Session = Depends(get_db)):
    """Daftar username yang pernah tercatat, untuk dropdown filter."""
    rows = db.query(ActivityLog.username).distinct().order_by(ActivityLog.username).all()
    return [r[0] for r in rows]
