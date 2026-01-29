import os
import shutil
import logging
from pathlib import Path
from typing import BinaryIO, Optional, Generator
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

STORAGE_BASE_PATH = os.getenv("STORAGE_PATH", "./storage")


class LocalStorageService:
    
    SUPPORTED_EXTENSIONS = {'.nrrd', '.nii', '.nii.gz'}
    
    def __init__(self, base_path: str = STORAGE_BASE_PATH):
        self.base_path = Path(base_path).resolve()
        self._ensure_directories()
        logger.info(f"LocalStorageService initialized at: {self.base_path}")
    
    def _ensure_directories(self):
        directories = [
            'segmentations',
            'deltas',
            'snapshots',
            'temp',
            'versions'
        ]
        for dir_name in directories:
            dir_path = self.base_path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {dir_path}")
    
    @staticmethod
    def _get_file_extension(filename: str) -> str:
        filename_lower = filename.lower()
        if filename_lower.endswith('.nii.gz'):
            return '.nii.gz'
        return Path(filename).suffix.lower()
    
    @staticmethod
    def validate_file_extension(filename: str) -> bool:
        ext = LocalStorageService._get_file_extension(filename)
        return ext in LocalStorageService.SUPPORTED_EXTENSIONS
    
    def _generate_filename(self, file_type: str, segmentation_id: int, 
                          version: Optional[int] = None,
                          original_extension: str = '.nii') -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        
        if file_type == 'delta':
            ext = '.json'
        else:
            ext = original_extension
        
        version_str = f"_v{version}" if version is not None else ""
        
        return f"seg_{segmentation_id}{version_str}_{file_type}_{timestamp}{ext}"
    
    def save_file(self, file_data: BinaryIO, file_type: str, 
                  segmentation_id: int, version: Optional[int] = None,
                  original_filename: Optional[str] = None,
                  metadata: dict = None) -> str:
        subdir_map = {
            'seg': 'segmentations',
            'delta': 'deltas',
            'snapshot': 'snapshots',
            'version': 'versions'
        }
        subdir = subdir_map.get(file_type, 'segmentations')
        
        if original_filename:
            extension = self._get_file_extension(original_filename)
            if file_type != 'delta' and not self.validate_file_extension(original_filename):
                raise ValueError(
                    f"Unsupported file extension: {extension}. "
                    f"Supported extensions: {', '.join(self.SUPPORTED_EXTENSIONS)}"
                )
            print('found ext ', extension)
        else:
            extension = '.nii'
        
        filename = self._generate_filename(file_type, segmentation_id, version, extension)
        full_path = self.base_path / subdir / filename

        print('filename: ', filename)
        print('full_path: ', full_path)
        
        try:
            with open(full_path, 'wb') as f:
                shutil.copyfileobj(file_data, f)
            
            file_size = full_path.stat().st_size
            logger.info(f"Saved file: {filename} ({file_size} bytes)")
            
            if metadata:
                logger.debug(f"File metadata: {metadata}")
            
        except Exception as e:
            logger.error(f"Failed to save file {filename}: {e}")
            raise
        
        return f"{subdir}/{filename}"
    
    def get_file(self, file_path: str) -> bytes:
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(full_path, 'rb') as f:
                content = f.read()
            logger.debug(f"Read file: {file_path} ({len(content)} bytes)")
            return content
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            raise
    
    def get_file_stream(self, file_path: str, chunk_size: int = 8192) -> Generator[bytes, None, None]:
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(full_path, 'rb') as f:
                while chunk := f.read(chunk_size):
                    yield chunk
        except Exception as e:
            logger.error(f"Failed to stream file {file_path}: {e}")
            raise
    
    def delete_file(self, file_path: str) -> bool:
        full_path = self.base_path / file_path
        
        try:
            if full_path.exists():
                full_path.unlink()
                logger.info(f"Deleted file: {file_path}")
                return True
            else:
                logger.warning(f"File not found for deletion: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return False
    
    def file_exists(self, file_path: str) -> bool:
        full_path = self.base_path / file_path
        return full_path.exists()
    
    def get_full_path(self, file_path: str) -> Path:
        return self.base_path / file_path
    
    def get_file_size(self, file_path: str) -> int:
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        return full_path.stat().st_size
    
    def get_storage_stats(self) -> dict:
        stats = {
            'total_size': 0,
            'file_count': 0,
            'by_type': {}
        }
        
        for subdir in ['segmentations', 'deltas', 'snapshots', 'versions', 'temp']:
            dir_path = self.base_path / subdir
            if not dir_path.exists():
                continue
            
            dir_size = 0
            file_count = 0
            
            for file_path in dir_path.rglob('*'):
                if file_path.is_file():
                    size = file_path.stat().st_size
                    dir_size += size
                    file_count += 1
            
            stats['by_type'][subdir] = {
                'size': dir_size,
                'count': file_count
            }
            stats['total_size'] += dir_size
            stats['file_count'] += file_count
        
        logger.info(f"Storage stats: {stats['file_count']} files, "
                   f"{stats['total_size'] / (1024**3):.2f} GB")
        
        return stats
    
    def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        temp_dir = self.base_path / 'temp'
        if not temp_dir.exists():
            return 0
        
        deleted_count = 0
        cutoff_time = datetime.utcnow().timestamp() - (max_age_hours * 3600)
        
        for file_path in temp_dir.iterdir():
            if file_path.is_file():
                if file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        logger.debug(f"Cleaned up temp file: {file_path.name}")
                    except Exception as e:
                        logger.error(f"Failed to delete temp file {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} temporary files")
        
        return deleted_count


_storage_instance = None

def get_storage_service() -> LocalStorageService:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = LocalStorageService()
    return _storage_instance
