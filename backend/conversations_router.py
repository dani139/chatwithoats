from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
import logging
import uuid
from datetime import datetime
from pydantic import BaseModel

from db import get_db
from models import Conversation, ConversationParticipant, ConversationCreate, ConversationResponse, ChatSettings, ChatSettingsCreate, ChatSettingsResponse, Message, MessageType, SourceType
from openai_helper import openai_helper

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(conversation: ConversationCreate, db: Session = Depends(get_db)):
    # Generate a UUID for the chatid
    chat_id = str(uuid.uuid4())
    
    # If chat_settings_id is provided, check that it exists
    chat_settings_id = conversation.chat_settings_id
    if chat_settings_id:
        chat_settings = db.query(ChatSettings).filter(ChatSettings.id == chat_settings_id).first()
        if not chat_settings:
            logger.warning(f"Chat settings with ID {chat_settings_id} not found.")
            raise HTTPException(status_code=404, detail="Specified chat settings not found")
    # If no chat_settings_id is provided, create default chat settings based on source type
    else:
        # Create a new chat setting for this conversation
        settings_id = str(uuid.uuid4())
        system_prompt = ""
        
        # Set appropriate system prompt based on source type
        if conversation.source_type == "WHATSAPP":
            system_prompt = "You are a friendly and laid back whatsapp assistant called Oats (Hebrew: אוטס)."
        elif conversation.source_type == "PORTAL":
            system_prompt = "You are Oats, a helpful AI assistant available through our web portal."
        else:
            system_prompt = "You are Oats, a helpful AI assistant."
        
        # Create new chat settings DB record with appropriate values
        db_chat_settings = ChatSettings(
            id=settings_id,
            name=f"Settings for {conversation.name or 'Untitled Chat'} ({conversation.source_type.lower()})",
            description=f"Auto-generated chat settings for {conversation.source_type.lower()} conversation",
            system_prompt=system_prompt,
            model="gpt-4o-mini",
            enabled_tools=[]
        )
        
        # Add to database
        db.add(db_chat_settings)
        chat_settings_id = settings_id
    
    # Create new conversation DB record
    db_conversation = Conversation(
        chatid=chat_id,
        name=conversation.name,
        is_group=conversation.is_group,
        group_name=conversation.group_name,
        silent=conversation.silent,
        enabled_apis=conversation.enabled_apis,
        paths=conversation.paths,
        source_type=conversation.source_type,
        chat_settings_id=chat_settings_id,
        portal_user_id=conversation.portal_user_id if conversation.source_type == "PORTAL" else None
    )
    
    # Add to database
    db.add(db_conversation)
    
    # Add participants if any
    for participant_number in conversation.participants:
        participant = ConversationParticipant(
            number=participant_number,
            chatid=chat_id
        )
        db.add(participant)
    
    # Commit the transaction
    db.commit()
    
    # Refresh the conversation to get the created_at timestamp
    db.refresh(db_conversation)
    
    logger.info(f"Created {conversation.source_type} conversation with ID: {chat_id}")
    
    # Convert to response model (with participants list)
    return ConversationResponse(
        chatid=db_conversation.chatid,
        name=db_conversation.name,
        is_group=db_conversation.is_group,
        group_name=db_conversation.group_name,
        created_at=db_conversation.created_at,
        updated_at=db_conversation.updated_at,
        silent=db_conversation.silent,
        enabled_apis=db_conversation.enabled_apis,
        paths=db_conversation.paths,
        participants=[p.number for p in db_conversation.participants],
        source_type=db_conversation.source_type,
        chat_settings_id=db_conversation.chat_settings_id,
        portal_user_id=db_conversation.portal_user_id
    )

