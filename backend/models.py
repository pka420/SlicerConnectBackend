from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum, UniqueConstraint, Index, Text, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import numpy as np

class UserRole(str, PyEnum):
    OWNER     = "owner"       # owns project
    EDITOR    = "editor"      # can modify
    REVIEWER  = "reviewer"    # can see + comment, cannot modify
    VIEWER    = "viewer"      # read-only
    GUEST     = "guest"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    is_verified = Column(Boolean, default=False)
    email_token = Column(String, nullable=True)
    
    owned_projects = relationship("Project", back_populates="owner", foreign_keys="[Project.owner_id]")
    collaborations = relationship(
        "ProjectCollaborator",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    reset_token = Column(String, nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)


class Project(Base):
    __tablename__ = "projects"
    
    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(100), nullable=False)
    description = Column(String, nullable=True)
    created_at  = Column(DateTime, server_default=func.now())
    updated_at  = Column(DateTime, onupdate=func.now(), server_default=func.now())
    
    owner_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_locked   = Column(Boolean, default=False, nullable=False)
    locked_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    locked_at   = Column(DateTime, nullable=True)

    owner       = relationship("User", foreign_keys=[owner_id], back_populates="owned_projects")
    lock_user   = relationship("User", foreign_keys=[locked_by_id])
    
    collaborators = relationship("ProjectCollaborator", back_populates="project", cascade="all, delete-orphan")
    segmentations = relationship("Segmentation", back_populates="project", cascade="all, delete-orphan")
    session = relationship("CollaborativeSession", back_populates="project", uselist=False, cascade="all, delete-orphan")



class ProjectCollaborator(Base):
    __tablename__ = "project_collaborators"
    
    user_id     = Column(Integer, ForeignKey("users.id"), primary_key=True)
    project_id  = Column(Integer, ForeignKey("projects.id"), primary_key=True)
    role        = Column(Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    added_at    = Column(DateTime, server_default=func.now())
    
    user        = relationship("User", back_populates="collaborations")
    project     = relationship("Project", back_populates="collaborators")


class Segmentation(Base):
    __tablename__ = "segmentations"
    
    id              = Column(Integer, primary_key=True)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name            = Column(String(120), nullable=False)
    color           = Column(String(9))  # #RRGGBBAA
    hash            = Column(Text, nullable=True)  
    created_by_id   = Column(Integer, ForeignKey("users.id"))
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, onupdate=func.now(), server_default=func.now())
    last_editor_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    project         = relationship("Project", back_populates="segmentations")
    creator         = relationship("User", foreign_keys=[created_by_id])
    last_editor     = relationship("User", foreign_keys=[last_editor_id])
    versions        = relationship("SegmentationVersion", back_populates="segmentation", cascade="all, delete-orphan")


class SegmentationVersion(Base):
    """Each significant change → new version row"""
    __tablename__ = "segmentation_versions"
    
    id                  = Column(Integer, primary_key=True)
    segmentation_id     = Column(Integer, ForeignKey("segmentations.id"), nullable=False)
    version_number      = Column(Integer, nullable=False)
    created_at          = Column(DateTime, server_default=func.now())
    created_by_id       = Column(Integer, ForeignKey("users.id"))
    change_description  = Column(String(300), nullable=True)
    file_path           = Column(String, nullable=False)
    is_complete_state   = Column(Boolean, default=True)
    
    segmentation        = relationship("Segmentation", back_populates="versions")
    creator             = relationship("User")
    
    __table_args__ = (
        UniqueConstraint('segmentation_id', 'version_number', name='uq_segmentation_version'),
        Index('ix_segmentation_versions_lookup', 'segmentation_id', 'version_number'),
    )


class EditType(str, PyEnum):
    FULL_SAVE = "full_save"      # Complete segmentation save (REST)
    DELTA = "delta"               # Incremental change (WebSocket)
    SNAPSHOT = "snapshot"         # Periodic snapshot during live session


class SegmentationEdit(Base):
    """
    Stores all edits - both full saves and deltas.
    This table supports both REST (full saves) and WebSocket (deltas) workflows.
    """
    __tablename__ = "segmentation_edits"
    
    id = Column(Integer, primary_key=True, index=True)
    segmentation_id = Column(Integer, ForeignKey("segmentations.id"), nullable=False, index=True)
    edit_type = Column(Enum(EditType), nullable=False, default=EditType.FULL_SAVE)
    
    file_path = Column(String(500), nullable=True)
    
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    
    change_description = Column(String(500), nullable=True)
    client_timestamp = Column(DateTime, nullable=True)  
    
    segmentation = relationship("Segmentation", backref="edits")
    creator = relationship("User")
    
    __table_args__ = (
        Index('ix_segmentation_edits_lookup', 'segmentation_id', 'created_at'),
    )


class SessionStatus(str, PyEnum):
    ACTIVE = "active"
    ENDED = "ended"
    ABANDONED = "abandoned"  


class CollaborativeSession(Base):
    """
    Represents a live collaborative editing session.
    Multiple users can join and edit simultaneously via WebSocket.
    """
    __tablename__ = "collaborative_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    started_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.ACTIVE, nullable=False, index=True)
    
    session_name = Column(String(200), nullable=True)  
    
    participants_json = Column(Text, nullable=True)  
    
    project = relationship("Project", back_populates="session")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, unique=True)

    started_by = relationship("User", foreign_keys=[started_by_id])


class InMemorySegmentation:
    _store: dict[int, dict] = {}

    @classmethod
    def get_session(cls, session_id: int) -> dict | None:
        return cls._store.get(session_id)

    @classmethod
    def set_full(cls, session_id: int, array: np.ndarray, metadata: dict):
        """Sets the entire state, including geometry."""
        cls._store[session_id] = {
            "array": array.copy(),
            "metadata": {
                "dimensions": metadata.get("dimensions"),
                "spacing": metadata.get("spacing"),
                "origin": metadata.get("origin"),
                "direction": metadata.get("direction"),
                "dataType": metadata.get("dataType")
            }
        }
        print(f"DEBUG: Session {session_id} initialized with metadata.")

    @classmethod
    def apply_delta(cls, session_id, indices, values, metadata):
        session = cls._store.get(session_id)
        
        # Slicer sends [X, Y, Z], but NumPy needs (Z, Y, X) for reshape and indexing
        # This MUST match the order of your indices [indices[:,0], indices[:,1], indices[:,2]]
        z_y_x_shape = (metadata["dimensions"][2], metadata["dimensions"][1], metadata["dimensions"][0])
        
        if session is None or session["array"].shape != z_y_x_shape:
            # Initialize with the correct Z, Y, X order
            session = {
                "array": np.zeros(z_y_x_shape, dtype=metadata["dataType"]),
                "metadata": metadata
            }

        # This line only works if the frontend sent indices as [Z, Y, X]
        # (which happens automatically if you use np.argwhere without np.flip)
        session["array"][indices[:, 0], indices[:, 1], indices[:, 2]] = values
        
        session["metadata"] = metadata
        cls._store[session_id] = session
        return session

    @classmethod
    def clear(cls, session_id: int):
        cls._store.pop(session_id, None)    
