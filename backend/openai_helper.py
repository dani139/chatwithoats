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
        logger.info(f"[OpenAI Helper] ENTERING get_openai_response for conversation {conversation.chatid}, user message: {user_message.id}")
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
            
            # Log formatted_messages, tools, and tool_choice before API call
            logger.info(f"[OpenAI Helper] Formatted messages for OpenAI: {json.dumps(formatted_messages, indent=2)}")
            logger.info(f"[OpenAI Helper] Tools for OpenAI API call: {json.dumps(tools, indent=2)}")
            actual_tool_choice = "auto" if tools else None
            logger.info(f"[OpenAI Helper] Tool choice for OpenAI API call: {actual_tool_choice}")
            
            # Final check to ensure all function tools have a name
            if tools:
                for i, tool in enumerate(tools):
                    if tool.get("type") == "function":
                        if "name" not in tool:
                            logger.error(f"[OpenAI Helper] Missing 'name' in function tool at index {i}")
                            # Try to add a placeholder name if missing
                            tool["name"] = f"function_{i}"
                
                logger.info(f"[OpenAI Helper] Final tool payload for Responses API: {json.dumps(tools)}")
            
            logger.info(f"[OpenAI Helper] PREPARING TO CALL OpenAI Responses API with model: {chat_settings.model}")
            response = None # Initialize response to None
            try:
                response = self.client.responses.create(
                    model=chat_settings.model,
                    input=formatted_messages,
                    tools=tools if tools else None,
                    tool_choice=actual_tool_choice
                )
            except httpx.HTTPStatusError as e_http:
                logger.error(f"[OpenAI Helper] HTTPStatusError during OpenAI API call: {e_http}")
                logger.error(f"[OpenAI Helper] HTTPStatusError response: {e_http.response.text if e_http.response else 'No response body'}")
                return f"I encountered an HTTP error: {e_http.response.status_code if e_http.response else 'Unknown status'} - {e_http.response.text if e_http.response else 'Details unavailable'}"
            except Exception as e_sdk_call: # Catch any other exceptions during the call
                logger.error(f"[OpenAI Helper] Exception during OpenAI API call (self.client.responses.create): {str(e_sdk_call)}")
                return f"I'm sorry, I couldn't connect to the AI service: {str(e_sdk_call)}"
            
            # Log the raw response from OpenAI
            logger.info("[OpenAI Helper] Attempting to log Raw OpenAI API response...")
            try:
                raw_response_data = response.model_dump_json(indent=2)
                logger.info(f"[OpenAI Helper] Raw OpenAI API response: {raw_response_data}")
            except Exception as e_dump:
                logger.error(f"[OpenAI Helper] Error serializing raw OpenAI response with model_dump_json: {str(e_dump)}")
                try:
                    logger.info(f"[OpenAI Helper] Raw OpenAI API response (fallback using repr): {repr(response)}")
                except Exception as e_repr:
                    logger.error(f"[OpenAI Helper] Error serializing raw OpenAI response with repr: {str(e_repr)}")
            logger.info("[OpenAI Helper] Raw OpenAI API response END")
            
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
            tool_calls = [] # This will store the extracted calls
            
            # Standard location for tool calls in openai >= 1.x SDK is response.output (list)
            if hasattr(response, "output") and isinstance(response.output, list):
                logger.info(f"[OpenAI Helper] Response has output attribute (list with {len(response.output)} items)")
                extracted_function_calls = []
                for item in response.output:
                    item_type = None
                    if isinstance(item, dict):
                        item_type = item.get('type')
                    elif hasattr(item, 'type'):
                        item_type = getattr(item, 'type')
                    
                    if item_type == 'function_call':
                        extracted_function_calls.append(item)
                    else:
                        logger.info(f"[OpenAI Helper] Skipping item in response.output of type: {item_type}")
                
                if extracted_function_calls:
                    has_tool_calls = True
                    tool_calls = extracted_function_calls
                    logger.info(f"[OpenAI Helper] Found {len(tool_calls)} function_call(s) in response.output list")
            else:
                logger.info("[OpenAI Helper] No tool calls found in response.output list or response.output is not a list.")
            
            logger.info(f"[OpenAI Helper] After checks, Response has tool_calls: {has_tool_calls}")
            
            if has_tool_calls and tool_calls:
                logger.info(f"Response contains {len(tool_calls)} tool calls")
                
                # Process tool calls and get tool messages
                tool_messages = await self.handle_tool_calls_with_array(tool_calls, conversation, db)
                
                # Add these tool messages to our conversation history
                for msg in tool_messages:
                    formatted_messages = self._add_tool_message_to_history(formatted_messages, msg)
                
                # Log the messages being sent for the second call
                logger.info(f"[OpenAI Helper] Messages for second call after tool execution: {json.dumps(formatted_messages, indent=2)}")
                
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
                # This represents the models decision to call a function from history.
                tool_call_object = {
                    "type": "function_call",
                    "id": msg.openai_tool_call_id,    # Use the stored fc_... ID from OpenAI\'s original tool_call
                    "call_id": msg.tool_call_id,     # Use the stored call_... ID for linking
                    "name": msg.openai_function_name,  # MUST be the name OpenAI knows
                    "arguments": msg.function_arguments
                }
                formatted_messages.append(tool_call_object)
            elif msg.type == MessageType.TOOL_RESULT:
                # This was a tool result from history
                formatted_messages.append({
                    "type": "function_call_output",
                    "call_id": msg.tool_call_id,
                    "output": msg.function_result
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
        
        logger.info(f"[OpenAI Helper] _get_tools_for_chat returning: {json.dumps(tools)}")
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
            logger.info(f"[OpenAI Helper] Processing tool in format_tools_for_openai: ID={tool.id}, Name={tool.name}, SkipParams={tool.skip_params}")
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
                            
                            # Initialize name components
                            server_name_str = "unknown_server"
                            version_str = ""
                            endpoint_str = "unknown_endpoint"
                            method_str = (api_request.method.lower() if api_request.method else "post")

                            # Determine the primary URL to parse for server
                            url_to_parse_for_server = None
                            # Priority 1: Server URL from the linked API object (more static and reliable)
                            if hasattr(api_request, 'api') and api_request.api and \
                               hasattr(api_request.api, 'server') and api_request.api.server:
                                url_to_parse_for_server = api_request.api.server
                            # Priority 2: URL directly on the ApiRequest object (might be less common or more dynamic)
                            elif hasattr(api_request, 'url') and api_request.url:
                                url_to_parse_for_server = api_request.url

                            if url_to_parse_for_server:
                                try:
                                    parsed_server_url = urlparse(url_to_parse_for_server)
                                    if parsed_server_url.netloc:
                                        # Replace dots with underscores for the server name part
                                        server_name_str = parsed_server_url.netloc.replace('.', '_')
                                        # Remove common TLDs (e.g., _com, _org) and other generic suffixes
                                        common_suffixes = ['_com', '_org', '_net', '_io', '_ai', '_co_uk', '_gov', '_info', '_biz']
                                        for suffix in common_suffixes:
                                            if server_name_str.endswith(suffix):
                                                server_name_str = server_name_str[:-len(suffix)]
                                                break # Stop after removing one suffix
                                except Exception as e:
                                    logger.warning(f"Failed to parse server URL '{url_to_parse_for_server}' for tool {tool.id}: {e}")
                            
                            # Determine the primary path to parse for version and endpoint
                            path_to_parse_for_endpoint = None
                            # Priority 1: Path from the ApiRequest object itself (most specific)
                            if api_request.path and api_request.path.strip() and api_request.path.strip() != '/':
                                path_to_parse_for_endpoint = api_request.path
                            # Priority 2: Path from the ApiRequest URL (if path above was not specific)
                            elif hasattr(api_request, 'url') and api_request.url:
                                try:
                                    parsed_req_url_path = urlparse(api_request.url).path
                                    if parsed_req_url_path and parsed_req_url_path.strip() and parsed_req_url_path.strip() != '/':
                                        path_to_parse_for_endpoint = parsed_req_url_path
                                except Exception: # nosemgrep
                                    pass # Silently ignore parsing error here, rely on other fallbacks or defaults
                            
                            # Priority 3: Path from the server URL (least specific, e.g. if server is http://host/api/v1)
                            if not path_to_parse_for_endpoint and url_to_parse_for_server:
                                try:
                                    parsed_server_url_path = urlparse(url_to_parse_for_server).path
                                    if parsed_server_url_path and parsed_server_url_path.strip() and parsed_server_url_path.strip() != '/':
                                        path_to_parse_for_endpoint = parsed_server_url_path
                                except Exception: # nosemgrep
                                    pass # Silently ignore

                            if path_to_parse_for_endpoint:
                                path_segments = path_to_parse_for_endpoint.strip('/').split('/')
                                if path_segments and path_segments[0]: # Check if there are any segments
                                    # Check for version-like first segment (e.g., v1, v2.0, v1beta)
                                    if re.match(r'^v[0-9]+(?:[a-zA-Z0-9._-]*)$', path_segments[0]):
                                        version_str = path_segments[0]
                                        endpoint_segments = path_segments[1:] # The rest are endpoint parts
                                    else:
                                        endpoint_segments = path_segments # No version prefix, all are endpoint parts
                                    
                                    current_endpoint_str = '_'.join(segment for segment in endpoint_segments if segment)
                                    if current_endpoint_str: # If we derived something meaningful
                                        endpoint_str = current_endpoint_str
                                    elif version_str: # Path was like "/v1/", endpoint is just base/root for that version
                                        endpoint_str = "base_version_endpoint" 
                                    # If no version_str and current_endpoint_str is empty, endpoint_str remains "unknown_endpoint"
                                elif path_to_parse_for_endpoint.strip('/') == '': # Path was effectively "/"
                                     endpoint_str = "root_api"
                                # else: endpoint_str remains "unknown_endpoint" if path_segments was empty (e.g. path_to_parse was just "/")
                            else: # No path information found at all
                                endpoint_str = "general_action" # Fallback if no path info
                                
                            # Assemble the name components, filtering out defaults if better info exists
                            name_parts = []
                            if server_name_str != "unknown_server": name_parts.append(server_name_str)
                            if version_str: name_parts.append(version_str)
                            if endpoint_str != "unknown_endpoint": name_parts.append(endpoint_str)
                            name_parts.append(method_str)

                            if not name_parts or (len(name_parts) == 1 and name_parts[0] == method_str and server_name_str == "unknown_server" and endpoint_str == "unknown_endpoint" and not version_str) :
                                # If all parts were default/empty except method, or list is empty for some reason
                                formatted_name = f"generic_api_tool_{tool.id[:4]}" # Ultimate fallback to ensure some name
                            else:
                                formatted_name = '_'.join(name_parts)
                            
                            # Ensure no leading/trailing underscores and collapse multiple underscores
                            formatted_name = re.sub(r'_+', '_', formatted_name).strip('_')
                            if not formatted_name: # Still possible if all parts were filtered or became empty
                                formatted_name = f"fallback_tool_name_{tool.id[:4]}"

                            # Clean up the name to ensure it's valid for OpenAI (alphanumeric, _, -)
                            tool_name = self._sanitize_tool_name(formatted_name)
                            
                            # Store the mapping of this name to the full tool ID
                            self._register_tool_name_mapping(tool_name, tool.id)
                            
                            # Log the formatted name being used
                            logger.info(f"[OpenAI Helper] Using formatted function name for API tool: {tool_name} (maps to tool ID: {tool.id})")
                            
                            # Format as per OpenAI's expected structure
                            function_def = {
                                "type": "function",
                                "name": tool_name,
                                "description": tool.description or api_request.description or f"Call {api_request.path}"
                            }
                            
                            # Initialize parameters first
                            if tool.function_schema and isinstance(tool.function_schema, dict) and "parameters" in tool.function_schema:
                                function_def["parameters"] = tool.function_schema["parameters"].copy() # Get parameters from existing schema
                            else:
                                function_def["parameters"] = self._build_parameters_from_api_request(api_request) # Build from API request

                            # Now, apply skip_params if they exist
                            if tool.skip_params:
                                current_parameters = function_def.get("parameters", {})
                                filtered_properties = {}
                                filtered_required = []
                                
                                if "properties" in current_parameters:
                                    for prop_name, prop_schema in current_parameters["properties"].items():
                                        if prop_name not in tool.skip_params:
                                            filtered_properties[prop_name] = prop_schema
                                
                                if "required" in current_parameters:
                                    for req_param in current_parameters["required"]:
                                        if req_param not in tool.skip_params:
                                            filtered_required.append(req_param)
                                
                                function_def["parameters"] = {
                                    "type": "object",
                                    "properties": filtered_properties,
                                    "required": filtered_required
                                }
                                logger.info(f"[OpenAI Helper] Applied skip_params for tool {tool.id} (Name: {tool_name}). Original params: {current_parameters.get('properties', {}).keys()}, Skipped: {tool.skip_params}, Final params: {filtered_properties.keys()}")
                            
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
            tool_call_object = {
                "type": "function_call",
                "id": message.openai_tool_call_id,    # Use the stored fc_... ID
                "call_id": message.tool_call_id,     # Use the stored call_... ID
                "name": message.openai_function_name, # MUST be the name OpenAI knows
                "arguments": message.function_arguments
            }
            formatted_messages.append(tool_call_object)

        elif message.type == MessageType.TOOL_RESULT:
            # This is the result we are sending back
            formatted_messages.append({
                "type": "function_call_output",
                "call_id": message.tool_call_id, # Correctly uses call_... ID for linking output
                "output": message.function_result
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
            
            # Special logging for image generation tool
            if "/images/generations" in endpoint.lower() or "dall" in tool.name.lower():
                logger.info(f"[OpenAI Helper] IMAGE GENERATION REQUEST DETAILS:")
                logger.info(f"[OpenAI Helper] Complete URL: {full_url}")
                logger.info(f"[OpenAI Helper] Method: {method}")
                logger.info(f"[OpenAI Helper] Headers: {json.dumps(headers, indent=2)}")
                logger.info(f"[OpenAI Helper] Body: {json.dumps(body, indent=2)}")
                logger.info(f"[OpenAI Helper] Raw arguments from LLM: {json.dumps(arguments, indent=2)}")
                
                # Check required fields for image generation without modifying them
                if 'model' not in body:
                    logger.warning("[OpenAI Helper] No model specified for image generation. This request may fail.")
                    
                if 'prompt' not in body:
                    logger.warning("[OpenAI Helper] No prompt specified for image generation. This request may fail.")
            
            # For speech tool, log the received arguments from LLM
            if "speech" in tool.name.lower() or (hasattr(api_request, 'path') and "audio" in api_request.path.lower()):
                logger.info(f"[OpenAI Helper] LLM provided arguments for speech tool ({tool.name}): {json.dumps(arguments, indent=2)}")
            
            # Add OpenAI API key if needed
            if "openai.com" in full_url:
                logger.info(f"[OpenAI Helper] Setting Authorization header for OpenAI API call with key: {self.masked_key}")
                headers["Authorization"] = f"Bearer {self.api_key}"
                
                # For OpenAI, ensure Content-Type is set correctly
                if method == "POST" or method == "PUT":
                    headers["Content-Type"] = "application/json"
            
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
        try:
            logger.info(f"Making {method} request to {url}")
            timeout_config = httpx.Timeout(60.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
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
        except httpx.HTTPStatusError as e:
            # Log more detailed information about the failed request
            error_msg = f"Error code: {e.response.status_code} - {e.response.text}"
            logger.error(f"HTTP request failed: {error_msg}")
            
            # For image generation requests, log more detailed information
            if "/images/generations" in url:
                logger.error(f"[OpenAI Helper] IMAGE GENERATION API CALL FAILED:")
                logger.error(f"[OpenAI Helper] URL: {url}")
                logger.error(f"[OpenAI Helper] Status code: {e.response.status_code}")
                logger.error(f"[OpenAI Helper] Response headers: {e.response.headers}")
                logger.error(f"[OpenAI Helper] Response body: {e.response.text}")
                logger.error(f"[OpenAI Helper] Request body: {json.dumps(body, indent=2)}")
            
            return error_msg
        except Exception as e:
            logger.error(f"Unexpected error during HTTP request: str(e)='{str(e)}', repr(e)='{repr(e)}'")
            return f"Error making HTTP request: {str(e)}"
    
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
        openai_tool_call_id: str,
        tool_linking_id: str,
        tool_definition_name: str,
        openai_function_name: str,
        function_args: Dict[str, Any]
    ) -> Message:
        """
        Create a message for a tool call.
        
        Args:
            chat_id: The chat ID
            openai_tool_call_id: The ID of the tool call object from OpenAI (fc_...)
            tool_linking_id: The linking ID for the tool call (call_...)
            tool_definition_name: The canonical name of the tool (e.g., 'text_to_speech')
            openai_function_name: The name used/understood by OpenAI (e.g., 'unknown_audio_post_...')
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
            openai_tool_call_id=openai_tool_call_id,
            tool_call_id=tool_linking_id,
            tool_definition_name=tool_definition_name,
            openai_function_name=openai_function_name,
            function_arguments=json.dumps(function_args)
        )
    
    def _create_tool_result_message(
        self,
        chat_id: str,
        tool_linking_id: str,
        tool_definition_name: str,
        openai_function_name: str,
        function_result: str
    ) -> Message:
        """
        Create a message for a tool result.
        
        Args:
            chat_id: The chat ID
            tool_linking_id: The linking ID for the tool call (call_...)
            tool_definition_name: The canonical name of the tool
            openai_function_name: The name used/understood by OpenAI
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
            tool_call_id=tool_linking_id,
            tool_definition_name=tool_definition_name,
            openai_function_name=openai_function_name,
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
            tool_calls: Array of tool calls (from response.output), named tool_calls_from_openai here
            conversation: The conversation object
            db: Database session
            
        Returns:
            A list of tool call and result messages
        """
        messages = []
        tool_calls_from_openai = tool_calls # Rename for clarity
        
        if not tool_calls_from_openai:
            return messages
        
        for tool_call_from_openai in tool_calls_from_openai:
            openai_fc_id = None
            openai_call_id = None
            current_openai_function_name = None # Renamed from function_name for clarity
            function_args = None
            
            # Handle dict-style tool calls (new API format)
            if isinstance(tool_call_from_openai, dict):
                if tool_call_from_openai.get('type') == 'function_call':
                    openai_fc_id = tool_call_from_openai.get('id') # This is the fc_ ID from OpenAI
                    openai_call_id = tool_call_from_openai.get('call_id') # This is the call_ ID for linking
                    
                    # For Responses API, call_id is the primary one used by OpenAI for linking.
                    # Ensure we have call_id. If fc_id (OpenAI's internal tool_call.id) is missing, we can log but proceed.
                    if not openai_call_id:
                        logger.warning(f"Missing 'call_id' in dict tool_call: {tool_call_from_openai}, attempting to use 'id' as call_id.")
                        openai_call_id = openai_fc_id # Fallback, though not ideal for Responses API
                    if not openai_fc_id:
                        logger.warning(f"Missing 'id' (fc_ id) in dict tool_call: {tool_call_from_openai}. This ID is usually present.")
                        # If fc_id is absolutely required later, this could be an issue.

                    current_openai_function_name = tool_call_from_openai.get('name')
                    args_str = tool_call_from_openai.get('arguments')
                    try:
                        function_args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON arguments for dict tool_call {openai_call_id}. Args: {args_str}")
                        function_args = {"error": "Failed to parse arguments", "arguments_string": args_str}
                else:
                    logger.warning(f"Skipping dict tool_call with unknown type: {tool_call_from_openai.get('type')}")
                    continue
            
            # Handle object-style tool calls (e.g. ResponseFunctionToolCall from openai>=1.x)
            elif hasattr(tool_call_from_openai, 'type') and getattr(tool_call_from_openai, 'type') == 'function_call':
                openai_fc_id = getattr(tool_call_from_openai, 'id', None) # fc_ ID
                openai_call_id = getattr(tool_call_from_openai, 'call_id', None) # call_ ID

                if not openai_call_id:
                    logger.warning(f"Missing 'call_id' in object tool_call: {tool_call_from_openai}, attempting to use 'id' as call_id.")
                    openai_call_id = openai_fc_id
                if not openai_fc_id:
                     logger.warning(f"Missing 'id' (fc_ id) in object tool_call: {tool_call_from_openai}. This ID is usually present.")
                
                current_openai_function_name = getattr(tool_call_from_openai, 'name', None)
                args_val = getattr(tool_call_from_openai, 'arguments', None)
                
                if isinstance(args_val, str):
                    try:
                        function_args = json.loads(args_val)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON arguments for object tool_call {openai_call_id}. Args: {args_val}")
                        function_args = {"error": "Failed to parse arguments", "arguments_string": args_val}
                else:
                    function_args = args_val # Assume it's already a dict if not a string
            else:
                logger.warning(f"Skipping tool_call of unhandled type or structure: {type(tool_call_from_openai)}")
                continue
            
            if not openai_call_id or not current_openai_function_name:
                logger.warning(f"Skipping tool call due to missing openai_call_id or name. Original tool_call: {tool_call_from_openai}")
                continue
            
            # Resolve the canonical tool name
            tool_id = self._get_tool_id_by_name(current_openai_function_name)
            resolved_tool_object = None
            canonical_tool_name = current_openai_function_name # Fallback to openai name if not found
            if tool_id:
                for t_obj in conversation.chat_settings.tools:
                    if t_obj.id == tool_id:
                        resolved_tool_object = t_obj
                        canonical_tool_name = resolved_tool_object.name
                        logger.info(f"Resolved tool: ID='{tool_id}', Canonical Name='{canonical_tool_name}', OpenAI Name='{current_openai_function_name}'")
                        break
            if not resolved_tool_object:
                 logger.warning(f"Could not fully resolve tool object for openai_function_name: {current_openai_function_name}. Using OpenAI name as canonical.")


            logger.info(f"Processing tool call: openai_fc_id='{openai_fc_id}', openai_call_id='{openai_call_id}', openai_name='{current_openai_function_name}', canonical_name='{canonical_tool_name}'")
            
            tool_call_msg = self._create_tool_call_message(
                conversation.chatid, 
                openai_fc_id,
                openai_call_id,
                canonical_tool_name, # Use canonical name
                current_openai_function_name, # Pass OpenAI name
                function_args
            )
            
            db.add(tool_call_msg)
            db.commit() # Commit tool call message first
            messages.append(tool_call_msg)
            
            # _execute_tool uses the current_openai_function_name to find the tool again
            function_result = await self._execute_tool(conversation, current_openai_function_name, function_args)
            
            tool_result_msg = self._create_tool_result_message(
                conversation.chatid, 
                openai_call_id,
                canonical_tool_name, # Use canonical name
                current_openai_function_name, # Pass OpenAI name
                function_result
            )
            
            db.add(tool_result_msg)
            db.commit() # Commit tool result message
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