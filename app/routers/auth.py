from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.core.security import verify_password, create_access_token, get_password_hash
from app.schemas.user import MIN_PASSWORD, Token, UserResponse
from app.core.logging_utils import log_activity
from pydantic import BaseModel, Field


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=MIN_PASSWORD)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

@router.post("/login", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(form_data.password, user.password_hash):
        log_activity(db, user.username, "LOGIN_FAILED", "Login gagal: password salah")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "full_name": user.full_name or user.username}
    )
    
    log_activity(db, user.username, "LOGIN", "Berhasil login ke dalam sistem")
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "full_name": user.full_name or user.username
    }

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return current_user



@router.post("/change-password")
def change_own_password(req: ChangePasswordRequest, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """Setiap pengguna (semua role) mengganti password akunnya sendiri."""
    if not verify_password(req.current_password, current_user.password_hash):
        log_activity(db, current_user.username, "CHANGE_PASSWORD_FAILED", "Ganti password gagal: password lama salah")
        raise HTTPException(status_code=400, detail="Password lama salah")
    if req.new_password == req.current_password:
        raise HTTPException(status_code=400, detail="Password baru harus berbeda dari password lama")
    current_user.password_hash = get_password_hash(req.new_password)
    db.commit()
    log_activity(db, current_user.username, "CHANGE_PASSWORD", "Mengganti password akun sendiri")
    return {"success": True}
