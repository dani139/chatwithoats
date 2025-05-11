from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging
import uuid
from datetime import datetime

from db import get_db
from models import Tool, ToolCreate, ToolUpdate, ToolResponse, ChatSettings, ToolType

logger = logging.getLogger(__name__)
router = APIRouter()

def format_tools_for_openai(tools: List[Tool]) -> List[Dict[str, Any]]:
    """
    Format tools into the structure expected by the OpenAI API
    
    Args:
        tools: List of Tool objects
        
    Returns:
        List of dictionaries formatted for OpenAI API
    """
    openai_tools = []
    
    for tool in tools:
        if tool.type == ToolType.OPENAI_TOOL:
            config = tool.configuration
            
            # Handle built-in tools with just a type
            if "type" in config and config["type"] != "function":
                openai_tools.append({"type": config["type"]})
            
            # Handle function tools
            elif config.get("type") == "function":
                openai_tools.append({
                    "type": "function",
                    "name": config.get("name"),
                    "description": config.get("description"),
                    "parameters": config.get("parameters", {})
                })
    
    return openai_tools

# Tool CRUD operations
@router.post("/tools", response_model=ToolResponse)
async def create_tool(tool: ToolCreate, db: Session = Depends(get_db)):
    # Generate a UUID for the id
    tool_id = str(uuid.uuid4())
    
    # Validate tool configuration based on tool type
    if tool.type == ToolType.OPENAI_TOOL:
        config = tool.configuration
        # For function type, validate required fields
        if config.type == "function":
            if not config.name:
                raise HTTPException(status_code=400, detail="Function tools must have a name")
            if not config.description:
                raise HTTPException(status_code=400, detail="Function tools must have a description")
            if not config.parameters:
                raise HTTPException(status_code=400, detail="Function tools must have parameters")
    
    # Create new tool DB record
    db_tool = Tool(
        id=tool_id,
        name=tool.name,
        description=tool.description,
        type=tool.type,
        configuration=tool.configuration.dict(),
        created_at=datetime.utcnow()
    )
    
    # Add to database
    db.add(db_tool)
    
    # Commit the transaction
    db.commit()
    db.refresh(db_tool)
    
    logger.info(f"Created tool with ID: {tool_id}")
    
    # Convert to response model
    return db_tool

@router.get("/tools", response_model=List[ToolResponse])
async def get_all_tools(
    tool_type: Optional[ToolType] = None,
    db: Session = Depends(get_db)
):
    # Start with base query
    query = db.query(Tool)
    
    # Apply filter if tool_type is provided
    if tool_type:
        query = query.filter(Tool.type == tool_type)
    
    # Execute query
    tools_list = query.all()
    
    logger.info(f"Fetched all tools. Count: {len(tools_list)}")
    return tools_list

