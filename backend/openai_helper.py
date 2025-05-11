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

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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
        body = None
        
        # Add headers
        for header_name, header_info in config.get("headers", {}).items():
            # Only add required headers or headers provided in arguments
            if header_info.get("required", False) or header_name in arguments:
                headers[header_name] = arguments.get(header_name, "")
        
        # Add OpenAI API key if this is an OpenAI API call (based on server_url)
        if server_url and "api.openai.com" in server_url:
            headers["Authorization"] = f"Bearer {os.environ.get('OPENAI_API_KEY')}"
            headers["Content-Type"] = "application/json"
        
        # Add query parameters
        for param_name, param_info in config.get("params", {}).items():
            # Only add required params or params provided in arguments
            if param_info.get("required", False) or param_name in arguments:
                params[param_name] = arguments.get(param_name, "")
        
        # Prepare body if needed
        if method in ["POST", "PUT", "PATCH"]:
            # Extract body parameters from arguments
            # Skip params that were used in the query string
            body_params = {k: v for k, v in arguments.items() if k not in params}
            if body_params:
                body = body_params
        
        # Make the request
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(full_url, params=params, headers=headers)
            elif method == "POST":
                response = await client.post(full_url, params=params, headers=headers, json=body)
            elif method == "PUT":
                response = await client.put(full_url, params=params, headers=headers, json=body)
            elif method == "DELETE":
                response = await client.delete(full_url, params=params, headers=headers)
            elif method == "PATCH":
                response = await client.patch(full_url, params=params, headers=headers, json=body)
            else:
                return f"Unsupported HTTP method: {method}"
            
            # Get response content
            try:
                result = response.json()
                return json.dumps(result, indent=2)
            except:
                # Return text if not JSON
                return response.text
                
    except Exception as e:
        logger.error(f"Error executing API tool {tool.name}: {e}")
        return f"Error executing tool: {str(e)}"

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