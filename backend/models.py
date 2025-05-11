from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, JSON, Integer, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel
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

# SQLAlchemy Models
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
    chat_settings_id = Column(String, nullable=True)
    portal_user_id = Column(String, nullable=True)
    source_type = Column(String, nullable=False, default=SourceType.WHATSAPP)
    
    # Relationships
    participants = relationship("ConversationParticipant", back_populates="conversation")
    messages = relationship("Message", back_populates="conversation")

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
    
    class Config:
        orm_mode = True 