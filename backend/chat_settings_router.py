from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import uuid
from datetime import datetime

from db import get_db
from models import ChatSettings, ChatSettingsCreate, ChatSettingsUpdate, ChatSettingsResponse
from models import Tool, ToolType

logger = logging.getLogger(__name__)
router = APIRouter()

async def get_or_create_web_search_tool(db: Session) -> Tool:
    """
    Get the web search tool from the database or create it if it doesn't exist.
    
    Args:
        db: Database session
        
    Returns:
        Web search tool object
    """
    # Check if web search tool already exists - getting all OpenAI tools and filtering in Python
    # This approach is more compatible across different database backends
    openai_tools = db.query(Tool).filter(Tool.type == ToolType.OPENAI_TOOL).all()
    web_search_tool = None
    
    for tool in openai_tools:
        if tool.configuration.get('type') == 'web_search':
            web_search_tool = tool
            break
    
    # If web search tool doesn't exist, create it
    if not web_search_tool:
        tool_id = str(uuid.uuid4())
        
        # Create new web search tool
        web_search_tool = Tool(
            id=tool_id,
            name="Web Search",
            description="Search the web for the latest information",
            type=ToolType.OPENAI_TOOL,
            configuration={
                "type": "web_search"
            },
            created_at=datetime.utcnow()
        )
        
        # Add to database
        db.add(web_search_tool)
        db.commit()
        db.refresh(web_search_tool)
        
        logger.info(f"Created new web search tool with ID: {tool_id}")
    
    return web_search_tool

@router.post("/chat-settings", response_model=ChatSettingsResponse)
async def create_chat_settings(chat_settings: ChatSettingsCreate, add_web_search: bool = True, db: Session = Depends(get_db)):
    # Generate a UUID for the id
    settings_id = str(uuid.uuid4())
    
    # Get or create web search tool
    web_search_tool = None
    enabled_tools = list(chat_settings.enabled_tools) if chat_settings.enabled_tools else []
    
    if add_web_search:
        web_search_tool = await get_or_create_web_search_tool(db)
        
        # Add web search tool ID to enabled_tools if not already present
        if web_search_tool.id not in enabled_tools:
            enabled_tools.append(web_search_tool.id)
    
    # Create new chat settings DB record
    db_chat_settings = ChatSettings(
        id=settings_id,
        name=chat_settings.name,
        description=chat_settings.description,
        system_prompt=chat_settings.system_prompt,
        model=chat_settings.model,
        enabled_tools=enabled_tools
    )
    
    # Add to database
    db.add(db_chat_settings)
    
    # Associate web search tool with chat settings if enabled
    if add_web_search and web_search_tool:
        db_chat_settings.tools = [web_search_tool]
    
    # Commit the transaction
    db.commit()
    db.refresh(db_chat_settings)
    
    logger.info(f"Created chat settings with ID: {settings_id} {' and linked web search tool' if add_web_search else ' without web search tool'}")
    
    # Convert to response model
    return ChatSettingsResponse(
        id=db_chat_settings.id,
        name=db_chat_settings.name,
        description=db_chat_settings.description,
        system_prompt=db_chat_settings.system_prompt,
        model=db_chat_settings.model,
        enabled_tools=db_chat_settings.enabled_tools
    )

@router.get("/chat-settings", response_model=List[ChatSettingsResponse])
async def get_all_chat_settings(db: Session = Depends(get_db)):
    # Execute query
    chat_settings_list = db.query(ChatSettings).all()
    
    # Convert to response models
    result = []
    for settings in chat_settings_list:
        result.append(
            ChatSettingsResponse(
                id=settings.id,
                name=settings.name,
                description=settings.description,
                system_prompt=settings.system_prompt,
                model=settings.model,
                enabled_tools=settings.enabled_tools
            )
        )
    
    logger.info(f"Fetched all chat settings. Count: {len(result)}")
    return result

@router.get("/chat-settings/{settings_id}", response_model=ChatSettingsResponse)
async def get_chat_settings(settings_id: str, db: Session = Depends(get_db)):
    # Get the chat settings by ID
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    
    # Check if found
    if not chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    logger.info(f"Fetched chat settings with ID: {settings_id}")
    
    # Return as response model
    return ChatSettingsResponse(
        id=chat_settings.id,
        name=chat_settings.name,
        description=chat_settings.description,
        system_prompt=chat_settings.system_prompt,
        model=chat_settings.model,
        enabled_tools=chat_settings.enabled_tools
    )

@router.put("/chat-settings/{settings_id}", response_model=ChatSettingsResponse)
async def update_chat_settings(settings_id: str, chat_settings: ChatSettingsUpdate, db: Session = Depends(get_db)):
    # Get the chat settings by ID
    db_chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    
    # Check if found
    if not db_chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found for update.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    # Update fields if provided in the request
    if chat_settings.name is not None:
        db_chat_settings.name = chat_settings.name
    if chat_settings.description is not None:
        db_chat_settings.description = chat_settings.description
    if chat_settings.system_prompt is not None:
        db_chat_settings.system_prompt = chat_settings.system_prompt
    if chat_settings.model is not None:
        db_chat_settings.model = chat_settings.model
    if chat_settings.enabled_tools is not None:
        db_chat_settings.enabled_tools = chat_settings.enabled_tools
    
    # Save the changes
    db.add(db_chat_settings)
    db.commit()
    db.refresh(db_chat_settings)
    
    logger.info(f"Updated chat settings with ID: {settings_id}")
    
    # Return the updated settings
    return ChatSettingsResponse(
        id=db_chat_settings.id,
        name=db_chat_settings.name,
        description=db_chat_settings.description,
        system_prompt=db_chat_settings.system_prompt,
        model=db_chat_settings.model,
        enabled_tools=db_chat_settings.enabled_tools
    )

@router.delete("/chat-settings/{settings_id}", status_code=204)
async def delete_chat_settings(settings_id: str, db: Session = Depends(get_db)):
    # Get the chat settings
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    
    # Check if found
    if not chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found for DELETE.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    # Check if there are conversations using these settings
    if len(chat_settings.conversations) > 0:
        logger.warning(f"Cannot delete chat settings with ID {settings_id} as it's being used by conversations.")
        raise HTTPException(
            status_code=400, 
            detail="Cannot delete chat settings that are being used by conversations"
        )
    
    # Delete the chat settings
    db.delete(chat_settings)
    
    # Commit the transaction
    db.commit()
    
    logger.info(f"Deleted chat settings with ID: {settings_id}")
    return 