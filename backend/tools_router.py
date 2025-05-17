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
from models import Tool, ToolCreate, ToolUpdate, ToolResponse, ChatSettings, ToolType, ApiToolConfig, OpenAIToolConfig, MessageToolConfig, Conversation, ApiRequest, Api
from openai_helper import openai_helper

logger = logging.getLogger(__name__)
router = APIRouter()

# Tool CRUD operations
@router.post("/tools", response_model=ToolResponse)
async def create_tool(tool: ToolCreate, db: Session = Depends(get_db)):
    # Generate a UUID for the id
    tool_id = str(uuid.uuid4())
    
    name = tool.name
    description = tool.description
    function_schema = None
    
    # Validate tool configuration
    if tool.tool_type == ToolType.FUNCTION:
        # Validate function schema for function tools
        if tool.api_request_id:
            # Check if API request exists
            api_request = db.query(ApiRequest).filter(ApiRequest.id == tool.api_request_id).first()
            if not api_request:
                raise HTTPException(
                    status_code=400, 
                    detail=f"API request with ID {tool.api_request_id} not found"
                )
                
            # If linking to an API request, ensure we have a proper function schema
            # Get the API record to add more context if needed
            api = db.query(Api).filter(Api.id == api_request.api_id).first()
            
            # Generate or enhance the name if needed
            if not name or name.strip() == "":
                # Create a function-friendly name from the API request
                method = api_request.method.lower()
                path_part = api_request.path.replace('/', '_').replace('{', '').replace('}', '').strip('_')
                name = f"{method}_{path_part}"
            
            # Generate or enhance the description if needed
            if not description or description.strip() == "":
                api_name = api.service if api else "API"
                server = api.server if api else ""
                full_path = f"{server}{api_request.path}" if server and not api_request.path.startswith(server) else api_request.path
                description = api_request.description or f"{api_request.method} request to {full_path} ({api_name})"
            
            # Build parameters schema from API request if not provided
            if not tool.function_schema:
                parameters_schema = {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
                
                # Use request_body_schema if available
                if api_request.request_body_schema:
                    if isinstance(api_request.request_body_schema, dict):
                        schema = api_request.request_body_schema
                        if "properties" in schema:
                            parameters_schema["properties"] = schema["properties"]
                        if "required" in schema:
                            parameters_schema["required"] = schema["required"]
                
                # Create the complete function schema
                function_schema = {
                    "name": name,
                    "description": description,
                    "parameters": parameters_schema
                }
            else:
                # Ensure the provided function schema has name and description fields
                function_schema = tool.function_schema.copy() if isinstance(tool.function_schema, dict) else {}
                if "name" not in function_schema:
                    function_schema["name"] = name
                if "description" not in function_schema:
                    function_schema["description"] = description
                if "parameters" not in function_schema:
                    function_schema["parameters"] = {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
        elif not tool.function_schema:
            # Function tools must have either an API request or a function schema
            raise HTTPException(
                status_code=400,
                detail="Function tools must have either an API request ID or a function schema"
            )
        else:
            # Custom function schema was provided, just ensure it has a name field
            function_schema = tool.function_schema.copy() if isinstance(tool.function_schema, dict) else {}
            
            # Generate a name if not provided
            if not name and "name" in function_schema:
                name = function_schema["name"]
            elif not name:
                name = f"custom_function_{tool_id[:8]}"
                
            # Ensure function schema has a name field
            if "name" not in function_schema:
                function_schema["name"] = name
            
            # Generate a description if not provided
            if not description and "description" in function_schema:
                description = function_schema["description"]
            elif not description:
                description = "Custom function tool"
                
            # Ensure function schema has a description
            if "description" not in function_schema:
                function_schema["description"] = description
                
            # Ensure function schema has parameters
            if "parameters" not in function_schema:
                function_schema["parameters"] = {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
    else:
        # For non-function tools, just use the provided schema
        function_schema = tool.function_schema
        
        # Generate default name and description if not provided
        if not name:
            name = f"{tool.tool_type}_tool_{tool_id[:8]}"
        if not description:
            description = f"Tool of type {tool.tool_type}"
    
    # Create new tool DB record using new schema
    db_tool = Tool(
        id=tool_id,
        name=name,
        description=description,
        type=str(tool.tool_type),  # Store tool_type in legacy type field for backward compatibility
        tool_type=tool.tool_type,
        api_request_id=tool.api_request_id,
        function_schema=function_schema,
        configuration={},  # Empty configuration for new tools
        created_at=datetime.utcnow()
    )
    
    # Add to database
    db.add(db_tool)
    
    # Commit the transaction
    db.commit()
    db.refresh(db_tool)
    
    logger.info(f"Created tool with ID: {tool_id}, type: {tool.tool_type}")
    
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
        # For API-linked tools, check if it's already associated or needs to be copied
        if tool.api_request_id and tool.id not in current_tool_ids:
            # Generate a new UUID for the copy
            new_tool_id = str(uuid.uuid4())
            
            # Create a new tool with the same API request but customized for this chat settings
            tool_copy = Tool(
                id=new_tool_id,
                name=f"{tool.name} ({settings_id[:8]})",  # Add identifier to the name
                description=tool.description,
                type=ToolType.FUNCTION,
                tool_type=ToolType.FUNCTION,
                api_request_id=tool.api_request_id,
                function_schema=tool.function_schema.copy() if tool.function_schema else None,
                configuration={},  # Empty configuration for modern tools
                created_at=datetime.utcnow()
            )
            
            # Add to database
            db.add(tool_copy)
            db.commit()
            db.refresh(tool_copy)
            
            logger.info(f"Created copy of API-linked tool {tool.id} with ID: {new_tool_id} for chat settings {settings_id}")
            
            # Use the copy
            final_tools.append(tool_copy)
            final_tool_ids.append(new_tool_id)
        else:
            # Use the original tool for non-API tools or already associated API tools
            final_tools.append(tool)
            final_tool_ids.append(tool.id)
    
    # Associate tools with chat settings
    chat_settings.tools = final_tools
    chat_settings.enabled_tools = final_tool_ids  # For backward compatibility
    
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
    
    # For API-linked tools, create a copy instead of using the original
    if tool.api_request_id:
        # Generate a new UUID for the copy
        new_tool_id = str(uuid.uuid4())
        
        # Create a new tool with the same API request but customized for this chat settings
        tool_copy = Tool(
            id=new_tool_id,
            name=f"{tool.name} ({settings_id[:8]})",  # Add identifier to the name
            description=tool.description,
            type=ToolType.FUNCTION,
            tool_type=ToolType.FUNCTION,
            api_request_id=tool.api_request_id,
            function_schema=tool.function_schema.copy() if tool.function_schema else None,
            configuration={},  # Empty configuration for modern tools
            created_at=datetime.utcnow()
        )
        
        # Add to database
        db.add(tool_copy)
        db.commit()
        db.refresh(tool_copy)
        
        logger.info(f"Created copy of API-linked tool {tool_id} with ID: {new_tool_id} for chat settings {settings_id}")
        
        # Use the copy instead of the original
        tool = tool_copy
        tool_id = new_tool_id
    
    # Check if tool is already associated with chat settings
    if tool in chat_settings.tools:
        logger.info(f"Tool {tool_id} is already associated with chat settings {settings_id}")
        return tool
    
    # Associate tool with chat settings
    chat_settings.tools.append(tool)
    
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
    api_id: str
    api_name: str
    api_requests_created: int
    api_requests: List[Dict[str, Any]]

@router.post("/tools/import-openapi", response_model=OpenAPIImportResponse)
async def import_openapi_spec(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Import an OpenAPI specification (JSON or YAML) and create API and API request records.
    This does NOT automatically create tools - you need to explicitly create tools from the API requests.
    
    Args:
        file: The OpenAPI spec file (JSON or YAML)
        db: Database session
    
    Returns:
        OpenAPIImportResponse with the number of API requests created and their details
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
        
        # First, create an API record for this OpenAPI spec
        api_id = str(uuid.uuid4())
        
        # Get API metadata from the spec
        api_title = spec.get('info', {}).get('title', 'Imported API')
        api_version = spec.get('info', {}).get('version', '1.0.0')
        api_description = spec.get('info', {}).get('description', f'Imported from {file.filename}')
        
        # Determine server URL from OpenAPI spec if available
        server_url = ""
        if 'servers' in spec and len(spec['servers']) > 0:
            server_obj = spec['servers'][0]
            if 'url' in server_obj:
                server_url = server_obj['url']
        
        # Create the API record
        db_api = Api(
            id=api_id,
            server=server_url,
            service=api_title,
            provider=spec.get('info', {}).get('contact', {}).get('name', 'Unknown'),
            version=api_version,
            description=api_description,
            processed=True
        )
        
        # Add to database
        db.add(db_api)
        db.commit()
        db.refresh(db_api)
        
        logger.info(f"Created API record with ID: {api_id}")
        
        # List to store created API requests
        api_requests = []
        
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
                
                # Create a UUID for the API request
                api_request_id = str(uuid.uuid4())
                
                # Create API request record
                db_api_request = ApiRequest(
                    id=api_request_id,
                    api_id=api_id,
                    path=path,
                    method=method.upper(),
                    description=description,
                    request_body_schema=request_schema,
                    skip_parameters=None,
                    constant_parameters=None
                )
                
                # Add to database
                db.add(db_api_request)
                
                # Add to the list of created API requests
                api_requests.append({
                    "id": api_request_id,
                    "path": path,
                    "method": method.upper(),
                    "description": description,
                    "operation_id": operation_id
                })
        
        # Commit all to the database
        db.commit()
        
        logger.info(f"Created {len(api_requests)} API requests from OpenAPI spec")
        
        # Return response with API requests info
        return OpenAPIImportResponse(
            api_id=api_id,
            api_name=api_title,
            api_requests_created=len(api_requests),
            api_requests=api_requests
        )
        
    except HTTPException as e:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log the error and return a 500
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

@router.get("/api-requests", response_model=List[Dict[str, Any]])
async def get_api_requests(db: Session = Depends(get_db)):
    """
    Get all API requests in the database.
    
    Returns:
        List of API requests
    """
    try:
        # Get all API requests
        api_requests = db.query(ApiRequest).all()
        
        # Convert to response format
        response = []
        for req in api_requests:
            # Get the API details
            api = db.query(Api).filter(Api.id == req.api_id).first()
            
            response.append({
                "id": req.id,
                "api_id": req.api_id,
                "path": req.path,
                "method": req.method,
                "description": req.description,
                "service": api.service if api else None,
                "server": api.server if api else None,
                "provider": api.provider if api else None,
                "request_body_schema": req.request_body_schema
            })
        
        logger.info(f"Fetched {len(response)} API requests")
        return response
    except Exception as e:
        logger.error(f"Error getting API requests: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching API requests: {str(e)}")

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