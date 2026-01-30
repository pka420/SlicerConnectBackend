from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException, status
from typing import Dict, Set, List, Optional
import json
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from models import User, CollaborativeSession, SessionStatus, Segmentation, Project
from .auth import get_current_user
from services.session_service import SessionService
from services.segmentation_service import SegmentationService
from services.permission_service import PermissionService

router = APIRouter(prefix="/collaboration", tags=["Collaboration"])

class ConnectionManager:
    """
    Manages WebSocket connections for collaborative sessions
    """
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        self.user_mapping: Dict[WebSocket, int] = {}
    
    async def connect(self, websocket: WebSocket, session_id: int, user_id: int):
        """Accept and register a new connection"""
        await websocket.accept()
        
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        
        self.active_connections[session_id].add(websocket)
        self.user_mapping[websocket] = user_id
    
    def disconnect(self, websocket: WebSocket, session_id: int):
        """Remove a connection"""
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        
        if websocket in self.user_mapping:
            del self.user_mapping[websocket]
    
    async def broadcast(self, session_id: int, message: dict, exclude: WebSocket = None):
        """Broadcast message to all connections in a session"""
        if session_id not in self.active_connections:
            return
        
        dead_connections = set()
        for connection in self.active_connections[session_id]:
            if connection == exclude:
                continue
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.add(connection)
        
        # Clean up dead connections
        for connection in dead_connections:
            self.disconnect(connection, session_id)
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to a specific connection"""
        try:
            await websocket.send_json(message)
        except Exception:
            pass
    
    def get_session_users(self, session_id: int) -> Set[int]:
        """Get all user IDs in a session"""
        if session_id not in self.active_connections:
            return set()
        
        users = set()
        for connection in self.active_connections[session_id]:
            if connection in self.user_mapping:
                users.add(self.user_mapping[connection])
        return users


manager = ConnectionManager()



class SessionStartRequest(BaseModel):
    project_id: int
    session_name: Optional[str] = None

@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def start_collaborative_session(
    request: SessionStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start a new collaborative editing session
    Returns session_id and WebSocket URL to connect to
    """
    project = db.query(Project).get(request.project_id)
    
    perm_service = PermissionService(db)
    if not perm_service.can_start_session(current_user, project):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to start a session on this segmentation"
        )
    
    session_service = SessionService(db)
    try:
        session = session_service.start_session(
            project_id=request.project_id,
            user_id=current_user.id,
            session_name=request.session_name
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "session_id": session.id,
        "project_id": session.project_id,
        "started_at": session.started_at,
        "websocket_url": f"/api/collaboration/sessions/{session.id}/ws"
    }

@router.websocket("/sessions/{session_id}/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    WebSocket endpoint for real-time collaborative editing
    
    Connect with: ws://localhost:8000/api/collaboration/sessions/{session_id}/ws?token={jwt_token}
    
    Message Types:
    - delta: Segmentation changes
    - cursor: Cursor position updates
    - chat: Chat messages
    - ping: Keep-alive
    """
    try:
        current_user: User = get_current_user(token, db)
    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=401, detail=str(e))

    session = db.query(CollaborativeSession).filter(
        CollaborativeSession.id == session_id
    ).first()
    perm_service = PermissionService(db)

    if not session:
        project = db.query(Project).get(session_id)
        if not perm_service.can_start_session(current_user, project):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to start a session on this segmentation"
            )
        session_service = SessionService(db)
        try:
            session = session_service.start_session(
                project_id=project.id,
                user_id=current_user.id,
                session_name="Session for project " + str(project.id)
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    if session.status != SessionStatus.ACTIVE:
        await websocket.close(code=1008, reason="Session not found or inactive")
        return
    
    project = session.project
    if not perm_service.can_edit(current_user, project):
        await websocket.close(code=1008, reason="Access denied")
        return
    
    session_service = SessionService(db)
    session_service.add_participant(session_id, current_user.id)
    
    await manager.connect(websocket, session_id, current_user.id)
    
    await manager.broadcast(
        session_id,
        {
            "type": "user_joined",
            "user_id": current_user.id,
            "username": current_user.username,
            "timestamp": datetime.utcnow().isoformat()
        },
        exclude=websocket
    )
    
    await manager.send_personal(
        websocket,
        {
            "type": "session_state",
            "session_id": session_id,
            "project_id": session.project_id,
            "active_users": list(manager.get_session_users(session_id)),
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    seg_service = SegmentationService(db)
    
    try:
        while True:
            data = await websocket.receive()
            message = json.loads(data)
            message_type = message.get("type")
            
            if message_type == 'chat':
                await manager.broadcast(
                    session_id,
                    {
                        "type": "chat",
                        "user_id": current_user.id,
                        "username": current_user.username,
                        "message": message.get("message"),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
        
            elif message_type == 'ping':
                await manager.send_personal(
                    websocket,
                    {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            elif message_type == "segmentation_update":
                await session.handle_delta(websocket, message)

            elif message_type == "segmentation_full":
                await session.handle_full(websocket, message)
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        await manager.broadcast(
            session_id,
            {
                "type": "user_left",
                "user_id": current_user.id,
                "username": current_user.username,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, session_id)


@router.post("/sessions/{session_id}/end")
def end_collaborative_session(
    session_id: int,
    create_final_version: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    End a collaborative editing session
    
    - **create_final_version**: Whether to create a final version (default: true)
    """
    session_service = SessionService(db)
    
    try:
        session = session_service.end_session(
            session_id=session_id,
            user_id=current_user.id,
            create_final_version=create_final_version
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Notify all connected users that session ended
    asyncio.create_task(
        manager.broadcast(
            session_id,
            {
                "type": "session_ended",
                "session_id": session_id,
                "ended_by": current_user.id,
                "final_version_id": session.final_version_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    )
    
    return {
        "session_id": session.id,
        "status": session.status.value,
        "ended_at": session.ended_at,
        "final_version_id": session.final_version_id
    }


@router.get("/sessions/active")
def get_active_sessions(
    segmentation_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of active collaborative sessions
    
    - **segmentation_id**: Optional - filter by segmentation
    """
    session_service = SessionService(db)
    sessions = session_service.get_active_sessions(
        segmentation_id=segmentation_id,
        user_id=current_user.id
    )
    
    return [
        {
            "session_id": s.id,
            "segmentation_id": s.segmentation_id,
            "segmentation_name": s.segmentation.name,
            "project_id": s.segmentation.project_id,
            "started_by": {
                "id": s.started_by.id,
                "username": s.started_by.username
            },
            "started_at": s.started_at,
            "session_name": s.session_name,
            "active_users": list(manager.get_session_users(s.id))
        }
        for s in sessions
    ]