@router.get("/tools/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: str, db: Session = Depends(get_db)):
    # Get the tool by ID
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    
    # Check if found
    if not tool:
        logger.warning(f"Tool with ID {tool_id} not found.")
        raise HTTPException(status_code=404, detail="Tool not found")
    
    logger.info(f"Fetched tool with ID: {tool_id}")
    
    # Return as response model
    return tool

@router.put("/tools/{tool_id}", response_model=ToolResponse)
async def update_tool(tool_id: str, tool: ToolUpdate, db: Session = Depends(get_db)):
    # Get the tool by ID
    db_tool = db.query(Tool).filter(Tool.id == tool_id).first()
    
    # Check if found
    if not db_tool:
        logger.warning(f"Tool with ID {tool_id} not found for update.")
        raise HTTPException(status_code=404, detail="Tool not found")
    
    # Update fields if provided in the request
    if tool.name is not None:
        db_tool.name = tool.name
    if tool.description is not None:
        db_tool.description = tool.description
    if tool.configuration is not None:
        # Merge the configurations
        current_config = db_tool.configuration
        for key, value in tool.configuration.items():
            current_config[key] = value
        db_tool.configuration = current_config
    
    # Update timestamp
    db_tool.updated_at = datetime.utcnow()
    
    # Save the changes
    db.add(db_tool)
    db.commit()
    db.refresh(db_tool)
    
    logger.info(f"Updated tool with ID: {tool_id}")
    
    # Return the updated tool
    return db_tool

@router.delete("/tools/{tool_id}", status_code=204)
async def delete_tool(tool_id: str, db: Session = Depends(get_db)):
    # Get the tool
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    
    # Check if found
    if not tool:
        logger.warning(f"Tool with ID {tool_id} not found for DELETE.")
        raise HTTPException(status_code=404, detail="Tool not found")
    
    # Delete the tool
    db.delete(tool)
    
    # Commit the transaction
    db.commit()
    
    logger.info(f"Deleted tool with ID: {tool_id}")
    return

# Chat Settings tools management
@router.get("/chat-settings/{settings_id}/tools", response_model=List[ToolResponse])
async def get_tools_for_chat_settings(settings_id: str, db: Session = Depends(get_db)):
    # Check if chat settings exists
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    if not chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    # Get tools associated with the chat settings
    tools = chat_settings.tools
    
    logger.info(f"Fetched {len(tools)} tools for chat settings {settings_id}")
    return tools

@router.get("/chat-settings/{settings_id}/openai-tools")
async def get_openai_tools_for_chat_settings(settings_id: str, db: Session = Depends(get_db)):
    """
    Get tools associated with chat settings, formatted for OpenAI API
    """
    # Check if chat settings exists
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    if not chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    # Get tools associated with the chat settings
    tools = chat_settings.tools
    
    # Filter for OpenAI tools only and format them
    openai_tools = format_tools_for_openai(tools)
    
    logger.info(f"Formatted {len(openai_tools)} OpenAI tools for chat settings {settings_id}")
    return openai_tools

@router.put("/chat-settings/{settings_id}/tools", response_model=List[ToolResponse])
async def update_tools_for_chat_settings(
    settings_id: str, 
    tool_ids: List[str],
    db: Session = Depends(get_db)
):
    # Check if chat settings exists
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    if not chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    # Verify all tools exist
    tools = db.query(Tool).filter(Tool.id.in_(tool_ids)).all()
    if len(tools) != len(tool_ids):
        found_ids = [t.id for t in tools]
        missing_ids = [tid for tid in tool_ids if tid not in found_ids]
        logger.warning(f"Some tools not found: {missing_ids}")
        raise HTTPException(status_code=404, detail=f"Tools not found: {missing_ids}")
    
    # Associate tools with chat settings
    chat_settings.tools = tools
    chat_settings.enabled_tools = tool_ids
    
    # Save changes
    db.add(chat_settings)
    db.commit()
    db.refresh(chat_settings)
    
    logger.info(f"Updated tools for chat settings {settings_id}")
    return tools

@router.post("/chat-settings/{settings_id}/tools/{tool_id}", response_model=ToolResponse)
async def add_tool_to_chat_settings(
    settings_id: str,
    tool_id: str,
    db: Session = Depends(get_db)
):
    # Check if chat settings exists
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    if not chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    # Check if tool exists
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        logger.warning(f"Tool with ID {tool_id} not found.")
        raise HTTPException(status_code=404, detail="Tool not found")
    
    # Check if tool is already associated with chat settings
    if tool in chat_settings.tools:
        logger.info(f"Tool {tool_id} is already associated with chat settings {settings_id}")
        return tool
    
    # Associate tool with chat settings
    chat_settings.tools.append(tool)
    
    # Also add to enabled_tools
    enabled_tools = chat_settings.enabled_tools or []
    if tool_id not in enabled_tools:
        enabled_tools.append(tool_id)
        chat_settings.enabled_tools = enabled_tools
    
    # Save changes
    db.add(chat_settings)
    db.commit()
    
    logger.info(f"Added tool {tool_id} to chat settings {settings_id}")
    return tool

@router.delete("/chat-settings/{settings_id}/tools/{tool_id}", status_code=204)
async def remove_tool_from_chat_settings(
    settings_id: str,
    tool_id: str,
    db: Session = Depends(get_db)
):
    # Check if chat settings exists
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    if not chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    # Check if tool exists
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        logger.warning(f"Tool with ID {tool_id} not found.")
        raise HTTPException(status_code=404, detail="Tool not found")
    
    # Remove association between tool and chat settings
    if tool in chat_settings.tools:
        chat_settings.tools.remove(tool)
    
    # Also remove from enabled_tools
    enabled_tools = chat_settings.enabled_tools or []
    if tool_id in enabled_tools:
        enabled_tools.remove(tool_id)
        chat_settings.enabled_tools = enabled_tools
    
    # Save changes
    db.add(chat_settings)
    db.commit()
    
    logger.info(f"Removed tool {tool_id} from chat settings {settings_id}")
    return 