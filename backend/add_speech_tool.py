#!/usr/bin/env python
import asyncio
import uuid
from datetime import datetime
import os
import sys
import logging

# Set up path to allow importing from backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db, Base, engine
from models import Tool, ToolType, ChatSettings, Conversation

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def add_speech_tool():
    """Add the OpenAI speech API tool to the database and assign it to the currentTest chat"""
    # Create DB session
    db = next(get_db())
    
    try:
        # Find the "currentTest" conversation
        conversation = db.query(Conversation).filter(Conversation.group_name == "currentTest").first()
        
        if not conversation:
            logger.error("Could not find conversation with group_name 'currentTest'")
            return
        
        # Get the chat settings associated with this conversation
        chat_settings = conversation.chat_settings
        
        if not chat_settings:
            logger.error(f"No chat settings found for conversation {conversation.chatid}")
            return
        
        # Check if the speech tool already exists
        existing_tool = db.query(Tool).filter(Tool.name == "speech").first()
        
        if existing_tool:
            logger.info(f"Speech tool already exists with ID: {existing_tool.id}")
            
            # Check if it's already assigned to the chat settings
            if existing_tool in chat_settings.tools:
                logger.info("Speech tool is already assigned to the chat settings")
            else:
                # Assign it to the chat settings
                chat_settings.tools.append(existing_tool)
                
                # Update enabled_tools list
                enabled_tools = chat_settings.enabled_tools or []
                if existing_tool.id not in enabled_tools:
                    enabled_tools.append(existing_tool.id)
                    chat_settings.enabled_tools = enabled_tools
                
                # Save changes
                db.add(chat_settings)
                db.commit()
                logger.info(f"Assigned existing speech tool to chat settings {chat_settings.id}")
            
            return
        
        # Define the speech tool configuration
        speech_tool_config = {
            "type": "speech",
            "name": "speech"  # This is important - the name is required for the OpenAI API
        }
        
        # Create the tool
        tool_id = str(uuid.uuid4())
        speech_tool = Tool(
            id=tool_id,
            name="speech",
            description="Convert text to speech using OpenAI's API",
            type=ToolType.OPENAI_TOOL,
            configuration=speech_tool_config,
            created_at=datetime.utcnow()
        )
        
        # Add tool to database
        db.add(speech_tool)
        
        # Assign it to the chat settings
        chat_settings.tools.append(speech_tool)
        
        # Update enabled_tools list
        enabled_tools = chat_settings.enabled_tools or []
        if tool_id not in enabled_tools:
            enabled_tools.append(tool_id)
            chat_settings.enabled_tools = enabled_tools
        
        # Save changes
        db.add(chat_settings)
        db.commit()
        
        logger.info(f"Created speech tool with ID: {tool_id} and assigned it to chat settings {chat_settings.id}")
        
    except Exception as e:
        logger.error(f"Error adding speech tool: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(add_speech_tool()) 