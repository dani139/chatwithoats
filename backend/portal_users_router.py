from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
import logging
from datetime import datetime

from db import get_db
from models import PortalUser, PortalUserCreate, PortalUserResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/portal-users", response_model=PortalUserResponse)
async def create_portal_user(user: PortalUserCreate, db: Session = Depends(get_db)):
    """
    Create a new portal user.
    
    Args:
        user: The portal user to create
        db: Database session
        
    Returns:
        The created portal user
    """
    # Check if user already exists
    existing_user = db.query(PortalUser).filter(PortalUser.id == user.id).first()
    if existing_user:
        logger.info(f"Portal user with ID {user.id} already exists.")
        return existing_user
    
    # Create new portal user
    db_user = PortalUser(
        id=user.id,
        username=user.username,
        email=user.email
    )
    
    # Add to database
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    logger.info(f"Created portal user with ID: {user.id}")
    return db_user

@router.get("/portal-users", response_model=List[PortalUserResponse])
async def get_portal_users(db: Session = Depends(get_db)):
    """
    Get all portal users.
    
    Args:
        db: Database session
        
    Returns:
        List of portal users
    """
    users = db.query(PortalUser).all()
    logger.info(f"Fetched {len(users)} portal users")
    return users

@router.get("/portal-users/{user_id}", response_model=PortalUserResponse)
async def get_portal_user(user_id: str, db: Session = Depends(get_db)):
    """
    Get a portal user by ID.
    
    Args:
        user_id: The portal user ID
        db: Database session
        
    Returns:
        The portal user
    """
    user = db.query(PortalUser).filter(PortalUser.id == user_id).first()
    if not user:
        logger.warning(f"Portal user with ID {user_id} not found.")
        raise HTTPException(status_code=404, detail="Portal user not found")
    
    logger.info(f"Fetched portal user with ID: {user_id}")
    return user 