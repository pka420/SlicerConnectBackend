from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from pydantic import BaseModel, Field
from datetime import datetime

from database import get_db
from models import User, Project, ProjectCollaborator, UserRole
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

    # Build collaborators list
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

    # Build locked_by info
    locked_by = None
    if project.locked_by_id:
        locker = db.query(User).get(project.locked_by_id)
        if locker:
            locked_by = {"id": locker.id, "username": locker.username}

    # Return response - construct manually to avoid __dict__ conflicts
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
