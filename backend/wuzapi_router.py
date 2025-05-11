from fastapi import APIRouter, Request, HTTPException, Form, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Any, Dict, Optional, List, Set
import logging
import json
import os
import httpx
from sqlalchemy.orm import Session
import uuid

from db import get_db
from models import Conversation, ConversationParticipant, ConversationCreate, SourceType, Message, MessageType

# Configure basic logging
logger = logging.getLogger(__name__)

router = APIRouter()

# WuzAPI details (Dev Docker )
WUZAPI_BASE_URL = "http://wuzapi:8080" 
WEBHOOK_PATH = "/wuzapi_webhook" 

# Track known chats to avoid duplicate processing
known_chats: Set[str] = set()
# Cache for group names to avoid repeated API calls
group_info_cache: Dict[str, Dict[str, Any]] = {}

async def get_group_info(group_jid: str, user_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetches group information (name, participants) from WuzAPI.
    Returns a dictionary with {\'name\': group_name, \'participants\': [...]}
    or None if fetching fails.
    """
    url = f"{WUZAPI_BASE_URL}/group/info"
    headers = {
        "Token": user_token
    }
    params = {"groupJID": group_jid}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            response_data = response.json()
            if response_data.get("success") and "data" in response_data:
                group_details = response_data["data"]
                group_name = group_details.get("Name")
                participants = group_details.get("Participants", [])
                if group_name:
                    logger.info(f"Successfully fetched info for group {group_jid}: Name='{group_name}', Participants count: {len(participants)}")
                    return {"name": group_name, "participants": participants}
                else:
                    logger.warning(f"Fetched info for group {group_jid}, but no 'Name' field found.")
                    return None
            else:
                logger.warning(f"Failed to get group info for {group_jid}. WuzAPI success: {response_data.get('success')}, Data: {response_data.get('data')}")
                return None
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching group info for {group_jid}: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error fetching group info for {group_jid}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error fetching group info for {group_jid}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching group info for {group_jid}: {e}")
        return None

async def check_conversation_exists(chat_id: str, db: Session) -> Optional[Conversation]:
    """
    Check if a conversation with the given chat_id exists in the database.
    Returns the conversation object if found, None otherwise.
    """
    try:
        # Query the database for the conversation with the given chat_id
        conversation = db.query(Conversation).filter(Conversation.chatid == chat_id).first()
        if conversation:
            logger.info(f"Found existing conversation with ID: {chat_id}")
            # Add to known chats to avoid duplicate processing
            known_chats.add(chat_id)
            return conversation
        logger.info(f"No existing conversation found with ID: {chat_id}")
        return None
    except Exception as e:
        logger.error(f"Error checking for existing conversation {chat_id}: {e}")
        return None

async def process_conversation(chat_id: str, is_group: bool, sender_jid: str, push_name: str, client_name: str, db: Session, group_name: Optional[str] = None, participants: Optional[List[str]] = None) -> Optional[Conversation]:
    """
    Process a conversation - check if it exists, create if it doesn't.
    Returns the conversation object.
    """
    try:
        # First check if conversation exists
        conversation = await check_conversation_exists(chat_id, db)
        
        if not conversation:
            # Create new conversation if it doesn't exist
            # Generate a UUID for the chatid - using the original chat_id from WhatsApp instead
            # Generate conversation data
            conversation_data = ConversationCreate(
                name=push_name if not is_group else group_name,
                is_group=is_group,
                group_name=group_name if is_group else None,
                silent=False,  # Default to not silent
                enabled_apis=[],  # Default to no APIs enabled
                paths={},  # Default to empty paths
                participants=[sender_jid] if not is_group and sender_jid else (participants or []),
                source_type=SourceType.WHATSAPP
            )
            
            # Create conversation object
            db_conversation = Conversation(
                chatid=chat_id,
                name=conversation_data.name,
                is_group=conversation_data.is_group,
                group_name=conversation_data.group_name,
                silent=conversation_data.silent,
                enabled_apis=conversation_data.enabled_apis,
                paths=conversation_data.paths,
                source_type=conversation_data.source_type
            )
            
            # Add to database
            db.add(db_conversation)
            
            # Add participants if any
            for participant_number in conversation_data.participants:
                participant = ConversationParticipant(
                    number=participant_number,
                    chatid=chat_id
                )
                db.add(participant)
            
            # Commit the transaction
            db.commit()
            
            # Refresh the conversation to get any database-generated values
            db.refresh(db_conversation)
            
            logger.info(f"Created new conversation with ID: {chat_id}")
            
            # Add to known chats
            known_chats.add(chat_id)
            
            return db_conversation
        
        return conversation
                
    except Exception as e:
        logger.error(f"Error processing conversation for chat {chat_id}: {e}")
        return None

async def handle_new_message(chat_id: str, sender_jid: str, sender_name: str, message_text: str, message_type: str, db: Session) -> str:
    """
    Handle a new message in a conversation.
    Returns a response text.
    """
    try:
        # Generate a UUID for the message ID
        message_id = str(uuid.uuid4())
        
        # Create a new message
        db_message = Message(
            id=message_id,
            chatid=chat_id,
            sender=sender_jid,
            sender_name=sender_name,
            type=message_type,
            content=message_text,
            role="user"  # Assuming all incoming messages are from users
        )
        
        # Add to database
        db.add(db_message)
        
        # Commit the transaction
        db.commit()
        
        logger.info(f"Stored new message with ID: {message_id} for chat: {chat_id}")
        
        # Generate and return a text response
        # In a real system, this would call an AI or other service to generate a response
        response_text = f"Received: {message_text}"
        
        return response_text
    except Exception as e:
        logger.error(f"Error handling new message for chat {chat_id}: {e}")
        return f"Error processing message: {str(e)}"

# Define Pydantic models for the incoming payload
class WuzapiEventData(BaseModel):
    event: Dict[str, Any]
    type: str

class WuzapiWebhookPayload(BaseModel):
    jsonData: str # This will be a JSON string
    token: str

# Define models for message handling
class MessageRequest(BaseModel):
    chat_id: str
    sender_jid: str
    sender_name: str
    message_text: str
    message_type: str = MessageType.TEXT

class MessageResponse(BaseModel):
    response_text: str

@router.post("/messages", response_model=MessageResponse)
async def process_message(message: MessageRequest, db: Session = Depends(get_db)):
    """
    Process a new message and return a response.
    """
    response_text = await handle_new_message(
        message.chat_id,
        message.sender_jid,
        message.sender_name,
        message.message_text,
        message.message_type,
        db
    )
    
    return MessageResponse(response_text=response_text)

@router.post(WEBHOOK_PATH)
async def wuzapi_webhook_handler(
    request: Request, 
    background_tasks: BackgroundTasks,
    jsonData: str = Form(...), 
    token: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handles incoming webhook events from WuzAPI, expecting application/x-www-form-urlencoded.
    """
    client_host = request.client.host if request.client else "unknown"

    logger.info(f"Request Headers: {request.headers}")
    logger.info(f"Form Data: jsonData='{jsonData}', token='{token}'")
    
    inner_payload_dict: Dict[str, Any]
    event_type: Optional[str] = None
    event_data: Dict[str, Any] = {}
    client_name: Optional[str] = token

    try:
        inner_payload_dict = json.loads(jsonData)
        event_type = inner_payload_dict.get("type") 
        event_data = inner_payload_dict.get("event", {})

        logger.info(f"Client Token: {client_name}")
        logger.info(f"Parsed Event Type: {event_type}")
        logger.info(f"Parsed Event Data: {event_data}")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse jsonData string. Error: {e}. jsonData content: {jsonData[:500]}")
        raise HTTPException(status_code=400, detail=f"Invalid jsonData format. Error: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during parsing: {e}")
        logger.error(f"jsonData during unexpected error: {jsonData[:500]}")
        raise HTTPException(status_code=500, detail=f"Internal server error during parsing: {e}")

    if event_type == "Message":
        info_data = event_data.get("Info", {})
        message_content_data = event_data.get("Message", {})
        
        chat_id = info_data.get("Chat")
        sender_jid = info_data.get("Sender") 
        is_group_message = info_data.get("IsGroup", False)
        push_name = info_data.get("PushName", "Unknown User")

        text = None
        reaction_text = None
        group_info = None
        group_display_name = chat_id

        # Process conversation - check if exists, create if not
        if chat_id:
            if is_group_message and chat_id not in known_chats:
                # Only fetch group info when creating a new conversation
                group_info = await get_group_info(chat_id, client_name)
                if group_info:
                    group_display_name = group_info.get("name", "Unknown Group")
                    participants = [p.get("JID") for p in group_info.get("participants", [])]
                    # Cache the group info for future use
                    group_info_cache[chat_id] = group_info
                    
                    # Process conversation in the background
                    background_tasks.add_task(
                        process_conversation,
                        chat_id=chat_id,
                        is_group=True,
                        sender_jid=sender_jid,
                        push_name=push_name,
                        client_name=client_name,
                        db=db,
                        group_name=group_display_name,
                        participants=participants
                    )
            else:
                # Process conversation in the background
                background_tasks.add_task(
                    process_conversation,
                    chat_id=chat_id,
                    is_group=False,
                    sender_jid=sender_jid,
                    push_name=push_name,
                    client_name=client_name,
                    db=db
                )

        if info_data.get("Type") == "reaction":
            reaction_message_data = message_content_data.get("reactionMessage", {})
            reaction_text = reaction_message_data.get("text")
            reacted_to_id = reaction_message_data.get("key", {}).get("ID")
            if is_group_message:
                # Use cached group info if available, otherwise use chat_id as display name
                if chat_id in group_info_cache:
                    group_display_name = group_info_cache[chat_id].get("name", chat_id)
                logger.info(f"Client \'{client_name}\': Reaction in Group \'{group_display_name}\' [{chat_id}] by sender \'{push_name}\' ({sender_jid}). Reaction: \'{reaction_text}\' to message {reacted_to_id}")
            else:
                logger.info(f"Client \'{client_name}\': Reaction from {push_name} (Chat ID: [{chat_id}]). Reaction: \'{reaction_text}\' to message {reacted_to_id}")
        else:
            text = message_content_data.get("conversation")
            if not text:
                extended_text_message = message_content_data.get("extendedTextMessage", {})
                text = extended_text_message.get("text")
            
            if text:
                # Handle the new message and get a response
                background_tasks.add_task(
                    handle_new_message,
                    chat_id=chat_id,
                    sender_jid=sender_jid,
                    sender_name=push_name,
                    message_text=text,
                    message_type=MessageType.TEXT,
                    db=db
                )
            
            if is_group_message:
                participant_count = "N/A"
                
                # Use cached group info if available, otherwise use chat_id as display name
                if chat_id in group_info_cache:
                    group_display_name = group_info_cache[chat_id].get("name", chat_id)
                    participant_count = len(group_info_cache[chat_id].get("participants", []))
                
                logger.info(f"Client \'{client_name}\': Message in Group \'{group_display_name}\' [{chat_id}] (Participants: {participant_count}) by sender \'{push_name}\' ({sender_jid}): {text}")
            else:
                logger.info(f"Client \'{client_name}\': Message from {push_name} (Chat ID: [{chat_id}]): {text}")

    elif event_type == "ChatPresence":
        state = event_data.get("State")
        chat_id = event_data.get("Chat")
        is_group_event = isinstance(event_data.get("Chat"), str) and "@g.us" in event_data.get("Chat")
        if is_group_event:
             logger.info(f"Client \'{client_name}\': Chat presence in Group Chat ID [{chat_id}]: {state}")
        else:
             logger.info(f"Client \'{client_name}\': Chat presence from User/Chat ID [{chat_id}]: {state}")
    elif event_type == "ReadReceipt":
        chat_id = event_data.get("Chat")
        logger.info(f"Client \'{client_name}\': Read receipt for Chat ID [{chat_id}]. Data: {event_data}")
    elif event_type == "HistorySync":
        logger.info(f"Client \'{client_name}\': History sync event. Data: {event_data}")
    else:
        chat_id = event_data.get("Chat")
        logger.info(f"Client \'{client_name}\': Received unhandled event type \'{event_type}\' for chat {chat_id if chat_id else 'N/A'}. Data: {event_data}")

    return {"status": "success", "message": f"Webhook for event \'{event_type}\' received for client \'{client_name}\'"} 