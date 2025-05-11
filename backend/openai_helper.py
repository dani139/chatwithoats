import os
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
from sqlalchemy.orm import Session

from models import Message, Conversation, ChatSettings, Tool, ToolType, MessageType
from tools_router import format_tools_for_openai

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))

async def get_openai_response(
    conversation: Conversation, 
    user_message: Message, 
    db: Session,
    message_history_limit: int = 20
) -> str:
    """
    Get a response from the OpenAI Responses API.
    
    Args:
        conversation: The conversation object
        user_message: The user message to respond to
        db: Database session
        message_history_limit: Maximum number of previous messages to include (default: 20)
        
    Returns:
        The text response from OpenAI
    """
    try:
        # Get chat settings for the conversation
        chat_settings = conversation.chat_settings
        if not chat_settings:
            logger.warning(f"No chat settings found for conversation {conversation.chatid}. Using defaults.")
            return "I'm sorry, I'm having trouble with my settings. Please try again later."

        # Get recent message history
        message_history = db.query(Message).filter(
            Message.chatid == conversation.chatid
        ).order_by(Message.created_at.desc()).limit(message_history_limit).all()
        
        # Reverse to get chronological order
        message_history.reverse()
        
        # Format messages for OpenAI
        formatted_messages = []
        
        # Add system message with the system prompt
        formatted_messages.append({
            "role": "system", 
            "content": chat_settings.system_prompt
        })
        
        # Add previous messages
        for msg in message_history:
            if msg.id == user_message.id:
                # Skip the current message as we'll add it last
                continue
                
            role = msg.role if msg.role else "user" if msg.sender else "assistant"
            
            # Handle different message types
            if msg.type == MessageType.TEXT:
                formatted_messages.append({
                    "role": role,
                    "content": msg.content
                })
            elif msg.type == MessageType.TOOL_CALL:
                # This was a tool call by the assistant
                formatted_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": msg.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": msg.function_name,
                            "arguments": msg.function_arguments
                        }
                    }]
                })
            elif msg.type == MessageType.TOOL_RESULT:
                # This was a tool result
                formatted_messages.append({
                    "role": "tool",
                    "content": msg.function_result,
                    "tool_call_id": msg.tool_call_id
                })
        
        # Add the current user message
        formatted_messages.append({
            "role": "user",
            "content": user_message.content
        })
        
        # Get enabled tools for this chat
        tools = []
        if chat_settings.tools:
            tools = format_tools_for_openai(chat_settings.tools)
        
        # Make the API call to OpenAI
        logger.info(f"Sending request to OpenAI with model: {chat_settings.model}")
        response = client.responses.create(
            model=chat_settings.model,
            input=formatted_messages,
            tools=tools if tools else None
        )
        
        # Extract and return the response text
        response_text = response.output_text
        
        # Log the response for debugging
        logger.info(f"Received response from OpenAI: {response_text[:100]}...")
        
        return response_text
        
    except Exception as e:
        logger.error(f"Error getting OpenAI response: {e}")
        return f"I'm sorry, I encountered an error: {str(e)}"
        
async def handle_tool_calls(
    response, 
    conversation: Conversation,
    db: Session
) -> List[Message]:
    """
    Process tool calls from the OpenAI response.
    
    Args:
        response: The OpenAI response object 
        conversation: The conversation object
        db: Database session
        
    Returns:
        A list of tool call and result messages
    """
    # This is a placeholder for future implementation
    # Will handle tool calls from the OpenAI response
    return [] 