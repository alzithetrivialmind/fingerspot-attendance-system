from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import jwt

from app.config import settings
from app.core.security import JWT_SECRET
from app.database import SessionLocal
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

# Hak akses dari yang terendah:
#   monitor        hanya layar monitor (/monitor) dan ganti password
#   view-only      melihat data
#   operator       mengelola karyawan, tarik/import scan, sinkron mesin
#   administrator  + kelola mesin, master data, hapus karyawan
#   super admin    + kelola pengguna, backup & restore
MONITOR_ROLE = "monitor"
MONITOR_ALLOWED_PREFIXES = ("/monitor", "/auth/")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, token: str = Security(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise credentials_exception
    username = payload.get("sub")
    if username is None:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception
    if user.role == MONITOR_ROLE and not request.url.path.startswith(MONITOR_ALLOWED_PREFIXES):
        raise HTTPException(status_code=403, detail="Akun monitor hanya untuk layar monitor")
    return user


def _require_roles(current_user: User, *roles: str) -> User:
    if current_user.role not in roles:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user


def require_super_admin(current_user: User = Depends(get_current_user)):
    return _require_roles(current_user, "super admin")


def require_administrator(current_user: User = Depends(get_current_user)):
    return _require_roles(current_user, "super admin", "administrator")


def require_operator(current_user: User = Depends(get_current_user)):
    return _require_roles(current_user, "super admin", "administrator", "operator")
