from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import BinaryIO, List, Dict, Optional, Tuple
from datetime import datetime
from io import BytesIO
import json
import struct
import base64
import zlib
import numpy as np

from models import (
    Segmentation, SegmentationVersion, SegmentationEdit, 
    EditType, User, CollaborativeSession
)
from services.storage_service import get_storage_service

class SegmentationService:
    """
    Service for managing segmentation operations.
    Handles both REST (full saves) and WebSocket (openIGTLink) workflows.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.storage = get_storage_service()
    
    def save_full_segmentation(
        self,
        segmentation_id: int,
        file_data: BinaryIO,
        original_filename: str,
        user_id: int,
        change_description: Optional[str] = None,
        create_version: bool = True,
        session_id: Optional[int] = None
    ) -> Tuple[SegmentationEdit, Optional[SegmentationVersion]]:
        """
        Save complete segmentation file 
        Args:
            segmentation_id: ID of segmentation
            file_data: Binary file data 
            user_id: ID of user saving
            change_description: Optional description of changes
            create_version: Whether to create a new version entry
            session_id: Optional collaborative session ID
        Returns:
            Tuple of (SegmentationEdit, SegmentationVersion or None)
        """
        segmentation = self.db.query(Segmentation).filter(
            Segmentation.id == segmentation_id
        ).first()
        
        if not segmentation:
            raise ValueError(f"Segmentation {segmentation_id} not found")
        
        file_path = self.storage.save_file(
            file_data=file_data,
            file_type='segmentation',
            original_filename=original_filename,
            segmentation_id=segmentation_id,
            metadata={'user_id': user_id, 'type': 'full_save'}
        )
        
        file_size = self.storage.get_file_size(file_path)

        print('file_size: ', file_size)
        print('file_path: ', file_path)
        
        edit = SegmentationEdit(
            segmentation_id=segmentation_id,
            edit_type=EditType.FULL_SAVE,
            file_path=file_path,
            created_by_id=user_id,
            session_id=session_id,
            change_description=change_description
        )
        self.db.add(edit)
        
        segmentation.updated_at = datetime.utcnow()
        segmentation.last_editor_id = user_id
        
        version = None
        if create_version:
            version = self.create_version(
                segmentation_id=segmentation_id,
                user_id=user_id,
                file_path=file_path,
                change_description=change_description,
                is_complete_state=True
            )
        
        self.db.commit()
        self.db.refresh(edit)
        if version:
            self.db.refresh(version)
        
        return edit, version
    
    def get_segmentation_data(
        self,
        segmentation_id: int,
        version_id: Optional[int] = None
    ) -> bytes:
        """
        Get segmentation file data
        
        Args:
            segmentation_id: ID of segmentation
            version_id: Optional specific version ID (defaults to latest)
            
        Returns:
            bytes: Segmentation file data
        """
        if version_id:
            version = self.db.query(SegmentationVersion).filter(
                SegmentationVersion.id == version_id,
                SegmentationVersion.segmentation_id == segmentation_id
            ).first()
            
            if not version:
                raise ValueError(f"Version {version_id} not found")
            
            file_path = version.file_path
        else:
            latest_edit = self.db.query(SegmentationEdit).filter(
                SegmentationEdit.segmentation_id == segmentation_id,
                SegmentationEdit.edit_type.in_([EditType.FULL_SAVE, EditType.SNAPSHOT])
            ).order_by(desc(SegmentationEdit.created_at)).first()
            
            if not latest_edit:
                raise ValueError(f"No data found for segmentation {segmentation_id}")
            
            file_path = latest_edit.file_path
        
        return self.storage.get_file(file_path)

    def handle_delta(self, message: dict):
        """Handle delta update with conflict resolution"""
        try:
            data = message["data"]
            dims = data["dimensions"]
            dtype = data["dataType"]

            compressed = base64.b64decode(data["imageData"])
            decompressedRaw = zlib.decompress(compressed)
            delta_array = np.frombuffer(decompressedRaw, dtype=dtype).reshape(dims)

            print(delta_array)
            # apply delta and save logs in db
            
        except Exception as e:
            print(str(e))

    def handle_full(self, message: dict):
        """Handle full segmentation update
            Read the whole segmentation
            and create another message to relay to everyone.
            

            I want to save this seg locally for future and also send to others.
            What do I need?
            save the reference in db? - need project_id, created_by_id etc.
            save the actual file on server?
        """
        try:
            data = message["data"]
            dims = data["dimensions"]
            dtype = data["dataType"]

            compressed = base64.b64decode(data["imageData"])
            decompressedRaw = zlib.decompress(compressed)
            seg_array = np.frombuffer(decompressedRaw, dtype=dtype).reshape(dims)

            # save logs in db
            # save actual seg in files somewhere...

            return True, None
            
        except Exception as e:
            print(str(e))
            return False, str(e)


