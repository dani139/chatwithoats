import os
import logging
import json
import httpx
import uuid
from typing import List, Dict, Any, Optional, Union
from openai import OpenAI
from sqlalchemy.orm import Session
from urllib.parse import urlparse
import re

from models import Message, Conversation, ChatSettings, Tool, ToolType, MessageType

# Configure logger
logger = logging.getLogger(__name__)


class OpenAIHelper:
    """
    Class for handling OpenAI API interactions in a modular, organized manner.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the OpenAI helper with an API key.
        
        Args:
            api_key: The OpenAI API key to use. If None, will try to get from environment.
        """
        # Get API key from parameter, environment, or .env file
        api_key_raw = api_key or os.getenv("OPENAI_API_KEY")
        
        # Clean up the API key - remove any whitespace, newlines, etc.
        self.api_key = api_key_raw.replace("\n", "").replace(" ", "").strip() if api_key_raw else None
        
        if not self.api_key:
            logger.error("No OpenAI API key provided!")
            raise ValueError("OpenAI API key is required. Provide it directly or set OPENAI_API_KEY in environment.")
        
        # Mask the API key for secure logging
        self.masked_key = self.api_key[:6] + "..." if self.api_key else "NOT SET"
        logger.info(f"[OpenAI Helper] Initializing OpenAI client with key: {self.masked_key}")
        
        # Initialize the OpenAI client
        self.client = OpenAI(api_key=self.api_key)

    async def get_openai_response(
        self,
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

            # Format conversation for OpenAI
            formatted_messages = self._format_conversation(conversation, user_message, db, message_history_limit)
            
            # Get enabled tools for this chat
            tools = self._get_tools_for_chat(conversation.chatid, chat_settings)
            
            # Make the API call to OpenAI
            logger.info(f"[OpenAI Helper] get_openai_response called with model: {chat_settings.model if chat_settings else 'default'} and key: {self.masked_key}")
            logger.info(f"[OpenAI Helper] Tool payload: {tools}")
            
            # Final check to ensure all function tools have a name
            if tools:
                for i, tool in enumerate(tools):
                    if tool.get("type") == "function":
                        if "name" not in tool:
                            logger.error(f"[OpenAI Helper] Missing 'name' in function tool at index {i}")
                            # Try to add a placeholder name if missing
                            tool["name"] = f"function_{i}"
                
                logger.info(f"[OpenAI Helper] Final tool payload for Responses API: {json.dumps(tools)}")
            
            response = self.client.responses.create(
                model=chat_settings.model,
                input=formatted_messages,
                tools=tools if tools else None,
                # Use 'auto' for tool_choice instead of a specific type
                tool_choice="auto" if tools else None
            )
            
            # Debug logging for the response
            logger.info(f"[OpenAI Helper] Response object type: {type(response)}")
            logger.info(f"[OpenAI Helper] Response attributes: {[attr for attr in dir(response) if not attr.startswith('_')]}")
            
            # Try to access the output attribute safely
            output_attr = getattr(response, "output", None)
            logger.info(f"[OpenAI Helper] Response output attribute type: {type(output_attr)}")
            
            # Check what's in the output
            if output_attr is not None:
                try:
                    if isinstance(output_attr, list):
                        logger.info(f"[OpenAI Helper] Response output is a list with {len(output_attr)} items")
                        for i, item in enumerate(output_attr):
                            logger.info(f"[OpenAI Helper] Output item {i} type: {type(item)}")
                            if hasattr(item, "__dict__"):
                                logger.info(f"[OpenAI Helper] Output item {i} attributes: {[attr for attr in dir(item) if not attr.startswith('_')]}")
                            elif isinstance(item, dict):
                                logger.info(f"[OpenAI Helper] Output item {i} keys: {item.keys()}")
                                if "type" in item:
                                    logger.info(f"[OpenAI Helper] Output item {i} type field: {item['type']}")
                    else:
                        # Try different ways to inspect the output
                        if hasattr(output_attr, "__dict__"):
                            logger.info(f"[OpenAI Helper] Output object attributes: {[attr for attr in dir(output_attr) if not attr.startswith('_')]}")
                        elif isinstance(output_attr, dict):
                            logger.info(f"[OpenAI Helper] Output object keys: {output_attr.keys()}")
                        else:
                            # Last resort - try string representation
                            logger.info(f"[OpenAI Helper] Output repr: {repr(output_attr)}")
                except Exception as e:
                    logger.error(f"[OpenAI Helper] Error inspecting output: {str(e)}")
            
            # Also check output_text attribute
            output_text_attr = getattr(response, "output_text", None)
            if output_text_attr is not None:
                logger.info(f"[OpenAI Helper] Response has output_text of type {type(output_text_attr)}: {output_text_attr[:100]}...")
            
            # Check for tool_calls in different possible locations
            has_tool_calls = False
            tool_calls = []
            
            # Check if output has tool calls - this is the standard location
            if hasattr(response, "output"):
                logger.info(f"[OpenAI Helper] Response has output attribute: {type(response.output)}")
                
                # Check if output is a list (array of tool calls)
                if isinstance(response.output, list):
                    # Extract function calls from the output array
                    function_calls = []
                    for item in response.output:
                        # Check if it's a dictionary or an object
                        if isinstance(item, dict) and item.get('type') == 'function_call':
                            function_calls.append(item)
                        # Check for ResponseFunctionToolCall with type="function_call"
                        elif hasattr(item, 'type') and getattr(item, 'type') == 'function_call':
                            function_calls.append(item)
                        # Check for legacy format with type="function"
                        elif hasattr(item, 'type') and getattr(item, 'type') == 'function':
                            function_calls.append(item)
                    
                    if function_calls:
                        has_tool_calls = True
                        tool_calls = function_calls
                        logger.info(f"[OpenAI Helper] Found {len(function_calls)} function calls in response.output list")
            
            # Also check if output has a tool_calls attribute
            elif hasattr(response.output, "tool_calls"):
                has_tool_calls = True
                tool_calls = response.output.tool_calls
                logger.info(f"[OpenAI Helper] Found tool_calls in response.output")
            
            # Direct tool_calls (legacy or alternate format)
            elif hasattr(response, "tool_calls"):
                has_tool_calls = True
                tool_calls = response.tool_calls
                logger.info(f"[OpenAI Helper] Found tool_calls directly on response")
            
            logger.info(f"[OpenAI Helper] Response has tool_calls: {has_tool_calls}")
            
            if has_tool_calls and tool_calls:
                logger.info(f"[OpenAI Helper] Number of tool calls: {len(tool_calls)}")
                for i, tool_call in enumerate(tool_calls):
                    # Handle both object-style and dict-style tool calls
                    if isinstance(tool_call, dict):
                        logger.info(f"[OpenAI Helper] Tool call {i} (dict): type={tool_call.get('type')}, id={tool_call.get('id')}")
                        if tool_call.get('type') == 'function_call':
                            logger.info(f"[OpenAI Helper] Function name: {tool_call.get('name')}")
                            logger.info(f"[OpenAI Helper] Function arguments: {tool_call.get('arguments')}")
                    else:
                        # For object-style calls, use getattr instead of get()
                        logger.info(f"[OpenAI Helper] Tool call {i} (object): type={getattr(tool_call, 'type', None)}, id={getattr(tool_call, 'id', None)}")
                        if getattr(tool_call, 'type', None) == 'function':
                            function_attr = getattr(tool_call, 'function', None)
                            if function_attr:
                                logger.info(f"[OpenAI Helper] Function name: {getattr(function_attr, 'name', None)}")
                                logger.info(f"[OpenAI Helper] Function arguments: {getattr(function_attr, 'arguments', None)}")
                        elif hasattr(tool_call, 'function') and tool_call.function:
                            # Handle ResponseFunctionToolCall objects
                            logger.info(f"[OpenAI Helper] Function name: {getattr(tool_call.function, 'name', None)}")
                            logger.info(f"[OpenAI Helper] Function arguments: {getattr(tool_call.function, 'arguments', None)}")
            
            # Check if the response contains tool calls and process them
            if has_tool_calls and tool_calls:
                logger.info(f"Response contains {len(tool_calls)} tool calls")
                
                # Process tool calls and get tool messages
                tool_messages = await self.handle_tool_calls_with_array(tool_calls, conversation, db)
                
                # Add these tool messages to our conversation history
                for msg in tool_messages:
                    formatted_messages = self._add_tool_message_to_history(formatted_messages, msg)
                
                # Make another request to get final response
                response = self.client.responses.create(
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
    
    def _format_conversation(
        self, 
        conversation: Conversation,
        user_message: Message,
        db: Session,
        message_history_limit: int
    ) -> List[Dict[str, Any]]:
        """
        Format a conversation for the OpenAI API.
        
        Args:
            conversation: The conversation object
            user_message: The user message to respond to
            db: Database session
            message_history_limit: Maximum number of previous messages to include
            
        Returns:
            List of formatted messages for the OpenAI API
        """
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
            "content": conversation.chat_settings.system_prompt
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
                    "content": msg.content or ""  # Make sure content is never null
                })
            elif msg.type == MessageType.TOOL_CALL:
                # For tool calls, include content as empty string instead of null
                # Format based on OpenAI's expected structure
                tc_msg = {
                    "role": "assistant",
                    "content": ""  # Empty string instead of null
                }
                
                # Add tool_calls in the correct format
                tc_msg["tool_calls"] = [{
                    "id": msg.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": msg.function_name,
                        "arguments": msg.function_arguments
                    }
                }]
                
                formatted_messages.append(tc_msg)
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
        
        return formatted_messages
    
    def _get_tools_for_chat(self, conversation_id: str, chat_settings: ChatSettings) -> List[Dict[str, Any]]:
        """
        Get the list of tools enabled for a chat.
        
        Args:
            conversation_id: The ID of the conversation
            chat_settings: The chat settings object
            
        Returns:
            List of formatted tools for the OpenAI API
        """
        tools = []
        if chat_settings.tools:
            logger.info(f"Chat settings for {conversation_id} has {len(chat_settings.tools)} tools")
            for tool in chat_settings.tools:
                logger.info(f"Tool: {tool.id} - {tool.name} - {tool.tool_type}")
            
            tools = self.format_tools_for_openai(chat_settings.tools)
            
            # Double check to ensure all tools are properly formatted (flat structure)
            for i, tool in enumerate(tools):
                if tool.get("type") == "function" and "function" in tool:
                    # Found old format - convert to flat structure
                    logger.warning(f"Converting tool at index {i} from nested to flat structure")
                    function_obj = tool.pop("function")
                    for k, v in function_obj.items():
                        tool[k] = v
            
            logger.info(f"Enabled tools for chat {conversation_id}: {json.dumps(tools)}")
        else:
            logger.warning(f"No tools found for chat settings {chat_settings.id}")
        
        return tools
    
    def format_tools_for_openai(self, tools: List[Tool]) -> List[Dict[str, Any]]:
        """
        Format tools for the OpenAI API based on their tool_type.
        
        Args:
            tools: List of Tool objects
            
        Returns:
            List of formatted tools for the OpenAI API
        """
        openai_tools = []
        
        for tool in tools:
            try:
                # Use tool_type if available, otherwise fallback to old structure for backward compatibility
                if tool.tool_type:
                    if tool.tool_type == ToolType.WEB_SEARCH:
                        # Built-in web search tool
                        ws_tool = {"type": "web_search_preview"}
                        if tool.function_schema:
                            # Add any optional configuration
                            if "user_location" in tool.function_schema:
                                ws_tool["user_location"] = tool.function_schema["user_location"]
                            if "search_context_size" in tool.function_schema:
                                ws_tool["search_context_size"] = tool.function_schema["search_context_size"]
                        openai_tools.append(ws_tool)
                    
                    elif tool.tool_type == ToolType.FILE_SEARCH:
                        # Built-in file search tool
                        openai_tools.append({"type": "file_search"})
                    
                    elif tool.tool_type == ToolType.FUNCTION:
                        if tool.api_request_id:
                            # API-based function tool
                            api_request = tool.api_request
                            if not api_request:
                                logger.warning(f"API request not found for tool: {tool.id}")
                                continue
                            
                            # Generate a descriptive name that indicates server, endpoint, and method
                            # but doesn't include the pipe character which isn't allowed by OpenAI
                            server_name = "unknown"
                            endpoint = "unknown"
                            method = api_request.method.lower() if api_request.method else "post"
                            
                            # Extract server name from URL if possible
                            if hasattr(api_request, 'url') and api_request.url:
                                try:
                                    url_parts = urlparse(api_request.url)
                                    server_name = url_parts.netloc.split('.')[0]
                                    path_parts = url_parts.path.strip('/').split('/')
                                    if path_parts and path_parts[0]:
                                        endpoint = path_parts[0]
                                except Exception as e:
                                    logger.warning(f"Failed to parse URL for tool {tool.id}: {e}")
                            
                            # Use API path as fallback for endpoint
                            if endpoint == "unknown" and api_request.path:
                                endpoint = api_request.path.strip('/').split('/')[0]
                            
                            # Create formatted name: server_endpoint_method_id
                            # OpenAI requires tool names to match pattern '^[a-zA-Z0-9_-]+$'
                            # So we'll use underscores and avoid special characters
                            formatted_name = f"{server_name}_{endpoint}_{method}_{tool.id[:8]}"
                            
                            # Clean up the name to ensure it's valid for OpenAI
                            tool_name = self._sanitize_tool_name(formatted_name)
                            
                            # Store the mapping of this name to the full tool ID
                            # This will be used by _execute_tool to look up the tool by ID
                            self._register_tool_name_mapping(tool_name, tool.id)
                            
                            # Log the formatted name being used
                            logger.info(f"[OpenAI Helper] Using formatted function name for API tool: {tool_name}")
                            
                            # Format as per OpenAI's expected structure
                            function_def = {
                                "type": "function",
                                "name": tool_name,
                                "description": tool.description or api_request.description or f"Call {api_request.path}"
                            }
                            
                            # Check if we already have a complete function schema
                            if tool.function_schema and isinstance(tool.function_schema, dict):
                                function_schema = tool.function_schema.copy()
                                
                                # Extract parameters if they exist in the schema
                                if "parameters" in function_schema:
                                    function_def["parameters"] = function_schema["parameters"]
                                else:
                                    function_def["parameters"] = self._build_parameters_from_api_request(api_request)
                            else:
                                # Build parameters from API request
                                function_def["parameters"] = self._build_parameters_from_api_request(api_request)
                            
                            # Log the full function definition if it's a speech tool
                            if "speech" in tool_name.lower() or "audio" in tool_name.lower():
                                logger.info(f"[OpenAI Helper] Speech tool function definition for OpenAI: {json.dumps(function_def, indent=2)}")

                            openai_tools.append(function_def)
                        elif tool.function_schema:
                            # Custom function tool with direct schema
                            # Make a deep copy to avoid modifying the original
                            function_schema = tool.function_schema.copy() if isinstance(tool.function_schema, dict) else {}
                            
                            # Get a valid tool name with ID for lookup
                            # Format: custom_functionname_id where id is first 8 chars of the UUID
                            tool_name = f"custom_{tool.name or 'function'}_{tool.id[:8]}"
                            valid_name = self._sanitize_tool_name(tool_name)
                            
                            # Store the mapping of this name to the full tool ID
                            self._register_tool_name_mapping(valid_name, tool.id)
                            
                            function_def = {
                                "type": "function",
                                "name": valid_name,
                                "description": function_schema.get("description") or tool.description or "Call a function"
                            }
                            
                            # Add parameters if available
                            if "parameters" in function_schema:
                                function_def["parameters"] = function_schema["parameters"]
                            else:
                                function_def["parameters"] = {"type": "object", "properties": {}, "required": []}
                                
                            openai_tools.append(function_def)
                        else:
                            # Fallback for function tools without schema
                            tool_name = f"function_{tool.id[:8]}"
                            valid_name = self._sanitize_tool_name(tool_name)
                            
                            # Store the mapping of this name to the full tool ID
                            self._register_tool_name_mapping(valid_name, tool.id)
                            
                            function_def = {
                                "type": "function",
                                "name": valid_name,
                                "description": tool.description or "Call a function",
                                "parameters": {"type": "object", "properties": {}, "required": []}
                            }
                            openai_tools.append(function_def)
                # No backward compatibility - ensure tool_type is set
                else:
                    logger.warning(f"Tool {tool.id} ({tool.name}) has no tool_type set, skipping")
            except Exception as e:
                logger.error(f"Error formatting tool {tool.name} ({tool.id}): {e}")
                
        logger.info(f"Returning {len(openai_tools)} formatted tools")
        return openai_tools
    
    def _sanitize_tool_name(self, name: str) -> str:
        """
        Sanitize a tool name to ensure it's valid for OpenAI API.
        The name must match the pattern '^[a-zA-Z0-9_-]+$'
        
        Args:
            name: The original tool name
            
        Returns:
            A sanitized tool name
        """
        if not name:
            return "unnamed_tool"
        
        # Replace any characters that aren't alphanumeric, underscore, or hyphen
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        
        # Ensure it starts with a letter or underscore (not a number or hyphen)
        if sanitized and not (sanitized[0].isalpha() or sanitized[0] == '_'):
            sanitized = 'f_' + sanitized
        
        # Ensure it's not too long
        if len(sanitized) > 64:
            sanitized = sanitized[:64]
            
        # If somehow we end up with an empty string, use a default
        if not sanitized:
            sanitized = "unnamed_tool"
            
        return sanitized
    
    def _build_parameters_from_api_request(self, api_request) -> Dict[str, Any]:
        """
        Build function parameters schema from API request details.
        
        Args:
            api_request: The API request object
            
        Returns:
            JSON Schema object for parameters
        """
        # Start with a basic object schema
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Use request_body_schema if available
        if api_request.request_body_schema:
            # Extract properties from request body schema
            if isinstance(api_request.request_body_schema, dict):
                schema = api_request.request_body_schema
                if "properties" in schema:
                    parameters["properties"] = schema["properties"]
                if "required" in schema:
                    parameters["required"] = schema["required"]
        
        return parameters
    
    def _add_tool_message_to_history(
        self,
        formatted_messages: List[Dict[str, Any]],
        message: Message
    ) -> List[Dict[str, Any]]:
        """
        Add a tool call or result message to the conversation history.
        
        Args:
            formatted_messages: The current formatted messages
            message: The tool call or result message to add
            
        Returns:
            Updated list of formatted messages
        """
        if message.type == MessageType.TOOL_CALL:
            formatted_messages.append({
                "role": "assistant",
                "content": "",  # Provide empty string instead of null
                "tool_calls": [{
                    "id": message.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": message.function_name,
                        "arguments": message.function_arguments
                    }
                }]
            })
        elif message.type == MessageType.TOOL_RESULT:
            formatted_messages.append({
                "role": "tool",
                "content": message.function_result,
                "tool_call_id": message.tool_call_id
            })
        
        return formatted_messages
            
    async def execute_api_tool(self, tool: Tool, arguments: Dict[str, Any]) -> str:
        """
        Execute an API tool by making the configured HTTP request.
        
        Args:
            tool: The API tool configuration
            arguments: Arguments provided by the model
            
        Returns:
            The response from the API call as a string
        """
        try:
            # Check if the API request exists
            if not tool.api_request:
                return f"Error: No API request associated with tool {tool.id} ({tool.name})"
            
            api_request = tool.api_request
            config = tool.configuration or {}
            
            # Extract endpoint, method from API request
            endpoint = api_request.path if hasattr(api_request, 'path') else ""
            method = api_request.method.upper() if hasattr(api_request, 'method') and api_request.method else "GET"
            
            # First try to get server_url from the tool configuration
            server_url = config.get("server_url", "")
            
            # If not in config, try to get from api_request's url attribute (legacy)
            if not server_url and hasattr(api_request, 'url') and api_request.url:
                # Try to extract the server URL from the full URL
                try:
                    url_parts = urlparse(api_request.url)
                    server_url = f"{url_parts.scheme}://{url_parts.netloc}"
                except Exception as e:
                    logger.warning(f"Failed to parse URL from API request: {e}")
            
            # If still not found, try to get from the linked API object
            if not server_url and hasattr(api_request, 'api') and api_request.api:
                if hasattr(api_request.api, 'server') and api_request.api.server:
                    server_url = api_request.api.server
                    logger.info(f"Using server URL from linked API: {server_url}")
            
            # Construct full URL
            full_url = f"{server_url}{endpoint}" if server_url else endpoint
            
            if not full_url:
                return f"Error: Could not determine URL for API request {api_request.id}"
            
            # Check for missing protocol
            if not full_url.startswith(('http://', 'https://')):
                return f"Error: Invalid URL {full_url}. URL must start with http:// or https://"
            
            # Prepare request parameters
            headers, params, body = self._prepare_request_params(config, arguments)
            
            # Add function arguments to the body if we have a request_body_schema
            if hasattr(api_request, 'request_body_schema') and api_request.request_body_schema:
                # Extract parameters from arguments based on the schema
                schema = api_request.request_body_schema
                if isinstance(schema, dict) and "properties" in schema:
                    for prop_name in schema.get("properties", {}):
                        if prop_name in arguments:
                            body[prop_name] = arguments[prop_name]
            
            # Log the request details
            logger.info(f"Executing API tool {tool.name} ({tool.id}): {method} {full_url}")
            logger.info(f"Headers: {headers}")
            logger.info(f"Params: {params}")
            logger.info(f"Body: {json.dumps(body)}") # Log the actual body being sent
            
            # If it's a speech tool, log the received arguments from LLM
            if "speech" in tool.name.lower() or (hasattr(api_request, 'path') and "audio" in api_request.path.lower()):
                logger.info(f"[OpenAI Helper] LLM provided arguments for speech tool ({tool.name}): {json.dumps(arguments, indent=2)}")
            
            # Add OpenAI API key if needed
            if "openai.com" in full_url:
                logger.info(f"[OpenAI Helper] Setting Authorization header for OpenAI API call with key: {self.masked_key}")
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # Make the API request based on method
            return await self._make_http_request(method, full_url, headers, params, body)
                
        except httpx.HTTPStatusError as e:
            error_msg = f"Error code: {e.response.status_code} - {e.response.text}"
            logger.error(f"API call failed: {error_msg}")
            return error_msg
        except Exception as e:
            error_msg = f"Error executing API tool: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _prepare_request_params(
        self,
        config: Dict[str, Any],
        arguments: Dict[str, Any]
    ) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """
        Prepare request parameters based on tool configuration and arguments.
        
        Args:
            config: The tool configuration
            arguments: Model-provided arguments
            
        Returns:
            Tuple of (headers, params, body)
        """
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
        
        return headers, params, body
    
    async def _make_http_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, Any],
        params: Dict[str, Any],
        body: Dict[str, Any]
    ) -> str:
        """
        Make an HTTP request and handle the response.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            headers: Request headers
            params: Query parameters
            body: Request body
            
        Returns:
            Response as a string
        """
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method == "POST":
                response = await client.post(url, headers=headers, params=params, json=body)
            elif method == "PUT":
                response = await client.put(url, headers=headers, params=params, json=body)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Check if the response was successful
            response.raise_for_status()
            
            return self._process_response(response, url)
    
    def _process_response(self, response: httpx.Response, url: str) -> str:
        """
        Process an HTTP response based on content type.
        
        Args:
            response: The HTTP response
            url: The request URL
            
        Returns:
            Processed response as a string
        """
        content_type = response.headers.get("content-type", "").lower()
        
        # Define a mapping for common audio content types to file extensions
        audio_type_to_extension = {
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/opus": ".opus",
            "audio/aac": ".aac",
            "audio/flac": ".flac",
            "audio/wav": ".wav",
            "audio/wave": ".wav",
            "audio/ogg": ".ogg",
            # Add more mappings as needed
        }
        
        file_extension = None
        for audio_type, ext in audio_type_to_extension.items():
            if audio_type in content_type:
                file_extension = ext
                break
        
        # If we determined a file extension or the URL suggests audio, treat as audio
        is_audio_response = file_extension is not None or "/audio/" in url.lower()
        
        if is_audio_response:
            # If we couldn't determine extension from content-type but URL implies audio,
            # default to .audio or a generic binary extension, or perhaps try to guess from URL path.
            # For now, let's default to .mp3 if URL implies audio but type is unknown/unmapped.
            if not file_extension and "/audio/" in url.lower():
                logger.warning(f"Could not determine specific audio type for {url} with content-type {content_type}, defaulting to .mp3 due to /audio/ in URL.")
                file_extension = ".mp3"
            elif not file_extension:
                # This case means content_type wasn't in our map and /audio/ not in URL, 
                # but is_audio_response was true (which is now impossible based on logic above).
                # However, to be safe, or if logic changes:
                logger.warning(f"Unmapped audio content type: {content_type} for URL {url}. Cannot save with specific extension.")
                # Fall through to JSON/text processing or return raw content if necessary.
                pass # Let it be handled by JSON/text processing below

            if file_extension: # Proceed if we have an extension
                file_id = str(uuid.uuid4())
                # Using a generic name prefix for now, could be derived from tool name or URL later
                file_path = f"/tmp/api_audio_output_{file_id}{file_extension}"
                
                try:
                    with open(file_path, "wb") as f:
                        f.write(response.content)
                    logger.info(f"Saved audio response from {url} to {file_path} (Content-Type: {content_type})")
                    return f"Audio file generated and saved as {file_path}. You can listen to it or download it."
                except Exception as e:
                    logger.error(f"Failed to save audio file {file_path}: {e}")
                    # Fall through to default JSON/text processing if saving fails

        # For JSON responses (if not handled as audio)
        if "application/json" in content_type:
            try:
                return json.dumps(response.json(), indent=2)
            except json.JSONDecodeError:
                logger.warning(f"Content-Type is application/json but failed to decode JSON from {url}. Returning raw text.")
                return response.text
        
        # For text responses (default fallback)
        return response.text

    async def handle_tool_calls(
        self, 
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
                # Extract function name and arguments from the tool call
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                # Log the original function name received from OpenAI
                logger.info(f"Processing tool call with original name: {function_name}")
                
                # Record the tool call - store the original function name as received from OpenAI
                tool_call_msg = self._create_tool_call_message(
                    conversation.chatid, tool_call_id, function_name, function_args
                )
                
                # Add to database
                db.add(tool_call_msg)
                db.commit()
                messages.append(tool_call_msg)
                
                # Execute the tool with the function name as received from OpenAI
                # The _execute_tool function will extract the tool ID if present
                function_result = await self._execute_tool(conversation, function_name, function_args)
                
                # Record the tool result - still use the original function name for consistency
                tool_result_msg = self._create_tool_result_message(
                    conversation.chatid, tool_call_id, function_name, function_result
                )
                
                # Add to database
                db.add(tool_result_msg)
                db.commit()
                messages.append(tool_result_msg)
        
        logger.info(f"Processed {len(messages) // 2} tool calls")
        return messages
    
    def _create_tool_call_message(
        self,
        chat_id: str,
        tool_call_id: str,
        function_name: str,
        function_args: Dict[str, Any]
    ) -> Message:
        """
        Create a message for a tool call.
        
        Args:
            chat_id: The chat ID
            tool_call_id: The tool call ID
            function_name: The function name
            function_args: The function arguments
            
        Returns:
            A Message object
        """
        return Message(
            id=str(uuid.uuid4()),
            chatid=chat_id,
            sender=None,
            sender_name="Oats",
            type=MessageType.TOOL_CALL,
            content=None,
            role="assistant",
            tool_call_id=tool_call_id,
            function_name=function_name,
            function_arguments=json.dumps(function_args)
        )
    
    def _create_tool_result_message(
        self,
        chat_id: str,
        tool_call_id: str,
        function_name: str,
        function_result: str
    ) -> Message:
        """
        Create a message for a tool result.
        
        Args:
            chat_id: The chat ID
            tool_call_id: The tool call ID
            function_name: The function name
            function_result: The function result
            
        Returns:
            A Message object
        """
        return Message(
            id=str(uuid.uuid4()),
            chatid=chat_id,
            sender=None,
            sender_name="Oats",
            type=MessageType.TOOL_RESULT,
            content=None,
            role="tool",
            tool_call_id=tool_call_id,
            function_name=function_name,
            function_result=function_result
        )
    
    async def _execute_tool(
        self,
        conversation: Conversation,
        function_name: str,
        function_args: Dict[str, Any]
    ) -> str:
        """
        Execute a tool based on its type.
        
        Args:
            conversation: The conversation
            function_name: The function name as received from OpenAI
            function_args: The function arguments
            
        Returns:
            The result of the tool execution
        """
        # Get the tool ID from the function name using our mapping
        tool_id = self._get_tool_id_by_name(function_name)
        
        # Find the tool in the database
        tool = None
        
        # First try to find by ID if we found one from the mapping
        if tool_id:
            for t in conversation.chat_settings.tools:
                if t.id == tool_id:
                    tool = t
                    logger.info(f"Found tool by ID: {tool_id}")
                    break
        
        # Fallback: search by name (for backward compatibility)
        if not tool:
            for t in conversation.chat_settings.tools:
                if t.name == function_name:
                    tool = t
                    logger.info(f"Found tool by name: {function_name}")
                    break
        
        if not tool:
            error_msg = f"Tool not found for function: {function_name}"
            logger.error(error_msg)
            return error_msg
        
        # Check if this is an API-linked function
        if tool.api_request_id:
            return await self.execute_api_tool(tool, function_args)
        
        # Handle based on tool_type
        if tool.tool_type == ToolType.FUNCTION:
            # For function tools without API links, we would implement custom logic here
            return f"Executed function {function_name} with args {function_args}. This is a placeholder response."
        
        return f"Unsupported tool type: {tool.tool_type}"

    async def handle_tool_calls_with_array(
        self, 
        tool_calls,
        conversation: Conversation,
        db: Session
    ) -> List[Message]:
        """
        Process tool calls from an array of tool calls (either dict or object style).
        
        Args:
            tool_calls: Array of tool calls (from response.output)
            conversation: The conversation object
            db: Database session
            
        Returns:
            A list of tool call and result messages
        """
        messages = []
        
        # Check if there are any tool calls
        if not tool_calls:
            return messages
        
        # Process each tool call
        for tool_call in tool_calls:
            tool_call_id = None
            function_name = None
            function_args = None
            
            # Handle dict-style tool calls (new API format)
            if isinstance(tool_call, dict):
                if tool_call.get('type') == 'function_call':
                    tool_call_id = tool_call.get('id') or tool_call.get('call_id')
                    function_name = tool_call.get('name')
                    # Arguments might be a JSON string or dict
                    args = tool_call.get('arguments')
                    if isinstance(args, str):
                        try:
                            function_args = json.loads(args)
                        except:
                            function_args = {"text": args}
                    else:
                        function_args = args
            
            # Handle object-style tool calls (legacy format)
            else:
                # First check for type 'function'
                if getattr(tool_call, 'type', None) == 'function':
                    tool_call_id = getattr(tool_call, 'id', None)
                    function_obj = getattr(tool_call, 'function', None)
                    if function_obj:
                        function_name = getattr(function_obj, 'name', None)
                        args = getattr(function_obj, 'arguments', None)
                        if isinstance(args, str):
                            try:
                                function_args = json.loads(args)
                            except:
                                function_args = {"text": args}
                        else:
                            function_args = args
                # Check for ResponseFunctionToolCall objects with type='function_call'
                elif getattr(tool_call, 'type', None) == 'function_call':
                    tool_call_id = getattr(tool_call, 'id', None) or getattr(tool_call, 'call_id', None)
                    function_name = getattr(tool_call, 'name', None)
                    args = getattr(tool_call, 'arguments', None)
                    if isinstance(args, str):
                        try:
                            function_args = json.loads(args)
                        except:
                            function_args = {"text": args}
                    else:
                        function_args = args
                # Then check for ResponseFunctionToolCall objects with direct function property
                elif hasattr(tool_call, 'function') and tool_call.function:
                    tool_call_id = getattr(tool_call, 'id', None)
                    function_name = getattr(tool_call.function, 'name', None)
                    args = getattr(tool_call.function, 'arguments', None)
                    if isinstance(args, str):
                        try:
                            function_args = json.loads(args)
                        except:
                            function_args = {"text": args}
                    else:
                        function_args = args
            
            # Skip if we couldn't extract necessary information
            if not tool_call_id or not function_name or not function_args:
                logger.warning(f"Skipping invalid tool call: {tool_call}")
                continue
            
            # Log the original function name received from OpenAI
            logger.info(f"Processing tool call with original name: {function_name}")
                
            # Record the tool call - store the original function name as received from OpenAI
            tool_call_msg = self._create_tool_call_message(
                conversation.chatid, tool_call_id, function_name, function_args
            )
            
            # Add to database
            db.add(tool_call_msg)
            db.commit()
            messages.append(tool_call_msg)
            
            # Execute the tool with the function name as received from OpenAI
            # The _execute_tool function will extract the tool ID if present
            function_result = await self._execute_tool(conversation, function_name, function_args)
            
            # Record the tool result - still use the original function name for consistency
            tool_result_msg = self._create_tool_result_message(
                conversation.chatid, tool_call_id, function_name, function_result
            )
            
            # Add to database
            db.add(tool_result_msg)
            db.commit()
            messages.append(tool_result_msg)
        
        logger.info(f"Processed {len(messages) // 2} tool calls")
        return messages

    def _register_tool_name_mapping(self, tool_name: str, tool_id: str) -> None:
        """
        Store a mapping between tool name (used with OpenAI) and the actual tool ID.
        
        Args:
            tool_name: The sanitized tool name used with OpenAI
            tool_id: The actual tool ID in the database
        """
        # Initialize the mapping dict if it doesn't exist yet
        if not hasattr(self, '_tool_name_to_id_map'):
            self._tool_name_to_id_map = {}
            
        # Store the mapping
        self._tool_name_to_id_map[tool_name] = tool_id
        logger.info(f"Registered tool name mapping: {tool_name} -> {tool_id}")
        
    def _get_tool_id_by_name(self, function_name: str) -> Optional[str]:
        """
        Get the tool ID from the function name.
        
        Args:
            function_name: The function name received from OpenAI
            
        Returns:
            The corresponding tool ID if found, None otherwise
        """
        # Check if we have a direct mapping
        if hasattr(self, '_tool_name_to_id_map') and function_name in self._tool_name_to_id_map:
            tool_id = self._tool_name_to_id_map[function_name]
            logger.info(f"Found tool ID {tool_id} for function name {function_name}")
            return tool_id
            
        # Legacy support - try to extract ID from the end of the name (assuming format like name_id)
        parts = function_name.split('_')
        if len(parts) > 1:
            # Try the last part as a potential tool ID prefix
            potential_id_prefix = parts[-1]
            if hasattr(self, '_tool_name_to_id_map'):
                # Look for any tool ID that starts with this prefix
                for tool_id in self._tool_name_to_id_map.values():
                    if tool_id.startswith(potential_id_prefix):
                        logger.info(f"Found tool ID {tool_id} for function name {function_name} via prefix match")
                        return tool_id
                        
        logger.warning(f"Could not find tool ID for function name: {function_name}")
        return None

# Create a singleton instance of OpenAIHelper
# Read the API key directly from the .env file to bypass any environment caching issues
def _read_api_key_from_env_file():
    # First, try the direct path in the app directory
    try:
        with open("/app/.env", "r") as f:
            content = f.read()
            # Find the line starting with OPENAI_API_KEY
            if "OPENAI_API_KEY=" in content:
                # Extract everything after OPENAI_API_KEY= until the next newline or end of file
                key_part = content.split("OPENAI_API_KEY=")[1]
                # If there's another key after this one, only take up to that point
                if "\n" in key_part:
                    key = key_part.split("\n")[0]
                else:
                    key = key_part
                # Clean up any whitespace
                key = key.replace("\n", "").strip()
                logger.info(f"Successfully read API key from /app/.env: {key[:6]}...")
                return key
    except Exception as e:
        logger.error(f"Error reading from /app/.env: {str(e)}")
        
    # Try the project root
    try:
        with open(".env", "r") as f:
            content = f.read()
            # Find the line starting with OPENAI_API_KEY
            if "OPENAI_API_KEY=" in content:
                # Extract everything after OPENAI_API_KEY= until the next newline or end of file
                key_part = content.split("OPENAI_API_KEY=")[1]
                # If there's another key after this one, only take up to that point
                if "\n" in key_part:
                    key = key_part.split("\n")[0]
                else:
                    key = key_part
                # Clean up any whitespace
                key = key.replace("\n", "").strip()
                logger.info(f"Successfully read API key from .env: {key[:6]}...")
                return key
    except Exception as e:
        logger.error(f"Error reading from .env: {str(e)}")
    
    return None

api_key = _read_api_key_from_env_file() or os.getenv("OPENAI_API_KEY")
logger.info(f"Initializing OpenAI Helper with key from file: {api_key[:6] + '...' if api_key else 'None'}")
openai_helper = OpenAIHelper(api_key=api_key) 