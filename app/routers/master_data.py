from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.dependencies import get_db, get_current_user, require_administrator
from app.core.logging_utils import log_activity
from app.models.user import User
from app.models.department import Department
from app.models.position import Position
from app.models.company import Company
from app.schemas.master_data import (
    Department as DepartmentSchema, DepartmentBase,
    Position as PositionSchema, PositionBase,
    Company as CompanySchema, CompanyBase,
)
from fastapi import HTTPException

router = APIRouter(
    prefix="/master-data",
    tags=["master-data"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/departments", response_model=List[DepartmentSchema])
def get_departments(db: Session = Depends(get_db)):
    return db.query(Department).all()

@router.post("/departments", response_model=DepartmentSchema, dependencies=[Depends(require_administrator)])
def create_department(dept: DepartmentBase, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_dept = Department(name=dept.name)
    db.add(new_dept)
    db.commit()
    db.refresh(new_dept)
    log_activity(db, current_user.username, "CREATE_MASTER_DATA", f"Menambahkan departemen baru: {new_dept.name}")
    return new_dept

@router.delete("/departments/{dept_id}", dependencies=[Depends(require_administrator)])
def delete_department(dept_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    # Check dependencies before deleting to be safe, or let SQLAlchemy handle foreign key constraints
    try:
        dept_name = dept.name
        db.delete(dept)
        db.commit()
        log_activity(db, current_user.username, "DELETE_MASTER_DATA", f"Menghapus departemen: {dept_name}")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cannot delete department (it might be in use)")
    return {"message": "Department deleted"}

@router.put("/departments/{dept_id}", response_model=DepartmentSchema, dependencies=[Depends(require_administrator)])
def update_department(dept_id: int, dept: DepartmentBase, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_dept = db.query(Department).filter(Department.id == dept_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db_dept.name = dept.name
    db.commit()
    db.refresh(db_dept)
    log_activity(db, current_user.username, "UPDATE_MASTER_DATA", f"Mengubah departemen menjadi: {db_dept.name}")
    return db_dept

@router.get("/positions", response_model=List[PositionSchema])
def get_positions(db: Session = Depends(get_db)):
    return db.query(Position).all()

@router.post("/positions", response_model=PositionSchema, dependencies=[Depends(require_administrator)])
def create_position(pos: PositionBase, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_pos = Position(name=pos.name)
    db.add(new_pos)
    db.commit()
    db.refresh(new_pos)
    log_activity(db, current_user.username, "CREATE_MASTER_DATA", f"Menambahkan posisi baru: {new_pos.name}")
    return new_pos

@router.delete("/positions/{pos_id}", dependencies=[Depends(require_administrator)])
def delete_position(pos_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pos = db.query(Position).filter(Position.id == pos_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    try:
        pos_name = pos.name
        db.delete(pos)
        db.commit()
        log_activity(db, current_user.username, "DELETE_MASTER_DATA", f"Menghapus posisi: {pos_name}")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cannot delete position (it might be in use)")
    return {"message": "Position deleted"}

@router.put("/positions/{pos_id}", response_model=PositionSchema, dependencies=[Depends(require_administrator)])
def update_position(pos_id: int, pos: PositionBase, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_pos = db.query(Position).filter(Position.id == pos_id).first()
    if not db_pos:
        raise HTTPException(status_code=404, detail="Position not found")
    db_pos.name = pos.name
    db.commit()
    db.refresh(db_pos)
    log_activity(db, current_user.username, "UPDATE_MASTER_DATA", f"Mengubah posisi menjadi: {db_pos.name}")
    return db_pos

@router.get("/companies", response_model=List[CompanySchema])
def get_companies(db: Session = Depends(get_db)):
    return db.query(Company).all()

@router.post("/companies", response_model=CompanySchema, dependencies=[Depends(require_administrator)])
def create_company(comp: CompanyBase, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_comp = Company(name=comp.name)
    db.add(new_comp)
    db.commit()
    db.refresh(new_comp)
    log_activity(db, current_user.username, "CREATE_MASTER_DATA", f"Menambahkan perusahaan baru: {new_comp.name}")
    return new_comp

@router.delete("/companies/{comp_id}", dependencies=[Depends(require_administrator)])
def delete_company(comp_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    comp = db.query(Company).filter(Company.id == comp_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        comp_name = comp.name
        db.delete(comp)
        db.commit()
        log_activity(db, current_user.username, "DELETE_MASTER_DATA", f"Menghapus perusahaan: {comp_name}")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cannot delete company (it might be in use)")
    return {"message": "Company deleted"}

@router.put("/companies/{comp_id}", response_model=CompanySchema, dependencies=[Depends(require_administrator)])
def update_company(comp_id: int, comp: CompanyBase, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_comp = db.query(Company).filter(Company.id == comp_id).first()
    if not db_comp:
        raise HTTPException(status_code=404, detail="Company not found")
    db_comp.name = comp.name
    db.commit()
    db.refresh(db_comp)
    log_activity(db, current_user.username, "UPDATE_MASTER_DATA", f"Mengubah perusahaan menjadi: {db_comp.name}")
    return db_comp

