from sqlalchemy.orm import Session
from typing import Optional

from models import User, Project, Segmentation, ProjectCollaborator, UserRole


class PermissionService:
    """
    Service for checking user permissions on projects
    Centralizes all permission logic.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def can_edit(self, user: User, project: Project) -> bool:
        """
        Check if user can edit a project
        
        Args:
            user: User object
            project: Project object
            
        Returns:
            bool: True if user can edit
        """
        # Owner can always edit
        if project.owner_id == user.id:
            return True
        
        # Check if user is a collaborator with edit permissions
        collaborator = self.db.query(ProjectCollaborator).filter(
            ProjectCollaborator.project_id == project.id,
            ProjectCollaborator.user_id == user.id
        ).first()
        
        if collaborator:
            # EDITOR and OWNER roles can edit
            return collaborator.role in [UserRole.EDITOR, UserRole.OWNER]
        
        return False
    
    def can_view(self, user: User, project: Project) -> bool:
        """
        Check if user can view a project
        
        Args:
            user: User object
            project: Project object
            
        Returns:
            bool: True if user can view
        """
        # Owner can always view
        if project.owner_id == user.id:
            return True
        
        # Check if user is a collaborator (all roles can view)
        collaborator = self.db.query(ProjectCollaborator).filter(
            ProjectCollaborator.project_id == project.id,
            ProjectCollaborator.user_id == user.id
        ).first()
        
        return collaborator is not None
    
    def can_start_session(self, user: User, project: Project) -> bool:
        """
        Check if user can start a collaborative session on a Project
        
        Args:
            user: User object
            project: Project object
            
        Returns:
            bool: True if user can start session
        """
        # Must be able to edit the project
        if not self.can_edit(user, project):
            return False
        
        # Check if project is locked
        if project.is_locked:
            # Only the user who locked it can start a session
            return project.locked_by_id == user.id
        
        return True
    
    def can_comment(self, user: User, project: Project) -> bool:
        """
        Check if user can add comments to a project
        
        Args:
            user: User object
            project: Project object
            
        Returns:
            bool: True if user can comment
        """
        # Owner can always comment
        if project.owner_id == user.id:
            return True
        
        # Check collaborator role
        collaborator = self.db.query(ProjectCollaborator).filter(
            ProjectCollaborator.project_id == project.id,
            ProjectCollaborator.user_id == user.id
        ).first()
        
        if collaborator:
            # EDITOR, REVIEWER, and OWNER can comment
            return collaborator.role in [UserRole.EDITOR, UserRole.REVIEWER, UserRole.OWNER]
        
        return False
    
    def can_delete(self, user: User, project: Project) -> bool:
        """
        Check if user can delete a project
        
        Args:
            user: User object
            project: Project object
            
        Returns:
            bool: True if user can delete
        """
        # Only owner can delete
        return project.owner_id == user.id
    
    def can_manage_collaborators(self, user: User, project: Project) -> bool:
        """
        Check if user can add/remove collaborators
        
        Args:
            user: User object
            project: Project object
            
        Returns:
            bool: True if user can manage collaborators
        """
        # Only owner can manage collaborators
        return project.owner_id == user.id
    
    def get_user_role(self, user: User, project: Project) -> Optional[UserRole]:
        """
        Get user's role in a project
        
        Args:
            user: User object
            project: Project object
            
        Returns:
            UserRole or None if user has no access
        """
        # Check if owner
        if project.owner_id == user.id:
            return UserRole.OWNER
        
        # Check collaborator role
        collaborator = self.db.query(ProjectCollaborator).filter(
            ProjectCollaborator.project_id == project.id,
            ProjectCollaborator.user_id == user.id
        ).first()
        
        return collaborator.role if collaborator else None
    
    def can_join_session(self, user: User, session_id: int) -> bool:
        """
        Check if user can join a collaborative session
        
        Args:
            user: User object
            session_id: ID of collaborative session
            
        Returns:
            bool: True if user can join
        """
        from models import CollaborativeSession
        
        session = self.db.query(CollaborativeSession).get(session_id)
        if not session:
            return False
        
        project = session.project
        
        # Must be able to edit the project
        return self.can_edit(user, project)


