import logging

from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog

logger = logging.getLogger(__name__)


def log_activity(db: Session, username: str, action: str, details: str = None):
    try:
        new_log = ActivityLog(
            username=username,
            action=action,
            details=details
        )
        db.add(new_log)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Gagal mencatat log aktivitas")
