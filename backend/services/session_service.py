import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pathlib import Path
import zlib
import asyncio
import numpy as np
import base64
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
        
        participants = json.loads(session.participants_json or "[]")
        if user_id != session.started_by_id and user_id not in participants:
            raise ValueError(f"User {user_id} cannot end this session")
        
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

    async def broadcast(self, message: dict, exclude: Optional[WebSocket] = None):
        """Broadcast message to all connections except excluded one"""
        message_text = json.dumps(message)
        dead_connections = set()
        
        for connection in self.connections:
            if connection != exclude:
                try:
                    await connection.send_text(message_text)
                except Exception as e:
                    logger.error(f"Error broadcasting to connection: {e}")
                    dead_connections.add(connection)
        
        # Clean up dead connections
        for connection in dead_connections:
            self.remove_connection(connection)

    async def handle_delta(self, websocket: WebSocket, message: dict):
        """Handle delta update with conflict resolution"""
        user_id = self.user_info[websocket]["user_id"]
        
        async with self.lock:
            try:
                data = message["data"]
                
                # Initialize segmentation if first update
                if self.segmentation is None:
                    self.segmentation = SegmentationState(
                        dimensions=data["dimensions"],
                        spacing=data["spacing"],
                        origin=data["origin"],
                        data_type=data["dataType"]
                    )
                    logger.info(f"Initialized segmentation for session {self.session_id}")
                
                # Decode delta
                compressed_indices = base64.b64decode(data["indices"])
                compressed_values = base64.b64decode(data["values"])
                
                indices_bytes = zlib.decompress(compressed_indices)
                values_bytes = zlib.decompress(compressed_values)
                
                indices = np.frombuffer(indices_bytes, dtype=np.uint16).reshape(-1, 3)
                values = np.frombuffer(values_bytes, dtype=data["dataType"])
                
                # Apply delta
                self.segmentation.apply_delta(indices, values, user_id)
                
                # Broadcast to others
                await self.broadcast(message, exclude=websocket)
                
            except Exception as e:
                logger.error(f"Error handling delta: {e}")
                import traceback
                traceback.print_exc()
                
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Failed to apply delta: {str(e)}"
                }))

    async def handle_full(self, websocket: WebSocket, message: dict):
        """Handle full segmentation update"""
        user_id = self.user_info[websocket]["user_id"]
        
        async with self.lock:
            try:
                data = message["data"]
                
                # Decode full segmentation
                compressed = base64.b64decode(data["imageData"])
                decompressed = zlib.decompress(compressed)
                
                dims = data["dimensions"]
                dtype = data["dataType"]
                encoding = data.get("encoding", "raw")
                
                if encoding == "rle":
                    # Decode run-length encoded data
                    rle_data = json.loads(decompressed.decode('utf-8'))
                    
                    # Expand runs
                    values = np.array(rle_data['values'], dtype=dtype)
                    counts = np.array(rle_data['counts'])
                    flat = np.repeat(values, counts)
                    array = flat.reshape(dims[2], dims[1], dims[0])
                    
                    logger.info(f"Decoded RLE: {len(values)} runs -> {array.size} voxels")
                else:
                    # Decode raw array
                    array = np.frombuffer(decompressed, dtype=dtype)
                    array = array.reshape(dims[2], dims[1], dims[0])
                
                # Update or create segmentation state
                if self.segmentation is None:
                    self.segmentation = SegmentationState(
                        dimensions=dims,
                        spacing=data["spacing"],
                        origin=data["origin"],
                        data_type=dtype
                    )
                
                self.segmentation.update_full(array, user_id)
                
                # Broadcast to others (send the message as-is to preserve encoding)
                await self.broadcast(message, exclude=websocket)
                
            except Exception as e:
                logger.error(f"Error handling full segmentation: {e}")
                import traceback
                traceback.print_exc()
                
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Failed to apply full segmentation: {str(e)}"
                }))



