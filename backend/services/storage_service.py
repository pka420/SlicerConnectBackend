import os
import shutil
from pathlib import Path
from typing import BinaryIO, Optional

class LocalStorageService:
    def __init__(self, base_path: str = "storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        for folder in ['segmentations', 'deltas', 'snapshots']:
            (self.base_path / folder).mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, relative_path: str) -> Path:
        return self.base_path / relative_path

    def save_file(self, 
                  file_data: BinaryIO, 
                  file_type: str, 
                  filename: str, 
                  existing_path: Optional[str] = None) -> str:
        
        if existing_path:
            full_path = self._get_full_path(existing_path)
        else:
            subdir_map = {
                'seg': 'segmentations',
                'delta': 'deltas',
                'snapshot': 'snapshots'
            }
            subdir = subdir_map.get(file_type, 'segmentations')
            full_path = self.base_path / subdir / filename

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_data.seek(0)
            with open(full_path, 'wb') as f:
                shutil.copyfileobj(file_data, f)
            
            print(f"File saved successfully: {full_path}")
            return str(full_path.relative_to(self.base_path))
        except Exception as e:
            print(f"Save failed for {filename}: {e}")
            raise

    def get_file(self, relative_path: str) -> BinaryIO:
        full_path = self._get_full_path(relative_path)
        if not full_path.exists():
            print(f"Error: No file found at {full_path}")
            raise FileNotFoundError(f"No file at {full_path}")
        return open(full_path, 'rb')

    def delete_file(self, relative_path: str) -> bool:
        try:
            full_path = self._get_full_path(relative_path)
            if full_path.exists():
                full_path.unlink()
                print(f"File deleted: {full_path}")
                return True
            print(f"Delete skipped: {full_path} does not exist")
            return False
        except Exception as e:
            print(f"Delete failed for {relative_path}: {e}")
            return False

    def exists(self, relative_path: str) -> bool:
        return self._get_full_path(relative_path).exists()

_storage_instance = None

def get_storage_service() -> LocalStorageService:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = LocalStorageService()
    return _storage_instance
