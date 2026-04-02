from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import BinaryIO, List, Dict, Optional, Tuple
from datetime import datetime
from io import BytesIO
import io
import json
import struct
import base64
import zlib
import numpy as np

from models import (
    Segmentation, SegmentationVersion, SegmentationEdit, 
    EditType, User, CollaborativeSession, InMemorySegmentation, Project
)
from services.storage_service import get_storage_service

class SegmentationService:
    """
    Service for managing segmentation operations.
    Handles RAM (InMemorySegmentation) and Disk (StorageService) syncing.
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
        change_description: Optional[str] = None
    ) -> SegmentationEdit:
        """
        Saves the complete segmentation file and logs the edit.
        """
        segmentation = self.db.query(Segmentation).filter(Segmentation.id == segmentation_id).first()
        if not segmentation:
            raise ValueError(f"Segmentation {segmentation_id} not found")

        latest_edit = self.db.query(SegmentationEdit)\
            .filter(SegmentationEdit.segmentation_id == segmentation_id)\
            .filter(SegmentationEdit.file_path.isnot(None))\
            .order_by(desc(SegmentationEdit.created_at))\
            .first()

        target_path = None
        if latest_edit is not None:
            target_path = latest_edit.file_path
            print('target_path: ', target_path)
        
        file_path = self.storage.save_file(
            file_data=file_data,
            file_type='segmentation',
            filename=original_filename,
            existing_path=target_path,
        )

        # hash_edit = Segmentation(
        #     segmentation_id=segmentation_id,
        # )
        # self.db.add(hash_edit)
        # self.db.commit()
        # self.db.refresh(hash_edit)
        # to do: save this hash on db 

        edit = SegmentationEdit(
            segmentation_id=segmentation_id,
            edit_type=EditType.FULL_SAVE,
            file_path=file_path,
            created_by_id=user_id,
            change_description=change_description
        )

        segmentation.updated_at = datetime.utcnow()
        segmentation.last_editor_id = user_id
        
        self.db.add(edit)
        self.db.commit()
        self.db.refresh(edit)
        
        return edit
    
    def get_segmentation_data(self, segmentation_id: int) -> bytes:
        """
        Retrieves the latest physical file data for a segmentation.
        """
        latest_edit = self.db.query(SegmentationEdit).filter(
            SegmentationEdit.segmentation_id == segmentation_id,
            SegmentationEdit.edit_type.in_([EditType.FULL_SAVE, EditType.SNAPSHOT])
        ).order_by(desc(SegmentationEdit.created_at)).first()

        print('found latest_edit at: ', latest_edit.file_path)
        
        if not latest_edit or not latest_edit.file_path:
            raise ValueError(f"No file data found for segmentation {segmentation_id}")
            
        file_handle = self.storage.get_file(latest_edit.file_path)
    
        try:
            data = file_handle.read()
            return data
        finally:
            file_handle.close() 

    def sync_ram_to_disk(self, project_id: int, user_id: int):
        """
        Bridge: Persists current RAM state (Voxels + Metadata) to Disk.
        """
        session = InMemorySegmentation.get_session(project_id)
        if session is None:
            return None

        segmentation = self.get_or_create_segmentation(project_id, self.db, user_id)

        data_to_save = {
            "array": session["array"],
            "metadata": session["metadata"]
        }

        buffer = io.BytesIO()
        np.save(buffer, data_to_save)
        buffer.seek(0)

        return self.save_full_segmentation(
            segmentation_id=segmentation.id,
            file_data=buffer,
            original_filename=f"session_{project_id}_sync.npy",
            user_id=user_id,
            change_description="Automatic session sync with spatial metadata"
        )

    def load_disk_to_ram(self, project_id: int, segmentation_id: int):
        """
        Bridge: Loads the latest file from disk back into the live RAM session.
        """
        try:
            file_bytes = self.get_segmentation_data(segmentation_id)
            loaded_data = np.load(io.BytesIO(file_bytes), allow_pickle=True).item()

            if isinstance(loaded_data, dict) and "array" in loaded_data:
                InMemorySegmentation.set_full(
                    project_id, 
                    loaded_data["array"], 
                    loaded_data["metadata"]
                )
            else:
                print("DEBUG: Loading legacy .npy file without metadata")
                default_meta = {
                    "dimensions": list(reversed(loaded_data.shape)),
                    "spacing": [1.0, 1.0, 1.0],
                    "origin": [0.0, 0.0, 0.0],
                    "direction": [1,0,0, 0,1,0, 0,0,1, 0,0,0, 1], 
                    "dataType": str(loaded_data.dtype)
                }
                InMemorySegmentation.set_full(project_id, loaded_data, default_meta)

            return True
        except Exception as e:
            print(f"DEBUG: Failed to load state from disk: {e}")
            return False

    def get_or_create_segmentation(self, project_id: int, db: Session, user_id: int) -> Segmentation:
        """
        Helper to find the master segmentation record or create one if this is a new project.
        """
        session_rec = db.query(CollaborativeSession).filter(CollaborativeSession.project_id == project_id).first()
        if not session_rec:
            raise ValueError(f"Session {project_id} does not exist.")

        segmentation = db.query(Segmentation).filter(Segmentation.project_id == session_rec.project_id).first()

        if not segmentation:
            print(f"DEBUG: Creating initial Segmentation record for Project {session_rec.project_id}")
            segmentation = Segmentation(
                project_id=session_rec.project_id,
                name=f"Segmentation_{session_rec.project_id}",
                created_by_id=user_id,
                color="#FF0000FF"
            )
            db.add(segmentation)
            db.flush() 
            
        return segmentation


    def handle_delta(self, message: dict, project_id: int, user_id: int, db: Session):
        try:
            data = message["data"]
            metadata = {
                "dimensions": data["dimensions"],
                "spacing": data["spacing"],
                "origin": data["origin"],
                "direction": data.get("direction"), 
                "dataType": data["dataType"]
            }

            dtype = data["dataType"]
            
            # Decode Indices: Result is an (N, 3) array where columns are [Z, Y, X]
            indices = np.frombuffer(
                zlib.decompress(base64.b64decode(data["indices"])), 
                dtype=np.uint16
            ).reshape(-1, 3)
            
            values = np.frombuffer(
                zlib.decompress(base64.b64decode(data["values"])), 
                dtype=dtype
            )

            InMemorySegmentation.apply_delta(project_id, indices, values, metadata)


        except Exception as e:
            db.rollback()
            import traceback
            traceback.print_exc()
            return False, str(e)

        return True, None

    def handle_full(self, message: dict, project_id: int, user_id: int, db: Session):
        try:
            data = message["data"]
            metadata = {
                    "dimensions": data["dimensions"],
                    "spacing": data["spacing"],
                    "origin": data["origin"],
                    "direction": data["direction"],
                    "dataType": data["dataType"]
                    }
            dims = (metadata["dimensions"][2], metadata["dimensions"][1], metadata["dimensions"][0])
            dtype = data["dataType"]
            compressed = base64.b64decode(data["imageData"])
            decompressedRaw = zlib.decompress(compressed)
            seg_array = np.frombuffer(decompressedRaw, dtype=dtype).reshape(dims)

            InMemorySegmentation.set_full(project_id, seg_array, metadata)

            segmentation = db.query(Segmentation).join(
                Project, Segmentation.project_id == Project.id
            ).join(
                CollaborativeSession, CollaborativeSession.project_id == Project.id
            ).filter(
                CollaborativeSession.id == project_id
            ).first()

            # if segmentation:
            #     edit = SegmentationEdit(
            #         segmentation_id=segmentation.id,
            #         edit_type=EditType.FULL_SAVE,
            #         delta_data=None,
            #         created_by_id=user_id,
            #         client_timestamp=message.get("timestamp"),
            #         change_description="full segmentation sync"
            #     )
            #     db.add(edit)
            #     db.commit()
            # should I save and fill up db or not?

            return True, None

        except Exception as e:
            db.rollback()
            print(str(e))
            return False, str(e)
