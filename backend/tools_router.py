from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging
import uuid
from datetime import datetime
import yaml
import json
from pydantic import BaseModel

from db import get_db
from models import Tool, ToolCreate, ToolUpdate, ToolResponse, ChatSettings, ToolType, ApiToolConfig, OpenAIToolConfig, MessageToolConfig, Conversation
from openai_helper import openai_helper

logger = logging.getLogger(__name__)
router = APIRouter()

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

@router.get("/chat-settings/{chat_id}/openai-tools", response_model=List[Dict[str, Any]])
def get_openai_tools_for_chat(chat_id: str, db: Session = Depends(get_db)):
    """
    Get formatted OpenAI tools for a chat settings.
    
    Args:
        chat_id: The chat settings ID
        
    Returns:
        List of formatted tools
    """
    # Find the chat settings
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == chat_id).first()
    if not chat_settings:
        raise HTTPException(status_code=404, detail=f"Chat settings with ID {chat_id} not found")
    
    # Format the tools for OpenAI
    tools = []
    if chat_settings.tools:
        logger.info(f"Formatting {len(chat_settings.tools)} tools for OpenAI")
        tools = openai_helper.format_tools_for_openai(chat_settings.tools)
    
    logger.info(f"Formatted {len(tools)} OpenAI tools for chat settings {chat_id}")
    return tools

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
    
    # Get current tools for comparison
    current_tool_ids = [t.id for t in chat_settings.tools]
    
    # Prepare the list of tools to associate
    final_tools = []
    final_tool_ids = []
    
    for tool in tools:
        # For API tools, check if it's already associated or needs to be copied
        if tool.type == ToolType.API_TOOL and tool.id not in current_tool_ids:
            # Generate a new UUID for the copy
            new_tool_id = str(uuid.uuid4())
            
            # Copy the configuration
            config_copy = tool.configuration.copy()
            
            # Create new tool
            tool_copy = Tool(
                id=new_tool_id,
                name=f"{tool.name} ({settings_id[:8]})",  # Add identifier to the name
                description=tool.description,
                type=tool.type,
                configuration=config_copy,
                created_at=datetime.utcnow()
            )
            
            # Add to database
            db.add(tool_copy)
            db.commit()
            db.refresh(tool_copy)
            
            logger.info(f"Created copy of API tool {tool.id} with ID: {new_tool_id} for chat settings {settings_id}")
            
            # Use the copy
            final_tools.append(tool_copy)
            final_tool_ids.append(new_tool_id)
        else:
            # Use the original tool for non-API tools or already associated API tools
            final_tools.append(tool)
            final_tool_ids.append(tool.id)
    
    # Associate tools with chat settings
    chat_settings.tools = final_tools
    chat_settings.enabled_tools = final_tool_ids
    
    # Save changes
    db.add(chat_settings)
    db.commit()
    db.refresh(chat_settings)
    
    logger.info(f"Updated tools for chat settings {settings_id}")
    return final_tools

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
    
    # For API tools, create a copy instead of using the original
    if tool.type == ToolType.API_TOOL:
        # Generate a new UUID for the copy
        new_tool_id = str(uuid.uuid4())
        
        # Copy the configuration
        config_copy = tool.configuration.copy()
        
        # Create new tool
        tool_copy = Tool(
            id=new_tool_id,
            name=f"{tool.name} ({settings_id[:8]})",  # Add identifier to the name
            description=tool.description,
            type=tool.type,
            configuration=config_copy,
            created_at=datetime.utcnow()
        )
        
        # Add to database
        db.add(tool_copy)
        db.commit()
        db.refresh(tool_copy)
        
        logger.info(f"Created copy of API tool {tool_id} with ID: {new_tool_id} for chat settings {settings_id}")
        
        # Use the copy instead of the original
        tool = tool_copy
        tool_id = new_tool_id
    
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

