import os
import logging
import json
import httpx
import uuid
from typing import List, Dict, Any, Optional, Union
from openai import OpenAI
from sqlalchemy.orm import Session

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
            
            response = self.client.responses.create(
                model=chat_settings.model,
                input=formatted_messages,
                tools=tools if tools else None
            )
            
            # Check if the response contains tool calls and process them
            if hasattr(response, "tool_calls") and response.tool_calls:
                logger.info(f"Response contains {len(response.tool_calls)} tool calls")
                
                # Process tool calls and get tool messages
                tool_messages = await self.handle_tool_calls(response, conversation, db)
                
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
                logger.info(f"Tool: {tool.id} - {tool.name} - {tool.type}")
            
            tools = self.format_tools_for_openai(chat_settings.tools)
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
                            
                            # Make a deep copy to avoid modifying the original
                            function_def = {"type": "function"}
                            
                            # Check if we already have a complete function schema
                            if tool.function_schema and isinstance(tool.function_schema, dict):
                                function_schema = tool.function_schema.copy()
                                
                                # Ensure required name field exists
                                if "name" not in function_schema:
                                    function_schema["name"] = tool.name
                                
                                # Ensure description exists
                                if "description" not in function_schema and tool.description:
                                    function_schema["description"] = tool.description
                                
                                function_def["function"] = function_schema
                            else:
                                # Build function schema from API request
                                function_def["function"] = {
                                    "name": tool.name or f"{api_request.method.lower()}_{api_request.path.replace('/', '_')}",
                                    "description": tool.description or api_request.description or f"Call {api_request.path}",
                                    "parameters": self._build_parameters_from_api_request(api_request)
                                }
                            openai_tools.append(function_def)
                        elif tool.function_schema:
                            # Custom function tool with direct schema
                            # Make a deep copy to avoid modifying the original
                            function_schema = tool.function_schema.copy() if isinstance(tool.function_schema, dict) else {}
                            
                            # Ensure the schema has name and description fields
                            if "name" not in function_schema:
                                function_schema["name"] = tool.name
                            if "description" not in function_schema and tool.description:
                                function_schema["description"] = tool.description
                            
                            # Ensure parameters field exists
                            if "parameters" not in function_schema:
                                function_schema["parameters"] = {"type": "object", "properties": {}, "required": []}
                                
                            function_def = {
                                "type": "function",
                                "function": function_schema
                            }
                            openai_tools.append(function_def)
                        else:
                            # Fallback for function tools without schema
                            function_def = {
                                "type": "function",
                                "function": {
                                    "name": tool.name,
                                    "description": tool.description or "Call a function",
                                    "parameters": {"type": "object", "properties": {}, "required": []}
                                }
                            }
                            openai_tools.append(function_def)
                
                # Backward compatibility for old tool structure
                else:
                    config = tool.configuration or {}
                    if "type" in config:
                        config_type = config.get("type")
                        if config_type in ["web_search", "web_search_preview"]:
                            ws_tool = {"type": "web_search_preview"}
                            if "user_location" in config:
                                ws_tool["user_location"] = config["user_location"]
                            if "search_context_size" in config:
                                ws_tool["search_context_size"] = config["search_context_size"]
                            openai_tools.append(ws_tool)
                        elif config_type == "function":
                            # Ensure the function config has a name
                            if "function" in config and isinstance(config["function"], dict):
                                if "name" not in config["function"]:
                                    config_copy = config.copy()
                                    config_copy["function"] = config["function"].copy()
                                    config_copy["function"]["name"] = tool.name
                                    openai_tools.append(config_copy)
                                else:
                                    openai_tools.append(config)
                            else:
                                openai_tools.append(config)
                    elif tool.type == "function":
                        function_def = {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description or "Function tool",
                                "parameters": config.get("parameters", {"type": "object", "properties": {}, "required": []})
                            }
                        }
                        openai_tools.append(function_def)
            except Exception as e:
                logger.error(f"Error formatting tool {tool.name} ({tool.id}): {e}")
                
        logger.info(f"Returning {len(openai_tools)} formatted tools")
        return openai_tools
    
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
                "content": None,
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
            config = tool.configuration
            
            # Extract endpoint, method, and server_url if available
            endpoint = config.get("endpoint", "")
            method = config.get("method", "GET").upper()
            server_url = config.get("server_url", "")
            
            # Construct full URL
            full_url = f"{server_url}{endpoint}" if server_url else endpoint
            
            # Prepare request parameters
            headers, params, body = self._prepare_request_params(config, arguments)
            
            # Log the request details
            logger.info(f"Executing API tool {tool.name} ({tool.id}): {method} {full_url}")
            logger.info(f"Headers: {headers}")
            logger.info(f"Params: {params}")
            logger.info(f"Body: {body}")
            
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
        # Check for binary data (like audio files)
        content_type = response.headers.get("content-type", "")
        
        # Special handling for audio responses from speech API
        if "audio/mpeg" in content_type or "audio/mp3" in content_type or "/audio/" in url:
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
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                logger.info(f"Processing tool call: {function_name} with args: {function_args}")
                
                # Record the tool call
                tool_call_msg = self._create_tool_call_message(
                    conversation.chatid, tool_call_id, function_name, function_args
                )
                
                # Add to database
                db.add(tool_call_msg)
                db.commit()
                messages.append(tool_call_msg)
                
                # Execute the tool
                function_result = await self._execute_tool(conversation, function_name, function_args)
                
                # Record the tool result
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
            function_name: The function name
            function_args: The function arguments
            
        Returns:
            The result of the tool execution
        """
        # Find the tool in the database
        tool = None
        for t in conversation.chat_settings.tools:
            if t.name == function_name:
                tool = t
                break
        
        if not tool:
            return "Tool not found."
        
        # Check if this is an API-linked function
        if tool.api_request_id:
            return await self.execute_api_tool(tool, function_args)
        
        # Handle based on tool_type
        if tool.tool_type == ToolType.FUNCTION:
            # For function tools without API links, we would implement custom logic here
            return f"Executed function {function_name} with args {function_args}. This is a placeholder response."
        
        return f"Unsupported tool type: {tool.tool_type}"

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