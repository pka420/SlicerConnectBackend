import json
import gzip
from typing import Dict, List, Any, Optional
from io import BytesIO

class DeltaManager:
    """
    Manages delta encoding/decoding and snapshot strategies.
    Optimizes storage by only saving changed voxels.
    """
    
    # Thresholds for storage decisions
    INLINE_DELTA_MAX_SIZE = 100 * 1024  # 100KB - store in DB directly
    SNAPSHOT_INTERVAL_DELTAS = 50        # Create snapshot every 50 deltas
    SNAPSHOT_INTERVAL_MINUTES = 10       # Or every 10 minutes
    
    @staticmethod
    def create_delta(action: str, voxel_changes: List[Dict], metadata: Dict = None) -> Dict:
        """
        Create a delta object representing changes
        
        Args:
            action: Type of edit ('paint', 'erase', 'smooth', 'fill', etc.)
            voxel_changes: List of changed voxels
                Example: [
                    {"x": 120, "y": 45, "z": 78, "old": 0, "new": 1},
                    {"x": 121, "y": 45, "z": 78, "old": 0, "new": 1}
                ]
            metadata: Optional metadata (brush size, tool settings, etc.)
            
        Returns:
            Dict: Delta object
        """
        delta = {
            "action": action,
            "voxel_changes": voxel_changes,
            "voxel_count": len(voxel_changes),
            "metadata": metadata or {}
        }
        return delta
    
    @staticmethod
    def encode_delta(delta: Dict, compress: bool = True) -> tuple[str, int]:
        """
        Encode delta to JSON string, optionally compressed
        
        Args:
            delta: Delta dictionary
            compress: Whether to gzip compress (for large deltas)
            
        Returns:
            tuple: (encoded_string, size_in_bytes)
        """
        json_str = json.dumps(delta, separators=(',', ':'))  # Compact JSON
        
        if compress and len(json_str) > 10000:  # Compress if > 10KB
            compressed = gzip.compress(json_str.encode('utf-8'))
            # Store as base64 for text column
            import base64
            encoded = base64.b64encode(compressed).decode('ascii')
            return f"gzip:{encoded}", len(compressed)
        
        return json_str, len(json_str)
    
    @staticmethod
    def decode_delta(encoded_str: str) -> Dict:
        """
        Decode delta from stored string
        
        Args:
            encoded_str: Encoded delta string (possibly compressed)
            
        Returns:
            Dict: Delta object
        """
        if encoded_str.startswith("gzip:"):
            # Decompress gzipped delta
            import base64
            compressed = base64.b64decode(encoded_str[5:])
            json_str = gzip.decompress(compressed).decode('utf-8')
        else:
            json_str = encoded_str
        
        return json.loads(json_str)
    
    @staticmethod
    def should_create_snapshot(session_edits_count: int, minutes_since_last: int) -> bool:
        """
        Determine if a snapshot should be created
        
        Args:
            session_edits_count: Number of deltas since last snapshot
            minutes_since_last: Minutes since last snapshot
            
        Returns:
            bool: True if snapshot should be created
        """
        return (
            session_edits_count >= DeltaManager.SNAPSHOT_INTERVAL_DELTAS or
            minutes_since_last >= DeltaManager.SNAPSHOT_INTERVAL_MINUTES
        )
    
    @staticmethod
    def apply_delta_to_array(segmentation_array, delta: Dict):
        """
        Apply delta changes to a numpy array (for reconstruction)
        
        Args:
            segmentation_array: numpy array of segmentation
            delta: Delta object with voxel changes
            
        Returns:
            Modified array (in-place modification)
        """
        for change in delta['voxel_changes']:
            x, y, z = change['x'], change['y'], change['z']
            segmentation_array[x, y, z] = change['new']
        
        return segmentation_array
    
    @staticmethod
    def reconstruct_from_deltas(base_array, deltas: List[Dict]):
        """
        Reconstruct segmentation by applying deltas to base
        
        Args:
            base_array: Base segmentation array (from last snapshot)
            deltas: List of delta objects to apply in order
            
        Returns:
            Reconstructed segmentation array
        """
        import numpy as np
        result = np.copy(base_array)
        
        for delta in deltas:
            DeltaManager.apply_delta_to_array(result, delta)
        
        return result
    
    @staticmethod
    def estimate_delta_size(voxel_count: int) -> int:
        """
        Estimate delta size in bytes
        
        Args:
            voxel_count: Number of voxels changed
            
        Returns:
            int: Estimated size in bytes
        """
        # Rough estimate: each voxel change ~40 bytes in JSON
        # {"x":123,"y":45,"z":78,"old":0,"new":1} = ~38 chars
        return voxel_count * 40


# Storage decision logic example
def save_edit_smart(storage_service, segmentation_id: int, edit_type: str, 
                   data, session_id: Optional[int] = None):
    """
    Example function showing smart storage decisions
    
    Args:
        storage_service: LocalStorageService instance
        segmentation_id: ID of segmentation
        edit_type: 'full_save', 'delta', or 'snapshot'
        data: Either full .nrrd file or delta dict
        session_id: Optional session ID
        
    Returns:
        tuple: (file_path or None, delta_data or None, size_bytes)
    """
    
    if edit_type == 'delta':
        # It's a delta - encode and decide storage
        delta_str, size = DeltaManager.encode_delta(data, compress=True)
        
        if size < DeltaManager.INLINE_DELTA_MAX_SIZE:
            # Store inline in database
            return None, delta_str, size
        else:
            # Save as file (rare - very large delta)
            file_obj = BytesIO(delta_str.encode('utf-8'))
            file_path = storage_service.save_file(
                file_data=file_obj,
                file_type='delta',
                segmentation_id=segmentation_id
            )
            return file_path, None, size
    
    elif edit_type in ['full_save', 'snapshot']:
        # Save full .nrrd file
        file_path = storage_service.save_file(
            file_data=data,
            file_type=edit_type.replace('_save', ''),
            segmentation_id=segmentation_id
        )
        size = storage_service.get_file_size(file_path)
        return file_path, None, size
    
    return None, None, 0
