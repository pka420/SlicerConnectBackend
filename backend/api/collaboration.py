from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException, status
from typing import Dict, Set, List, Optional
import json
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from models import User, CollaborativeSession, SessionStatus, Segmentation, Project, InMemorySegmentation
from .auth import get_current_user
from services.session_service import SessionService
from services.segmentation_service import SegmentationService
from services.permission_service import PermissionService
import zlib
import hashlib

router = APIRouter(prefix="/collaboration", tags=["Collaboration"])

class ConnectionManager:
    """
    Manages WebSocket connections for collaborative sessions
    """
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        self.user_mapping: Dict[WebSocket, int] = {}
    
    async def connect(self, websocket: WebSocket, project_id: int, user_id: int):
        """Accept and register a new connection"""
        await websocket.accept()
        
        if project_id not in self.active_connections:
            self.active_connections[project_id] = set()
        
        self.active_connections[project_id].add(websocket)
        self.user_mapping[websocket] = user_id
    
    def disconnect(self, websocket: WebSocket, project_id: int):
        """Remove a connection"""
        if project_id in self.active_connections:
            self.active_connections[project_id].discard(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        
        if websocket in self.user_mapping:
            del self.user_mapping[websocket]
    
    async def broadcast(self, project_id: int, message: dict, exclude: WebSocket = None):
        """Broadcast message to all connections in a session"""
        if project_id not in self.active_connections:
            return

        connections_snapshot = list(self.active_connections[project_id])
        
        dead_connections = set()
        for connection in connections_snapshot:
            if connection == exclude:
                continue
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.add(connection)
        
        # Clean up dead connections
        for connection in dead_connections:
            self.disconnect(connection, project_id)
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to a specific connection"""
        try:
            await websocket.send_json(message)
        except Exception:
            pass
    
    def get_session_users(self, project_id: int) -> Set[int]:
        """Get all user IDs in a session"""
        if project_id not in self.active_connections:
            return set()
        
        users = set()
        for connection in self.active_connections[project_id]:
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
    Returns project_id and WebSocket URL to connect to
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
        "project_id": session.id,
        "project_id": session.project_id,
        "started_at": session.started_at,
        "websocket_url": f"/api/collaboration/sessions/{session.id}/ws"
    }

@router.websocket("/sessions/{project_id}/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    WebSocket endpoint for real-time collaborative editing
    
    Connect with: ws://localhost:8000/api/collaboration/sessions/{project_id}/ws?token={jwt_token}
    
    Message Types:
    - delta: Segmentation changes
    - full: Segmentation Full
    - chat: Chat messages
    - ping: Keep-alive
    """

    print('in connections')
    print('session id ', project_id)
    try:
        current_user: User = get_current_user(token, db)
    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=401, detail=str(e))

    session = db.query(CollaborativeSession).filter(
        CollaborativeSession.project_id == project_id
    ).first()

    perm_service = PermissionService(db)
    session_service = SessionService(db)

    if not session:
        project = db.query(Project).get(project_id)
        if not perm_service.can_start_session(current_user, project):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to start a session on this segmentation"
            )
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
    
    session_service.add_participant(project_id, current_user.id)
    
    await manager.connect(websocket, project_id, current_user.id)
    
    await manager.broadcast(
        project_id,
        {
            "type": "user_joined",
            "userId": current_user.id,
            "username": current_user.username,
            "timestamp": datetime.utcnow().isoformat()
        },
        exclude=websocket
    )
    
    await manager.send_personal(
        websocket,
        {
            "type": "session_state",
            "project_id": project_id,
            "project_id": session.project_id,
            "active_users": list(manager.get_session_users(project_id)),
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    seg_service = SegmentationService(db)
    current_ram_state = InMemorySegmentation.get_session(project_id)
    if current_ram_state is None:
        print('current_ram_state is None')
        seg_rec = db.query(Segmentation).filter(Segmentation.project_id == session.project_id).first()
        if seg_rec:
            print('seg record found in db, hence the disk')
            print('loading RAM from disk')
            seg_service.load_disk_to_ram(project_id, seg_rec.id)
            current_ram_state = InMemorySegmentation.get_session(project_id)
    else:
        seg_rec = db.query(Segmentation).filter(Segmentation.project_id == session.project_id).first()

    if current_ram_state is not None:
        print('current_ram_state is not None NOW, loading from RAM')
        import base64
        import zlib

        seg_array = current_ram_state["array"]
        metadata = current_ram_state["metadata"]

        compressed_data = zlib.compress(seg_array.tobytes())
        encoded_data = base64.b64encode(compressed_data).decode('utf-8')

        current_hash = hashlib.sha256(seg_array.tobytes()).hexdigest()
        await manager.send_personal(
            websocket,
            {
                "type": "segmentation_full",
                "sessionHash": current_hash,
                "data": {
                    "dimensions": metadata["dimensions"],
                    "dataType": metadata["dataType"],
                    "imageData": encoded_data, 
                    "spacing": metadata["spacing"],
                    "origin": metadata["origin"],
                    "direction": metadata["direction"]
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    try:
        while True:
            message = await websocket.receive_json()
            try:
                message_type = message.get("type")
            except Exception as e:
                print('error :', str(e))
                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "message": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            
            if message_type == 'chat':
                await manager.broadcast(
                    project_id,
                    {
                        "type": "chat",
                        "user_id": current_user.id,
                        "username": current_user.username,
                        "message": message.get("message"),
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    exclude=websocket
                )
        
            elif message_type == 'ping':
                await manager.send_personal(
                    websocket,
                    {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            elif message_type == "segmentation_delta":
                success, err  = seg_service.handle_delta(message, project_id, current_user.id, db)
                if not success or err is not None:
                    print('err while applying segmentation_full ', err)
                sent_by = current_user.id
                print('sent by user: ', sent_by)
                for user_id in manager.get_session_users(project_id): 
                    if user_id != sent_by: 
                        message['username'] = current_user.username
                        await manager.broadcast(
                            project_id,
                            message=message,
                            exclude=websocket 
                        )

            elif message_type == "segmentation_full":
                success, err  = seg_service.handle_full(message, project_id, current_user.id, db)
                if not success or err is not None:
                    print('err while applying segmentation_full ', err)
                else:
                    sent_by = current_user.id
                    print('sent by user: ', sent_by)
                    print("users in session: ", manager.get_session_users(project_id))
                    for user_id in manager.get_session_users(project_id): 
                        if user_id != sent_by: 
                            print('forwarding to : ', user_id)
                            message['username'] = current_user.username
                            await manager.broadcast(
                                project_id,
                                message=message,
                                exclude=websocket 
                            )
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, project_id)

        print("WebSocketDisconnect")
        # should check manager.active_connections? or save if any single user left??
        seg_service.sync_ram_to_disk(project_id, user_id=current_user.id)
        InMemorySegmentation.clear(project_id)

        await manager.broadcast(
            project_id,
            {
                "type": "user_left",
                "userId": current_user.id,
                "username": current_user.username,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, project_id)


@router.post("/sessions/{project_id}/end")
def end_collaborative_session(
    project_id: int,
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
            project_id=project_id,
            user_id=current_user.id,
            create_final_version=create_final_version
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    asyncio.create_task(
        manager.broadcast(
            project_id,
            {
                "type": "session_ended",
                "project_id": project_id,
                "ended_by": current_user.id,
                "final_version_id": session.final_version_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    )
    
    return {
        "project_id": session.id,
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
            "project_id": s.id,
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
