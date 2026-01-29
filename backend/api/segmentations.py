from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi import Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from database import get_db
from models import User, Project, Segmentation, SegmentationVersion
from .auth import get_current_user
from services.storage_service import get_storage_service
from services.segmentation_service import SegmentationService
from services.permission_service import PermissionService

router = APIRouter(prefix="/segmentations", tags=["Segmentations"])

class SegmentationCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=120)
    color: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$')


class SegmentationResponse(BaseModel):
    id: int
    project_id: int
    name: str
    color: str
    created_by_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    last_editor_id: Optional[int]
    version_count: int = 0
    
    class Config:
        from_attributes = True


class SegmentationDetailResponse(SegmentationResponse):
    creator: dict
    last_editor: Optional[dict]
    latest_version: Optional[dict]
    is_locked: bool = False
    active_session_id: Optional[int] = None


class VersionResponse(BaseModel):
    id: int
    version_number: int
    created_by_id: int
    created_at: datetime
    change_description: Optional[str]
    is_complete_state: bool
    creator: dict
    
    class Config:
        from_attributes = True


@router.post("", response_model=SegmentationResponse, status_code=status.HTTP_201_CREATED)
async def create_segmentation(
    project_id: int = Form(...),
    name: str = Form(...),
    color: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new segmentation in a project with initial 
    
    - **project_id**: ID of the project
    - **name**: Name of the segmentation (e.g., "Tumor", "Liver", "Vessels")
    - **color**: Hex color code for visualization (e.g., "#FF0000" or "#FF0000AA")
    - **file**: file containing the segmentation data
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    print(file.filename)
    print(file)

    perm_service = PermissionService(db)
    if not perm_service.can_edit(current_user, project):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to add segmentations to this project"
        )
    
    if not file.filename.endswith(('.nrrd', 'nii')):
        raise HTTPException(
            status_code=400,
            detail="File must be a .nrrd or .nii file"
        )

    print('working')
    
    new_segmentation = Segmentation(
        project_id=project_id,
        name=name,
        color=color,
        created_by_id=current_user.id
    )
    db.add(new_segmentation)
    db.flush()
    print('working')
    
    seg_service = SegmentationService(db)
    try:
        edit, version = seg_service.save_full_segmentation(
            segmentation_id=new_segmentation.id,
            file_data=file.file,
            original_filename=file.filename,
            user_id=current_user.id,
            change_description="Initial segmentation",
            create_version=True
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save segmentation file: {str(e)}"
        )
    print('working')
    
    db.commit()
    db.refresh(new_segmentation)
    print('working')
    
    return SegmentationResponse(
        **new_segmentation.__dict__,
        version_count=1
    )


@router.get("/{segmentation_id}", response_model=SegmentationDetailResponse)
def get_segmentation(
    segmentation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information about a segmentation
    """
    segmentation = db.query(Segmentation).filter(
        Segmentation.id == segmentation_id
    ).first()
    
    if not segmentation:
        raise HTTPException(status_code=404, detail="Segmentation not found")
    
    # Check permissions
    perm_service = PermissionService(db)
    if not perm_service.can_view(current_user, segmentation.project):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get version count
    version_count = len(segmentation.versions)
    
    # Get latest version
    latest_version = None
    if segmentation.versions:
        latest = sorted(segmentation.versions, key=lambda v: v.version_number, reverse=True)[0]
        latest_version = {
            "id": latest.id,
            "version_number": latest.version_number,
            "created_at": latest.created_at,
            "change_description": latest.change_description
        }
    
    # Check for active session
    from models import CollaborativeSession, SessionStatus
    active_session = db.query(CollaborativeSession).filter(
        CollaborativeSession.segmentation_id == segmentation_id,
        CollaborativeSession.status == SessionStatus.ACTIVE
    ).first()
    
    return SegmentationDetailResponse(
        **segmentation.__dict__,
        version_count=version_count,
        creator={
            "id": segmentation.creator.id,
            "username": segmentation.creator.username
        },
        last_editor={
            "id": segmentation.last_editor.id,
            "username": segmentation.last_editor.username
        } if segmentation.last_editor else None,
        latest_version=latest_version,
        is_locked=segmentation.project.is_locked,
        active_session_id=active_session.id if active_session else None
    )


@router.get("/{segmentation_id}/download")
def download_segmentation(
    segmentation_id: int,
    version_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Download segmentation 
    
    - **version_id**: Optional - download specific version (defaults to latest)
    """
    segmentation = db.query(Segmentation).filter(
        Segmentation.id == segmentation_id
    ).first()
    
    if not segmentation:
        raise HTTPException(status_code=404, detail="Segmentation not found")
    
    perm_service = PermissionService(db)
    if not perm_service.can_view(current_user, segmentation.project):
        raise HTTPException(status_code=403, detail="Access denied")
    
    seg_service = SegmentationService(db)
    storage = get_storage_service()
    
    try:
        if version_id:
            version = db.query(SegmentationVersion).filter(
                SegmentationVersion.id == version_id,
                SegmentationVersion.segmentation_id == segmentation_id
            ).first()
            if not version:
                raise HTTPException(status_code=404, detail="Version not found")
            file_path = version.file_path
            print(file_path)
            filename = file_path.split('/')[-1]
        else:
            data = seg_service.get_segmentation_data(segmentation_id)
            from models import SegmentationEdit, EditType
            latest_edit = db.query(SegmentationEdit).filter(
                SegmentationEdit.segmentation_id == segmentation_id,
                SegmentationEdit.edit_type.in_([EditType.FULL_SAVE, EditType.SNAPSHOT])
            ).order_by(SegmentationEdit.created_at.desc()).first()
            file_path = latest_edit.file_path
            print(file_path)
            filename = file_path.split('/')[-1]
        
        return StreamingResponse(
            storage.get_file_stream(file_path),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Segmentation file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download file: {str(e)}")


@router.get("/{segmentation_id}/versions", response_model=List[VersionResponse])
def get_version_history(
    segmentation_id: int,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get version history for a segmentation
    
    - **limit**: Optional - limit number of versions returned
    """
    segmentation = db.query(Segmentation).filter(
        Segmentation.id == segmentation_id
    ).first()
    
    if not segmentation:
        raise HTTPException(status_code=404, detail="Segmentation not found")
    
    # Check permissions
    perm_service = PermissionService(db)
    if not perm_service.can_view(current_user, segmentation.project):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get versions
    seg_service = SegmentationService(db)
    versions = seg_service.get_version_history(segmentation_id, limit)
    
    # Format response
    return [
        VersionResponse(
            **v.__dict__,
            creator={
                "id": v.creator.id,
                "username": v.creator.username
            }
        )
        for v in versions
    ]

@router.get("/projects/{project_id}", response_model=List[SegmentationResponse])
def list_project_segmentations(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all segmentations in a project
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check permissions
    perm_service = PermissionService(db)
    if not perm_service.can_view(current_user, project):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get segmentations
    segmentations = db.query(Segmentation).filter(
        Segmentation.project_id == project_id
    ).all()
    
    return [
        SegmentationResponse(
            **seg.__dict__,
            version_count=len(seg.versions)
        )
        for seg in segmentations
    ]


