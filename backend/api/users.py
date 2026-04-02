from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from .auth import get_current_user  
from models import User
from sqlalchemy.orm import Session
from database import get_db

router = APIRouter(prefix="/users", tags=["users"])

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    class Config:
        from_attributes = True

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)  
):
    """
    Get current user's profile information
    """
    return current_user

@router.get("/me/details")
async def get_current_user_details(
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed user information
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "created_at": current_user.created_at,  
        "is_active": current_user.is_active    
    }


@router.get("/all-users")
async def get_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    users = db.query(User).filter(User.id != current_user.id).all()
    return [{"id": u.id, "username": u.username, "email": u.email} for u in users]

