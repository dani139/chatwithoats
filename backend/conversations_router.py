from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
import logging
import uuid
from datetime import datetime

from db import get_db
from models import Conversation, ConversationParticipant, ConversationCreate, ConversationResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(conversation: ConversationCreate, db: Session = Depends(get_db)):
    # Generate a UUID for the chatid
    chat_id = str(uuid.uuid4())
    
    # Create new conversation DB record
    db_conversation = Conversation(
        chatid=chat_id,
        name=conversation.name,
        is_group=conversation.is_group,
        group_name=conversation.group_name,
        silent=conversation.silent,
        enabled_apis=conversation.enabled_apis,
        paths=conversation.paths,
        source_type=conversation.source_type
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
    
    logger.info(f"Created conversation with ID: {chat_id}")
    
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
        source_type=db_conversation.source_type
    )

@router.get("/conversations", response_model=List[ConversationResponse])
async def get_all_conversations(db: Session = Depends(get_db)):
    # Get all conversations
    conversations = db.query(Conversation).all()
    
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
                source_type=conv.source_type
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
        source_type=conversation.source_type
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