@router.get("/conversations", response_model=List[ConversationResponse])
async def get_all_conversations(
    chat_settings_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # Start with base query
    query = db.query(Conversation)
    
    # Apply filter if chat_settings_id is provided
    if chat_settings_id:
        query = query.filter(Conversation.chat_settings_id == chat_settings_id)
    
    # Get all conversations matching the filter
    conversations = query.all()
    
    # Convert to response models
    result = []
    for conv in conversations:
        participants = [p.number for p in conv.participants]
        result.append(
            ConversationResponse(
                chatid=conv.chatid,
                name=conv.name,
                is_group=conv.is_group,
                group_name=conv.group_name,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                silent=conv.silent,
                enabled_apis=conv.enabled_apis,
                paths=conv.paths,
                participants=participants,
                source_type=conv.source_type,
                chat_settings_id=conv.chat_settings_id
            )
        )
    
    logger.info(f"Fetched all conversations. Count: {len(result)}")
    return result

@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    # Get the conversation by ID
    conversation = db.query(Conversation).filter(Conversation.chatid == conversation_id).first()
    
    # Check if found
    if not conversation:
        logger.warning(f"Conversation with ID {conversation_id} not found for GET.")
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get participants
    participants = [p.number for p in conversation.participants]
    
    logger.info(f"Fetched conversation with ID: {conversation_id}")
    
    # Return as response model
    return ConversationResponse(
        chatid=conversation.chatid,
        name=conversation.name,
        is_group=conversation.is_group,
        group_name=conversation.group_name,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        silent=conversation.silent,
        enabled_apis=conversation.enabled_apis,
        paths=conversation.paths,
        participants=participants,
        source_type=conversation.source_type,
        chat_settings_id=conversation.chat_settings_id
    )

@router.put("/conversations/{conversation_id}/chat_settings/{settings_id}", response_model=ConversationResponse)
async def update_conversation_chat_settings(
    conversation_id: str, 
    settings_id: str, 
    db: Session = Depends(get_db)
):
    # Get the conversation
    conversation = db.query(Conversation).filter(Conversation.chatid == conversation_id).first()
    
    # Check if conversation found
    if not conversation:
        logger.warning(f"Conversation with ID {conversation_id} not found for chat settings update.")
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Check if the chat settings exists
    chat_settings = db.query(ChatSettings).filter(ChatSettings.id == settings_id).first()
    if not chat_settings:
        logger.warning(f"Chat settings with ID {settings_id} not found for linking.")
        raise HTTPException(status_code=404, detail="Chat settings not found")
    
    # Update the conversation's chat settings
    conversation.chat_settings_id = settings_id
    conversation.updated_at = datetime.utcnow()
    
    # Commit the changes
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    
    # Get participants
    participants = [p.number for p in conversation.participants]
    
    logger.info(f"Updated chat settings for conversation {conversation_id} to {settings_id}")
    
    # Return updated conversation
    return ConversationResponse(
        chatid=conversation.chatid,
        name=conversation.name,
        is_group=conversation.is_group,
        group_name=conversation.group_name,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        silent=conversation.silent,
        enabled_apis=conversation.enabled_apis,
        paths=conversation.paths,
        participants=participants,
        source_type=conversation.source_type,
        chat_settings_id=conversation.chat_settings_id
    )

@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    # Get the conversation
    conversation = db.query(Conversation).filter(Conversation.chatid == conversation_id).first()
    
    # Check if found
    if not conversation:
        logger.warning(f"Conversation with ID {conversation_id} not found for DELETE.")
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # First delete participants due to foreign key constraint
    db.query(ConversationParticipant).filter(ConversationParticipant.chatid == conversation_id).delete()
    
    # Delete the conversation
    db.delete(conversation)
    
    # Commit the transaction
    db.commit()
    
    logger.info(f"Deleted conversation with ID: {conversation_id}")
    return

# You might also want PUT for updates
# @router.put("/conversations/{conversation_id}", response_model=ConversationOutput)
# async def update_conversation(conversation_id: str, conversation: ConversationInput):
#     if conversation_id not in conversations_db:
#         logger.warning(f"Conversation with ID {conversation_id} not found for UPDATE.")
#         raise HTTPException(status_code=404, detail="Conversation not found")
#     conversations_db[conversation_id].update(conversation.model_dump(exclude_unset=True))
#     logger.info(f"Updated conversation with ID: {conversation_id}")
#     return ConversationOutput(id=conversation_id, **conversations_db[conversation_id])

class PortalMessageRequest(BaseModel):
    content: str
    user_id: str
    username: str

class PortalMessageResponse(BaseModel):
    message_id: str
    response_id: str
    response_text: str
    portal_user_id: Optional[str] = None

@router.post("/conversations/{conversation_id}/portal-message", response_model=PortalMessageResponse)
async def add_portal_message(
    conversation_id: str,
    message: PortalMessageRequest,
    db: Session = Depends(get_db)
):
    """
    Add a message to a portal conversation and get a response.
    
    Args:
        conversation_id: The conversation ID
        message: The message object containing content, user_id, and username
        db: Database session
        
    Returns:
        The response from the assistant
    """
    # Get the conversation
    conversation = db.query(Conversation).filter(Conversation.chatid == conversation_id).first()
    if not conversation:
        logger.warning(f"Conversation with ID {conversation_id} not found.")
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Verify this is a portal conversation
    if conversation.source_type != SourceType.PORTAL:
        logger.warning(f"Conversation {conversation_id} is not a portal conversation.")
        raise HTTPException(status_code=400, detail="This endpoint only supports portal conversations")
    
    # Create a new user message
    message_id = str(uuid.uuid4())
    user_message = Message(
        id=message_id,
        chatid=conversation_id,
        sender=message.user_id,
        sender_name=message.username,
        type=MessageType.TEXT,
        content=message.content,
        role="user"
    )
    
    # Add to database
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    
    logger.info(f"Added portal message with ID: {message_id} to conversation: {conversation_id}")
    
    # Get response from OpenAI
    response_text = await openai_helper.get_openai_response(conversation, user_message, db)
    
    # Create assistant message
    assistant_message_id = str(uuid.uuid4())
    assistant_message = Message(
        id=assistant_message_id,
        chatid=conversation_id,
        sender=None,
        sender_name="Oats",
        type=MessageType.TEXT,
        content=response_text,
        role="assistant"
    )
    
    # Add to database
    db.add(assistant_message)
    db.commit()
    
    logger.info(f"Added assistant response with ID: {assistant_message_id} to conversation: {conversation_id}")
    
    # Return response
    return PortalMessageResponse(
        message_id=message_id,
        response_id=assistant_message_id,
        response_text=response_text,
        portal_user_id=conversation.portal_user_id
    )

class MessageResponse(BaseModel):
    id: str
    sender: Optional[str] = None
    sender_name: Optional[str] = None
    content: Optional[str] = None
    type: str
    role: Optional[str] = None
    created_at: datetime
    is_from_user: bool

@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Get messages for a conversation.
    
    Args:
        conversation_id: The conversation ID
        limit: Maximum number of messages to return (default: 50)
        offset: Number of messages to skip (default: 0)
        db: Database session
        
    Returns:
        List of messages
    """
    # Get the conversation
    conversation = db.query(Conversation).filter(Conversation.chatid == conversation_id).first()
    if not conversation:
        logger.warning(f"Conversation with ID {conversation_id} not found.")
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get messages for the conversation
    messages = db.query(Message).filter(
        Message.chatid == conversation_id
    ).order_by(Message.created_at.desc()).offset(offset).limit(limit).all()
    
    # Convert to response model
    result = []
    for msg in messages:
        result.append(
            MessageResponse(
                id=msg.id,
                sender=msg.sender,
                sender_name=msg.sender_name,
                content=msg.content,
                type=msg.type,
                role=msg.role,
                created_at=msg.created_at,
                is_from_user=bool(msg.sender)  # True if sender is not None
            )
        )
    
    # Reverse to get chronological order
    result.reverse()
    
    logger.info(f"Fetched {len(result)} messages for conversation {conversation_id}")
    return result