@router.put("/chat-settings/{settings_id}/tools/{tool_id}/headers")
async def update_api_tool_headers(
    settings_id: str,
    tool_id: str,
    headers: Dict[str, str],
    db: Session = Depends(get_db)
):
    """
    Update the headers configuration for an API tool associated with a specific chat settings.
    
    Args:
        settings_id: The chat settings ID
        tool_id: The tool ID
        headers: A dictionary of header name to header value
        db: Database session
        
    Returns:
        The updated tool
    """
    # Check if chat settings exists
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    if not chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    # Find the tool in chat settings
    tool = None
    for t in chat_settings.tools:
        if t.id == tool_id:
            tool = t
            break
    
    if not tool:
        logger.warning(f"Tool {tool_id} not found in chat settings {settings_id}")
        raise HTTPException(status_code=404, detail="Tool not found in chat settings")
    
    # Verify it's an API tool
    if tool.type != ToolType.API_TOOL:
        logger.warning(f"Tool {tool_id} is not an API tool")
        raise HTTPException(status_code=400, detail="Only API tools can have headers updated")
    
    # Update headers
    try:
        # Get the current configuration and make a deep copy
        config = json.loads(json.dumps(tool.configuration))
        
        # Update the headers
        if "headers" not in config:
            config["headers"] = {}
        
        # Add or update headers
        for header_name, header_value in headers.items():
            config["headers"][header_name] = header_value
        
        logger.info(f"Updating headers for tool {tool_id}: {config['headers']}")
        
        # Update the tool configuration 
        tool.configuration = config
        tool.updated_at = datetime.utcnow()
        
        # Save changes
        db.add(tool)
        db.commit()
        db.refresh(tool)
        
        # Check if the update worked
        updated_headers = tool.configuration.get("headers", {})
        logger.info(f"Tool headers after update: {updated_headers}")
        
        logger.info(f"Updated headers for API tool {tool_id} in chat settings {settings_id}")
        
        return tool
        
    except Exception as e:
        logger.error(f"Error updating headers for API tool {tool_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating tool headers: {str(e)}")

class OpenAPIImportResponse(BaseModel):
    tools_created: int
    tools: List[ToolResponse]

