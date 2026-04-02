from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from pydantic import BaseModel, Field
from datetime import datetime

from database import get_db
from models import User, Project, ProjectCollaborator, UserRole, Segmentation
from .auth import get_current_user  

router = APIRouter(prefix="/projects", tags=["Projects"])

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    created_at: datetime
    updated_at: datetime | None
    is_locked: bool
    locked_by_id: int | None
    locked_at: datetime | None

    class Config:
        from_attributes = True


class ProjectListItem(BaseModel):
    id: int
    name: str
    description: str | None
    role: str           
    created_at: datetime
    updated_at: datetime | None
    is_locked: bool
    locked_by_username: str | None = None

    class Config:
        from_attributes = True


class ProjectDetailResponse(ProjectResponse):
    owner: dict  
    locked_by: dict | None  
    collaborators: List[dict]  
    segmentation_count: int = 0


class CollaboratorAdd(BaseModel):
    user_id: int
    role: str = Field(default="viewer")  


class CollaboratorUpdate(BaseModel):
    role: str  


class CollaboratorResponse(BaseModel):
    user_id: int
    username: str
    role: str
    added_at: datetime
    
    class Config:
        from_attributes = True


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new project - current user becomes owner"""
    new_project = Project(
        name=project_in.name,
        description=project_in.description,
        owner_id=current_user.id
    )
    db.add(new_project)
    db.commit()

    db.refresh(new_project)
    return new_project


@router.get("", response_model=List[ProjectListItem])
def list_my_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all projects where current user is owner or collaborator"""
    owned = db.query(Project).filter(Project.owner_id == current_user.id).all()
    shared = (
        db.query(Project)
        .join(ProjectCollaborator)
        .filter(ProjectCollaborator.user_id == current_user.id)
        .all()
    )
    all_projects = {p.id: p for p in owned + shared}.values()

    result = []
    for project in all_projects:
        role = "owner" if project.owner_id == current_user.id else "unknown"

        if role == "unknown":
            collab = (
                db.query(ProjectCollaborator)
                .filter_by(project_id=project.id, user_id=current_user.id)
                .first()
            )
            if collab:
                role = collab.role.value  

        locked_by_username = None
        if project.is_locked and project.locked_by_id:
            locker = db.query(User).get(project.locked_by_id)
            locked_by_username = locker.username if locker else None

        result.append(
            ProjectListItem(
                id=project.id,
                name=project.name,
                description=project.description,
                role=role,
                created_at=project.created_at,
                updated_at=project.updated_at,
                is_locked=project.is_locked,
                locked_by_username=locked_by_username,
            )
        )

    result.sort(key=lambda x: x.updated_at or x.created_at, reverse=True)
    return result

@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project_detail(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed information about a specific project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    is_owner = project.owner_id == current_user.id
    is_collaborator = (
        db.query(ProjectCollaborator)
        .filter_by(project_id=project.id, user_id=current_user.id)
        .first()
        is not None
    )

    if not (is_owner or is_collaborator):
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this project"
        )

    collaborators_list = []
    for collab in project.collaborators:
        collaborators_list.append({
            "user": {
                "id": collab.user.id,
                "username": collab.user.username,
            },
            "role": collab.role.value,
            "added_at": collab.added_at,
        })

    locked_by = None
    if project.locked_by_id:
        locker = db.query(User).get(project.locked_by_id)
        if locker:
            locked_by = {"id": locker.id, "username": locker.username}

    return ProjectDetailResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        owner_id=project.owner_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        is_locked=project.is_locked,
        locked_by_id=project.locked_by_id,
        locked_at=project.locked_at,
        owner={"id": project.owner.id, "username": project.owner.username},
        locked_by=locked_by,
        collaborators=collaborators_list,
        segmentation_count=len(project.segmentations),
    )



@router.post("/{project_id}/collaborators", response_model=CollaboratorResponse, status_code=status.HTTP_201_CREATED)
def add_collaborator(
    project_id: int,
    collaborator_data: CollaboratorAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add a user as a collaborator to the project.
    Only project owners can add collaborators.
    """
    print(collaborator_data)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only project owner can add collaborators"
        )
    
    try:
        role_enum = UserRole(collaborator_data.role.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join([r.value for r in UserRole])}"
        )
    
    target_user = db.query(User).filter(User.id == collaborator_data.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if target_user.id == project.owner_id:
        detail="Project owner is already part of the project"
        print(detail)
        raise HTTPException(
            status_code=400,
            detail="Project owner is already part of the project"
        )
    
    existing = (
        db.query(ProjectCollaborator)
        .filter_by(project_id=project_id, user_id=collaborator_data.user_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="User is already a collaborator on this project"
        )
    
    new_collab = ProjectCollaborator(
        user_id=collaborator_data.user_id,
        project_id=project_id,
        role=role_enum
    )
    db.add(new_collab)
    db.commit()
    db.refresh(new_collab)
    
    return CollaboratorResponse(
        user_id=new_collab.user_id,
        username=target_user.username,
        role=new_collab.role.value,
        added_at=new_collab.added_at
    )


@router.get("/{project_id}/collaborators", response_model=List[CollaboratorResponse])
def list_collaborators(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all collaborators for a project.
    Only accessible to project owner and collaborators.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    is_owner = project.owner_id == current_user.id
    is_collaborator = (
        db.query(ProjectCollaborator)
        .filter_by(project_id=project_id, user_id=current_user.id)
        .first()
        is not None
    )
    
    if not (is_owner or is_collaborator):
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this project"
        )
    
    collaborators = (
        db.query(ProjectCollaborator)
        .filter(ProjectCollaborator.project_id == project_id)
        .all()
    )
    
    result = []
    for collab in collaborators:
        result.append(
            CollaboratorResponse(
                user_id=collab.user_id,
                username=collab.user.username,
                role=collab.role.value,
                added_at=collab.added_at
            )
        )
    
    return result


@router.patch("/{project_id}/collaborators/{user_id}", response_model=CollaboratorResponse)
def update_collaborator_role(
    project_id: int,
    user_id: int,
    role_update: CollaboratorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a collaborator's role in the project.
    Only project owner can update roles.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only project owner can update collaborator roles"
        )
    
    try:
        role_enum = UserRole(role_update.role.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join([r.value for r in UserRole])}"
        )
    
    collaborator = (
        db.query(ProjectCollaborator)
        .filter_by(project_id=project_id, user_id=user_id)
        .first()
    )
    
    if not collaborator:
        raise HTTPException(
            status_code=404,
            detail="Collaborator not found in this project"
        )
    
    collaborator.role = role_enum
    db.commit()
    db.refresh(collaborator)
    
    return CollaboratorResponse(
        user_id=collaborator.user_id,
        username=collaborator.user.username,
        role=collaborator.role.value,
        added_at=collaborator.added_at
    )


@router.delete("/{project_id}/collaborators/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_collaborator(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Remove a collaborator from the project.
    Only project owner can remove collaborators.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only project owner can remove collaborators"
        )
    
    collaborator = (
        db.query(ProjectCollaborator)
        .filter_by(project_id=project_id, user_id=user_id)
        .first()
    )
    
    if not collaborator:
        raise HTTPException(
            status_code=404,
            detail="Collaborator not found in this project"
        )
    
    db.delete(collaborator)
    db.commit()
    
    return None
