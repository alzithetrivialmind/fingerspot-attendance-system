from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.dependencies import get_db, get_current_user, require_super_admin
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.core.security import get_password_hash
from app.core.logging_utils import log_activity

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(require_super_admin)] # Protect all user management routes
)

@router.get("/", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = User(
        username=user.username,
        password_hash=hashed_password,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    log_activity(db, current_user.username, "CREATE_USER", f"Membuat user baru: {user.username}")
    
    return new_user

@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user_update.full_name is not None:
        db_user.full_name = user_update.full_name
    if user_update.role is not None:
        db_user.role = user_update.role
    if user_update.is_active is not None:
        db_user.is_active = user_update.is_active
    if user_update.password is not None:
        db_user.password_hash = get_password_hash(user_update.password)
        
    db.commit()
    db.refresh(db_user)
    
    log_activity(db, current_user.username, "UPDATE_USER", f"Mengubah data user: {db_user.username}")
    
    return db_user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent deleting the last super admin
    super_admins = db.query(User).filter(User.role == "super admin").count()
    if db_user.role == "super admin" and super_admins <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last super administrator")
        
    username_deleted = db_user.username
    db.delete(db_user)
    db.commit()
    
    log_activity(db, current_user.username, "DELETE_USER", f"Menghapus user: {username_deleted}")
    
    return None