@router.post("/tools/import-openapi", response_model=OpenAPIImportResponse)
async def import_openapi_spec(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Import an OpenAPI specification (JSON or YAML) and create API tools for each endpoint.
    
    Args:
        file: The OpenAPI spec file (JSON or YAML)
        db: Database session
    
    Returns:
        OpenAPIImportResponse with the number of tools created and their details
    """
    try:
        # Read file content
        content = await file.read()
        
        # Determine if the content is JSON or YAML
        try:
            if file.filename.endswith('.json'):
                spec = json.loads(content)
            elif file.filename.endswith('.yaml') or file.filename.endswith('.yml'):
                spec = yaml.safe_load(content)
            else:
                # Try to parse as JSON first, then YAML if that fails
                try:
                    spec = json.loads(content)
                except json.JSONDecodeError:
                    spec = yaml.safe_load(content)
        except Exception as e:
            logger.error(f"Error parsing OpenAPI spec: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid OpenAPI specification: {str(e)}")
        
        # Validate that it's an OpenAPI spec
        if 'openapi' not in spec:
            raise HTTPException(status_code=400, detail="File is not a valid OpenAPI specification")
        
        # List to store created tools
        created_tools = []
        
        # Process paths and operations
        for path, path_item in spec.get('paths', {}).items():
            # Get path parameters if any
            path_parameters = path_item.get('parameters', [])
            
            # Process each operation (GET, POST, etc.)
            for method, operation in path_item.items():
                # Skip non-operation fields like 'parameters'
                if method in ['parameters', 'summary', 'description', 'servers']:
                    continue
                
                # Get operation details
                operation_id = operation.get('operationId')
                if not operation_id:
                    # Create a sanitized operation ID if not provided
                    sanitized_path = path.replace('/', '_').replace('{', '').replace('}', '')
                    operation_id = f"{method}{sanitized_path}"
                
                summary = operation.get('summary', f"{method.upper()} {path}")
                description = operation.get('description', summary)
                
                # Combine path parameters with operation parameters
                parameters = path_parameters.copy()
                parameters.extend(operation.get('parameters', []))
                
                # Get request body schema if exists
                request_body = operation.get('requestBody', {})
                request_content = request_body.get('content', {})
                request_schema = None
                
                for content_type, content_obj in request_content.items():
                    if 'schema' in content_obj:
                        schema = content_obj['schema']
                        # Resolve the schema if it's a reference
                        request_schema = resolve_schema_reference_from_spec(schema, spec)
                        break
                
                # Create the API tool configuration
                config = {
                    "endpoint": path,
                    "method": method.upper(),
                    "params": {},
                    "headers": {},
                }
                
                # Get server URL from OpenAPI spec if available
                server_url = ""
                if 'servers' in spec and len(spec['servers']) > 0:
                    server_obj = spec['servers'][0]
                    if 'url' in server_obj:
                        server_url = server_obj['url']
                        # If server URL doesn't end with a slash but path starts with one, 
                        # it will be preserved, otherwise add a prefix separator
                        if not server_url.endswith('/') and not path.startswith('/'):
                            server_url += '/'
                
                # If we have a server URL, use it with the path
                if server_url:
                    config["server_url"] = server_url
                
                # If there's a request body schema, store the fully resolved schema
                if request_schema:
                    config["body_schema"] = request_schema
                
                # Add parameters to config
                for param in parameters:
                    param_name = param.get('name')
                    param_location = param.get('in')  # query, path, header, cookie
                    param_required = param.get('required', False)
                    param_schema = param.get('schema', {})
                    
                    # Resolve parameter schema if it's a reference
                    resolved_param_schema = resolve_schema_reference_from_spec(param_schema, spec)
                    
                    if param_location == 'query':
                        config['params'][param_name] = {
                            'required': param_required,
                            'schema': resolved_param_schema,
                            'description': param.get('description', '')
                        }
                    elif param_location == 'header':
                        config['headers'][param_name] = {
                            'required': param_required,
                            'schema': resolved_param_schema,
                            'description': param.get('description', '')
                        }
                
                # Create function-friendly name
                function_name = operation_id.replace('-', '_').replace(' ', '_').lower()
                
                # Generate a UUID for the id
                tool_id = str(uuid.uuid4())
                
                # Prepare a description that properly describes what the API does
                tool_description = description or f"{method.upper()} {path}"
                if server_url:
                    full_url = f"{server_url}{path}" if not path.startswith('/') else f"{server_url}{path[1:]}"
                    tool_description += f" (Endpoint: {full_url})"
                
                # Create the tool object
                tool_config = ApiToolConfig(
                    endpoint=config['endpoint'],
                    method=config['method'],
                    params=config['params'],
                    headers=config['headers'],
                    body_schema=config.get('body_schema'),
                    server_url=config.get('server_url', "")
                )
                
                # Create new tool DB record
                db_tool = Tool(
                    id=tool_id,
                    name=function_name,
                    description=tool_description,
                    type=ToolType.API_TOOL,
                    configuration=tool_config.dict(),
                    created_at=datetime.utcnow()
                )
                
                # Add to database
                db.add(db_tool)
                
                # Add to the list of created tools
                created_tools.append(db_tool)
        
        # Commit all tools to the database
        db.commit()
        
        # Refresh all tools to get their updated database values
        for tool in created_tools:
            db.refresh(tool)
        
        logger.info(f"Created {len(created_tools)} API tools from OpenAPI spec")
        
        # Convert SQLAlchemy models to Pydantic models for the response
        response_tools = []
        for tool in created_tools:
            # Extract configuration as a dictionary
            if isinstance(tool.configuration, dict):
                config = tool.configuration
            else:
                config = json.loads(json.dumps(tool.configuration))
                
            # Create the appropriate config model based on the tool type
            if tool.type == ToolType.API_TOOL:
                config_model = ApiToolConfig(**config)
            elif tool.type == ToolType.OPENAI_TOOL:
                config_model = OpenAIToolConfig(**config)
            else:
                config_model = MessageToolConfig(**config)
                
            # Create the response object
            response_tool = ToolResponse(
                id=tool.id,
                name=tool.name,
                description=tool.description,
                type=tool.type,
                configuration=config_model,
                created_at=tool.created_at,
                updated_at=tool.updated_at
            )
            response_tools.append(response_tool)
        
        return OpenAPIImportResponse(
            tools_created=len(response_tools),
            tools=response_tools
        )
        
    except Exception as e:
        logger.error(f"Error importing OpenAPI spec: {e}")
        raise HTTPException(status_code=500, detail=f"Error importing OpenAPI spec: {str(e)}")

def resolve_schema_reference_from_spec(schema: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively resolve schema references from the OpenAPI spec.
    
    Args:
        schema: The schema object which might contain references
        spec: The complete OpenAPI specification
        
    Returns:
        The fully resolved schema
    """
    if not isinstance(schema, dict):
        return schema
    
    # Make a copy to avoid modifying the original
    result = {}
    
    # If this is a reference, resolve it
    if "$ref" in schema:
        ref = schema["$ref"]
        
        # Extract reference path - for example "#/components/schemas/CreateSpeechRequest"
        if ref.startswith('#/'):
            path_parts = ref[2:].split('/')
            current = spec
            
            # Navigate through the reference path
            for part in path_parts:
                if part in current:
                    current = current[part]
                else:
                    logger.warning(f"Could not resolve reference {ref}")
                    # If we can't resolve, return with a description of the reference
                    return {
                        "type": "object",
                        "description": f"Schema reference: {ref}. Check API documentation for details."
                    }
            
            # Recursively resolve any nested references
            resolved = resolve_schema_reference_from_spec(current, spec)
            
            # Merge any additional properties from the original reference
            for key, value in schema.items():
                if key != "$ref":
                    if key not in resolved:
                        resolved[key] = value
            
            return resolved
        else:
            # External references not supported in this implementation
            logger.warning(f"External reference not supported: {ref}")
            return {
                "type": "object", 
                "description": f"External schema reference: {ref}. Check API documentation for details."
            }
    
    # Process all fields in the schema
    for key, value in schema.items():
        if isinstance(value, dict):
            # Recursively resolve nested objects
            result[key] = resolve_schema_reference_from_spec(value, spec)
        elif isinstance(value, list):
            # Recursively resolve items in arrays
            result[key] = [
                resolve_schema_reference_from_spec(item, spec) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            # Copy primitive values as is
            result[key] = value
    
    return result 

@router.post("/tools/create-speech-tool/{settings_id}")
async def create_speech_tool(settings_id: str, db: Session = Depends(get_db)):
    """
    Create the OpenAI speech API tool and assign it to the specified chat settings.
    
    Args:
        settings_id: ID of the chat settings to assign the tool to
        db: Database session
        
    Returns:
        The created tool
    """
    try:
        # Check if chat settings exists
        chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
        if not chat_settings:
            logger.warning(f"Chat settings with ID {settings_id} not found.")
            raise HTTPException(status_code=404, detail="Chat settings not found")
        
        # Check if speech tool already exists
        existing_tool = db.query(Tool).filter(Tool.name == "text_to_speech").first()
        
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
                logger.info(f"Assigned existing speech tool to chat settings {settings_id}")
            
            return existing_tool
        
        # Define the speech tool configuration as an API tool
        speech_tool_config = {
            "endpoint": "/audio/speech",
            "method": "POST",
            "server_url": "https://api.openai.com/v1",
            "params": {},
            "headers": {
                "Content-Type": {
                    "required": True,
                    "schema": {"type": "string"},
                    "description": "Content type of the request"
                }
            },
            "body_schema": {
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "description": "The model to use for generating the audio"
                    },
                    "input": {
                        "type": "string",
                        "description": "The text to generate audio for"
                    },
                    "voice": {
                        "type": "string",
                        "description": "The voice to use (alloy, echo, fable, onyx, nova, or shimmer)"
                    },
                    "response_format": {
                        "type": "string",
                        "description": "The format of the audio response (mp3, opus, aac, or flac)"
                    },
                    "speed": {
                        "type": "number",
                        "description": "The speed of the audio (0.25 to 4.0)"
                    }
                },
                "required": ["model", "input", "voice"]
            }
        }
        
        # Create the tool
        tool_id = str(uuid.uuid4())
        speech_tool = Tool(
            id=tool_id,
            name="text_to_speech",
            description="Convert text to speech using OpenAI's Audio API",
            type=ToolType.API_TOOL,
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
        db.refresh(speech_tool)
        
        logger.info(f"Created speech API tool with ID: {tool_id} and assigned it to chat settings {settings_id}")
        
        return speech_tool
        
    except Exception as e:
        logger.error(f"Error creating speech tool: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating speech tool: {str(e)}")

@router.get("/tools/find-settings-by-group-name/{group_name}")
async def find_settings_by_group_name(group_name: str, db: Session = Depends(get_db)):
    """
    Find chat settings by conversation group name.
    
    Args:
        group_name: The group name to search for
        db: Database session
        
    Returns:
        The chat settings ID associated with the conversation
    """
    try:
        # Find conversation by group name
        conversation = db.query(Conversation).filter(Conversation.group_name == group_name).first()
        
        if not conversation:
            logger.warning(f"No conversation found with group_name: {group_name}")
            raise HTTPException(status_code=404, detail=f"No conversation found with group_name: {group_name}")
            
        # Check if chat settings exists
        if not conversation.chat_settings:
            logger.warning(f"No chat settings associated with conversation {conversation.chatid}")
            raise HTTPException(status_code=404, detail="No chat settings found for this conversation")
            
        settings_id = conversation.chat_settings_id
        
        return {"chat_settings_id": settings_id, "conversation_id": conversation.chatid}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding chat settings by group name: {e}")
        raise HTTPException(status_code=500, detail=f"Error finding chat settings: {str(e)}")

# Tool execution endpoint for testing
class ToolExecuteRequest(BaseModel):
    tool_id: str
    arguments: Dict[str, Any]

@router.post("/tools/execute")
async def execute_tool(request: ToolExecuteRequest, db: Session = Depends(get_db)):
    """
    Execute a tool directly for testing purposes
    """
    # Get the tool by ID
    tool = db.query(Tool).filter(Tool.id == request.tool_id).first()
    
    # Check if found
    if not tool:
        logger.warning(f"Tool with ID {request.tool_id} not found.")
        raise HTTPException(status_code=404, detail="Tool not found")
    
    logger.info(f"Executing tool {tool.name} ({tool.id})")
    
    # Execute the tool based on its type
    if tool.type == ToolType.API_TOOL:
        # Execute the API tool
        result_data = await openai_helper.execute_api_tool(tool, request.arguments)
        return {"result": result_data}
    else:
        raise HTTPException(status_code=400, detail=f"Tool type {tool.type} cannot be executed directly") 