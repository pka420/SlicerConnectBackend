import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import json
from models import (
    CollaborativeSession, SessionStatus, Project, User
)


class SessionService:
    """
    Service for managing collaborative editing sessions.
    Handles session lifecycle and participant management.
    Sessions are now associated with projects, not individual segmentations.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def start_session(
        self,
        project_id: int,
        user_id: int,
        session_name: Optional[str] = None
    ) -> CollaborativeSession:
        """
        Start a new collaborative editing session for a project
        
        Args:
            project_id: ID of project to edit
            user_id: ID of user starting the session
            session_name: Optional name for the session
            
        Returns:
            CollaborativeSession record
        """
        existing_session = self.db.query(CollaborativeSession).filter(
            CollaborativeSession.project_id == project_id,
            CollaborativeSession.status == SessionStatus.ACTIVE
        ).first()
        
        if existing_session:
            return existing_session
        
        session = CollaborativeSession(
            project_id=project_id,
            started_by_id=user_id,
            status=SessionStatus.ACTIVE,
            session_name=session_name,
            participants_json=json.dumps([user_id])  # Creator is first participant
        )
        
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        
        return session
    
    def end_session(
        self,
        session_id: int,
        user_id: int
    ) -> CollaborativeSession:
        """
        End a collaborative editing session
        
        Args:
            session_id: ID of session to end
            user_id: ID of user ending the session
            
        Returns:
            Updated CollaborativeSession record
            
        Raises:
            ValueError: If session not found or already ended
        """
        session = self.db.query(CollaborativeSession).get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if session.status != SessionStatus.ACTIVE:
            raise ValueError(f"Session {session_id} is not active")
        
        # Only session creator or participants can end it
        participants = json.loads(session.participants_json or "[]")
        if user_id != session.started_by_id and user_id not in participants:
            raise ValueError(f"User {user_id} cannot end this session")
        
        # Update session
        session.status = SessionStatus.ENDED
        session.ended_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(session)
        
        return session
    
    def add_participant(
        self,
        session_id: int,
        user_id: int
    ) -> CollaborativeSession:
        """
        Add a participant to an active session
        
        Args:
            session_id: ID of session
            user_id: ID of user to add
            
        Returns:
            Updated CollaborativeSession record
        """
        session = self.db.query(CollaborativeSession).get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if session.status != SessionStatus.ACTIVE:
            raise ValueError(f"Cannot add participant to inactive session")
        
        # Get current participants
        participants = json.loads(session.participants_json or "[]")
        
        # Add user if not already in list
        if user_id not in participants:
            participants.append(user_id)
            session.participants_json = json.dumps(participants)
            self.db.commit()
            self.db.refresh(session)
        
        return session
    
    def remove_participant(
        self,
        session_id: int,
        user_id: int
    ) -> CollaborativeSession:
        """
        Remove a participant from a session
        
        Args:
            session_id: ID of session
            user_id: ID of user to remove
            
        Returns:
            Updated CollaborativeSession record
        """
        session = self.db.query(CollaborativeSession).get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Cannot remove the session creator
        if user_id == session.started_by_id:
            raise ValueError("Cannot remove session creator")
        
        # Get current participants
        participants = json.loads(session.participants_json or "[]")
        
        # Remove user if in list
        if user_id in participants:
            participants.remove(user_id)
            session.participants_json = json.dumps(participants)
            self.db.commit()
            self.db.refresh(session)
        
        return session
    
    def get_active_sessions(
        self,
        project_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> List[CollaborativeSession]:
        """
        Get active collaborative sessions
        
        Args:
            project_id: Optional filter by project
            user_id: Optional filter by participant
            
        Returns:
            List of active CollaborativeSession records
        """
        query = self.db.query(CollaborativeSession).filter(
            CollaborativeSession.status == SessionStatus.ACTIVE
        )
        
        if project_id:
            query = query.filter(
                CollaborativeSession.project_id == project_id
            )
        
        if user_id:
            # Filter sessions where user is a participant
            all_sessions = query.all()
            filtered_sessions = []
            for session in all_sessions:
                participants = json.loads(session.participants_json or "[]")
                if user_id in participants or user_id == session.started_by_id:
                    filtered_sessions.append(session)
            return filtered_sessions
        
        return query.all()
    
    def get_session_by_project(
        self,
        project_id: int
    ) -> Optional[CollaborativeSession]:
        """
        Get active session for a specific project
        
        Args:
            project_id: ID of project
            
        Returns:
            Active CollaborativeSession or None
        """
        return self.db.query(CollaborativeSession).filter(
            CollaborativeSession.project_id == project_id,
            CollaborativeSession.status == SessionStatus.ACTIVE
        ).first()
    
    def get_session_participants(
        self,
        session_id: int
    ) -> List[User]:
        """
        Get all participants in a session
        
        Args:
            session_id: ID of session
            
        Returns:
            List of User records
        """
        session = self.db.query(CollaborativeSession).get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        participant_ids = json.loads(session.participants_json or "[]")
        
        return self.db.query(User).filter(
            User.id.in_(participant_ids)
        ).all()
    
    def is_user_in_session(
        self,
        session_id: int,
        user_id: int
    ) -> bool:
        """
        Check if user is a participant in session
        
        Args:
            session_id: ID of session
            user_id: ID of user
            
        Returns:
            bool: True if user is in session
        """
        session = self.db.query(CollaborativeSession).get(session_id)
        if not session:
            return False
        
        participants = json.loads(session.participants_json or "[]")
        return user_id in participants or user_id == session.started_by_id
    
    def has_active_session(
        self,
        project_id: int
    ) -> bool:
        """
        Check if a project has an active session
        
        Args:
            project_id: ID of project
            
        Returns:
            bool: True if project has an active session
        """
        session = self.get_session_by_project(project_id)
        return session is not None
