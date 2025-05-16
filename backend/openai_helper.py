import os
import logging
import json
import httpx
import uuid
from typing import List, Dict, Any, Optional
from openai import OpenAI
from sqlalchemy.orm import Session

from models import Message, Conversation, ChatSettings, Tool, ToolType, MessageType
from tools_router import format_tools_for_openai

logger = logging.getLogger(__name__)

# Hardcoded OpenAI API key (DO NOT COMMIT TO PUBLIC REPOS)
OPENAI_API_KEY = "sk-proj-n9MbqjhS3RjoO0UCIoaWT3BlbkFJ8Bkdi74OIe6TujxP2xvy"

masked_key = OPENAI_API_KEY[:6] + "..." if OPENAI_API_KEY else "NOT SET"
logger.info(f"[OpenAI Helper] Initializing OpenAI client with key: {masked_key}")
client = OpenAI(api_key=OPENAI_API_KEY)

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
            logger.info(f"Chat settings for {conversation.chatid} has {len(chat_settings.tools)} tools")
            for tool in chat_settings.tools:
                logger.info(f"Tool: {tool.id} - {tool.name} - {tool.type}")
            
            tools = format_tools_for_openai(chat_settings.tools)
            logger.info(f"Enabled tools for chat {conversation.chatid}: {json.dumps(tools)}")
        else:
            logger.warning(f"No tools found for chat settings {chat_settings.id}")
        
        # Make the API call to OpenAI
        logger.info(f"[OpenAI Helper] get_openai_response called with model: {chat_settings.model if chat_settings else 'default'} and key: {masked_key}")
        logger.info(f"[OpenAI Helper] Tool payload: {tools}")
        response = client.responses.create(
            model=chat_settings.model,
            input=formatted_messages,
            tools=tools if tools else None
        )
        
        # Check if the response contains tool calls and process them
        if hasattr(response, "tool_calls") and response.tool_calls:
            logger.info(f"Response contains {len(response.tool_calls)} tool calls")
            
            # Process tool calls and get tool messages
            tool_messages = await handle_tool_calls(response, conversation, db)
            
            # Add these tool messages to our conversation history
            for msg in tool_messages:
                if msg.type == MessageType.TOOL_CALL:
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
                    formatted_messages.append({
                        "role": "tool",
                        "content": msg.function_result,
                        "tool_call_id": msg.tool_call_id
                    })
            
            # Make another request to get final response
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
        
async def execute_api_tool(tool: Tool, arguments: Dict[str, Any]) -> str:
    """
    Execute an API tool by making the configured HTTP request.
    
    Args:
        tool: The API tool configuration
        arguments: Arguments provided by the model
        
    Returns:
        The response from the API call as a string
    """
    try:
        config = tool.configuration
        
        # Extract endpoint, method, and server_url if available
        endpoint = config.get("endpoint", "")
        method = config.get("method", "GET").upper()
        server_url = config.get("server_url", "")
        
        # Construct full URL
        full_url = f"{server_url}{endpoint}" if server_url else endpoint
        
        # Prepare request parameters
        headers = {}
        params = {}
        body = {}
        
        # Add configured headers if any
        if config.get("headers"):
            headers.update(config.get("headers", {}))
        
        # Add query parameters from arguments that match param schema
        if config.get("params"):
            for param_name, param_info in config.get("params", {}).items():
                if param_name in arguments:
                    params[param_name] = arguments[param_name]
                    
        # Add body parameters from arguments that match body schema
        if config.get("body_schema"):
            body_schema = config.get("body_schema", {})
            
            if isinstance(body_schema, dict) and "properties" in body_schema:
                # Extract properties from arguments that match the schema
                for prop_name in body_schema.get("properties", {}):
                    if prop_name in arguments:
                        body[prop_name] = arguments[prop_name]
        
        # Log the request details
        logger.info(f"Executing API tool {tool.name} ({tool.id}): {method} {full_url}")
        logger.info(f"Headers: {headers}")
        logger.info(f"Params: {params}")
        logger.info(f"Body: {body}")
        
        # Add OpenAI API key if needed
        if "openai.com" in full_url:
            logger.info(f"[OpenAI Helper] Setting Authorization header for OpenAI API call with key: {masked_key}")
            headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
        
        # Make the API request based on method
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(full_url, headers=headers, params=params)
            elif method == "POST":
                response = await client.post(full_url, headers=headers, params=params, json=body)
            elif method == "PUT":
                response = await client.put(full_url, headers=headers, params=params, json=body)
            elif method == "DELETE":
                response = await client.delete(full_url, headers=headers, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Check if the response was successful
            response.raise_for_status()
            
            # Check for binary data (like audio files)
            content_type = response.headers.get("content-type", "")
            
            # Special handling for audio responses from speech API
            if "audio/mpeg" in content_type or "audio/mp3" in content_type or "/audio/" in endpoint:
                # For audio responses, save to a file and return the path
                file_id = str(uuid.uuid4())
                file_path = f"/tmp/speech_{file_id}.mp3"
                
                with open(file_path, "wb") as f:
                    f.write(response.content)
                
                return f"Audio file generated and saved as {file_path}. You can listen to it or download it."
            
            # For JSON responses
            if "application/json" in content_type:
                try:
                    return json.dumps(response.json(), indent=2)
                except:
                    return response.text
            
            # For text responses
            return response.text
            
    except httpx.HTTPStatusError as e:
        error_msg = f"Error code: {e.response.status_code} - {e.response.text}"
        logger.error(f"API call failed: {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"Error executing API tool: {str(e)}"
        logger.error(error_msg)
        return error_msg

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
    messages = []
    
    # Check if the response contains tool calls
    if not hasattr(response, "tool_calls") or not response.tool_calls:
        return messages
    
    # Process each tool call
    for tool_call in response.tool_calls:
        tool_call_id = tool_call.id
        
        if tool_call.type == "function":
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            logger.info(f"Processing tool call: {function_name} with args: {function_args}")
            
            # Record the tool call
            tool_call_msg_id = str(uuid.uuid4())
            tool_call_msg = Message(
                id=tool_call_msg_id,
                chatid=conversation.chatid,
                sender=None,
                sender_name="Oats",
                type=MessageType.TOOL_CALL,
                content=None,
                role="assistant",
                tool_call_id=tool_call_id,
                function_name=function_name,
                function_arguments=json.dumps(function_args)
            )
            
            # Add to database
            db.add(tool_call_msg)
            db.commit()
            messages.append(tool_call_msg)
            
            # Find the tool in the database
            tool = None
            for t in conversation.chat_settings.tools:
                if t.name == function_name:
                    tool = t
                    break
            
            function_result = "Tool not found."
            
            if tool:
                # Execute the appropriate tool based on its type
                if tool.type == ToolType.API_TOOL:
                    function_result = await execute_api_tool(tool, function_args)
                # Add more tool type handlers as needed
            
            # Record the tool result
            tool_result_msg_id = str(uuid.uuid4())
            tool_result_msg = Message(
                id=tool_result_msg_id,
                chatid=conversation.chatid,
                sender=None,
                sender_name="Oats",
                type=MessageType.TOOL_RESULT,
                content=None,
                role="tool",
                tool_call_id=tool_call_id,
                function_name=function_name,
                function_result=function_result
            )
            
            # Add to database
            db.add(tool_result_msg)
            db.commit()
            messages.append(tool_result_msg)
    
    logger.info(f"Processed {len(messages) // 2} tool calls")
    return messages 