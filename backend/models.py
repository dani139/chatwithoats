from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, JSON, Integer, Float, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field
from db import Base
import datetime

# Enum types (matching PostgreSQL enum types)
class MessageType(str, Enum):
    TEXT = "TEXT"
    VOICE = "VOICE"
    IMAGE = "IMAGE"
    MEDIA = "MEDIA"
    LOCATION = "LOCATION"
    SYSTEM = "SYSTEM"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"

class SourceType(str, Enum):
    WHATSAPP = "WHATSAPP"
    PORTAL = "PORTAL"

class ToolType(str, Enum):
    FUNCTION = "function"
    WEB_SEARCH = "web_search_preview"
    FILE_SEARCH = "file_search"
    
    # String constants for consistent type references
    FUNCTION_STR = "function"
    WEB_SEARCH_STR = "web_search_preview"
    FILE_SEARCH_STR = "file_search"

# Association table for ChatSettings to Tools many-to-many relationship
chat_settings_tools = Table(
    'chat_settings_tools',
    Base.metadata,
    Column('chat_settings_id', String, ForeignKey('chat_settings.id')),
    Column('tool_id', String, ForeignKey('tools.id'))
)

# SQLAlchemy Models
class PortalUser(Base):
    __tablename__ = "portal_users"
    
    id = Column(String, primary_key=True)
    username = Column(String, nullable=False)
    email = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    conversations = relationship("Conversation", back_populates="portal_user")

class Tool(Base):
    __tablename__ = "tools"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    type = Column(String, nullable=False)  # Legacy column, kept for backwards compatibility
    tool_type = Column(String, nullable=True)  # New column: 'function', 'web_search_preview', etc.
    api_request_id = Column(String, ForeignKey("api_requests.id"), nullable=True)
    configuration = Column(JSON, nullable=False)  # Legacy column, kept for backwards compatibility
    function_schema = Column(JSON, nullable=True)  # New column: Directly stores OpenAI function schema
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    chat_settings = relationship("ChatSettings", secondary=chat_settings_tools, back_populates="tools")
    api_request = relationship("ApiRequest", back_populates="tools")

class ChatSettings(Base):
    __tablename__ = "chat_settings"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    system_prompt = Column(String, nullable=False)
    model = Column(String, nullable=False, default="gpt-4o-mini")
    # enabled_tools removed - we now only use the relationship
    
    # Relationships
    conversations = relationship("Conversation", back_populates="chat_settings")
    tools = relationship("Tool", secondary=chat_settings_tools, back_populates="chat_settings")

class ApiRequest(Base):
    __tablename__ = "api_requests"
    
    id = Column(String, primary_key=True)
    api_id = Column(String, ForeignKey("apis.id"), nullable=False)
    path = Column(String, nullable=False)
    method = Column(String, nullable=False)  # HTTP method (GET, POST, etc.)
    description = Column(String, nullable=True)
    request_body_schema = Column(JSON, nullable=True)
    response_schema = Column(JSON, nullable=True)
    skip_parameters = Column(JSON, nullable=True)
    constant_parameters = Column(JSON, nullable=True)
    
    # Relationships
    api = relationship("Api", back_populates="requests")
    tools = relationship("Tool", back_populates="api_request")

class Api(Base):
    __tablename__ = "apis"
    
    id = Column(String, primary_key=True)
    server = Column(String, nullable=False)
    service = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    version = Column(String, nullable=False)
    description = Column(String, nullable=True)
    processed = Column(Boolean, nullable=False)
    
    # Relationships
    requests = relationship("ApiRequest", back_populates="api")

class Conversation(Base):
    __tablename__ = "conversations"
    
    chatid = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    is_group = Column(Boolean, nullable=False)
    group_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    silent = Column(Boolean, nullable=False)
    enabled_apis = Column(JSON, nullable=False)
    paths = Column(JSON, nullable=False)
    chat_settings_id = Column(String, ForeignKey("chat_settings.id"), nullable=True)
    portal_user_id = Column(String, ForeignKey("portal_users.id"), nullable=True)
    source_type = Column(String, nullable=False, default=SourceType.WHATSAPP)
    
    # Relationships
    participants = relationship("ConversationParticipant", back_populates="conversation")
    messages = relationship("Message", back_populates="conversation")
    chat_settings = relationship("ChatSettings", back_populates="conversations")
    portal_user = relationship("PortalUser", back_populates="conversations")

