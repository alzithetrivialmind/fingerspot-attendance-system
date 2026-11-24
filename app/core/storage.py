import os
import shutil
from fastapi import UploadFile
from pathlib import Path
from app.config import settings

def save_photo(file: UploadFile, employee_id: int) -> str:
    # Ensure storage path exists
    storage_dir = Path(settings.STORAGE_PATH)
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract extension securely
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png"]:
        raise ValueError("Unsupported file extension. Only JPG and PNG are allowed.")
    
    filename = f"emp_{employee_id}{ext}"
    file_path = storage_dir / filename
    
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return str(file_path)