class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"
    
    # This table doesn't have a primary key in the schema, so we'll create a composite one
    number = Column(String, primary_key=True)
    chatid = Column(String, ForeignKey("conversations.chatid"), primary_key=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="participants")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True)
    chatid = Column(String, ForeignKey("conversations.chatid"), nullable=False)
    sender = Column(String, nullable=True)
    sender_name = Column(String, nullable=True)
    type = Column(String, nullable=False)  # Using MessageType enum value
    content = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    caption = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    quoted_message_id = Column(String, ForeignKey("messages.id"), nullable=True)
    quoted_message_content = Column(String, nullable=True)
    role = Column(String, nullable=True)
    tool_call_id = Column(String, nullable=True)
    function_name = Column(String, nullable=True)
    function_arguments = Column(String, nullable=True)
    function_result = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    quoted_message = relationship("Message", remote_side=[id], backref="quotes")

# Pydantic models for API requests/responses
class ConversationParticipantModel(BaseModel):
    number: str

class ConversationCreate(BaseModel):
    name: Optional[str] = None
    is_group: bool
    group_name: Optional[str] = None
    silent: bool = False
    enabled_apis: List[str] = []
    paths: dict = {}
    participants: List[str] = []
    source_type: SourceType = SourceType.WHATSAPP
    chat_settings_id: Optional[str] = None
    portal_user_id: Optional[str] = None

class ConversationResponse(BaseModel):
    chatid: str
    name: Optional[str] = None
    is_group: bool
    group_name: Optional[str] = None
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    silent: bool
    enabled_apis: List[str] = []
    paths: dict = {}
    participants: List[str] = []
    source_type: SourceType = SourceType.WHATSAPP
    chat_settings_id: Optional[str] = None
    portal_user_id: Optional[str] = None
    
    class Config:
        orm_mode = True

# Chat settings Pydantic models
class ChatSettingsBase(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: str
    model: str = "gpt-4o-mini"

class ChatSettingsCreate(ChatSettingsBase):
    pass

class ChatSettingsUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None

class ChatSettingsResponse(ChatSettingsBase):
    id: str
    
    class Config:
        orm_mode = True

# Tool configuration models
class ApiToolConfig(BaseModel):
    endpoint: str
    method: str  # GET, POST, PUT, DELETE
    params: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    body: Optional[Dict[str, Any]] = None
    body_schema: Optional[Dict[str, Any]] = None  # Schema for the request body
    response_mapping: Optional[Dict[str, str]] = None
    server_url: Optional[str] = None  # Base URL for the API endpoint

class OpenAIToolConfig(BaseModel):
    type: str  # "function" or built-in types like "web_search_preview"
    name: Optional[str] = None  # Required for function type
    description: Optional[str] = None  # Required for function type
    parameters: Optional[Dict[str, Any]] = None  # Required for function type
    user_location: Optional[Dict[str, Any]] = None  # For web_search_preview
    search_context_size: Optional[str] = None  # For web_search_preview

class MessageToolConfig(BaseModel):
    action: str
    parameters: Dict[str, Any]

# Tool models
class ToolBase(BaseModel):
    name: str
    description: Optional[str] = None
    tool_type: ToolType
    api_request_id: Optional[str] = None
    function_schema: Optional[Dict[str, Any]] = None

class ToolCreate(ToolBase):
    pass

class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tool_type: Optional[ToolType] = None
    api_request_id: Optional[str] = None
    function_schema: Optional[Dict[str, Any]] = None

class ToolResponse(ToolBase):
    id: str
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    
    class Config:
        orm_mode = True

# Portal user Pydantic models
class PortalUserCreate(BaseModel):
    id: str  # User ID from the portal system
    username: str
    email: Optional[str] = None

class PortalUserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    
    class Config:
        orm_mode = True

# Add ApiRequest models
class ApiRequestBase(BaseModel):
    api_id: str
    path: str
    method: str
    description: Optional[str] = None
    request_body_schema: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None

class ApiRequestCreate(ApiRequestBase):
    pass

class ApiRequestUpdate(BaseModel):
    path: Optional[str] = None
    method: Optional[str] = None
    description: Optional[str] = None
    request_body_schema: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None

class ApiRequestResponse(ApiRequestBase):
    id: str
    
    class Config:
        orm_mode = True

# Add models for managing tool associations
class AddToolToSettings(BaseModel):
    tool_id: str

class ToolAssignmentResponse(BaseModel):
    chat_settings_id: str
    tools: List[ToolResponse]
    
    class Config:
        orm_mode = True 