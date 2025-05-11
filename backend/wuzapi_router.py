from fastapi import APIRouter, Request, HTTPException, Form, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Any, Dict, Optional, List, Set, Union, Literal
import logging
import json
import os
import httpx
import base64
import re
from sqlalchemy.orm import Session
import uuid

from db import get_db
from models import Conversation, ConversationParticipant, ConversationCreate, SourceType, Message, MessageType, ChatSettings
from chat_settings_router import get_or_create_web_search_tool
from openai_helper import get_openai_response

# Configure basic logging
logger = logging.getLogger(__name__)

router = APIRouter()

# WuzAPI details (Dev Docker )
WUZAPI_BASE_URL = "http://wuzapi:8080" 
WEBHOOK_PATH = "/wuzapi_webhook" 

# Bot's WhatsApp number - messages from this number should be ignored
BOT_WHATSAPP_NUMBER = "972543857242"

# Track known chats to avoid duplicate processing
known_chats: Set[str] = set()
# Cache for group names to avoid repeated API calls
group_info_cache: Dict[str, Dict[str, Any]] = {}

# WuzAPI handler class
class WuzapiHandler:
    def __init__(self):
        self.base_url = WUZAPI_BASE_URL
        # Get token from environment variable or use default
        token = os.environ.get("WUZAPI_TOKEN", "iamhipster")
        self.headers = {
            "Content-Type": "application/json",
            "token": token
        }
        logger.info(f"Initialized WuzAPI handler with base URL: {self.base_url}")
        
    async def send_message(self, chat_id: str, message: str, context_info: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Send a text message via WuzAPI
        
        Args:
            chat_id: The WhatsApp chat ID to send the message to
            message: The message content to send
            context_info: Optional context info for replying to messages
            
        Returns:
            Message ID if successful, None otherwise
        """
        try:
            url = f"{self.base_url}/chat/send/text"
            
            # Sanitize message (convert markdown-style formatting to WhatsApp format)
            message = self.sanitize_message(message)
            
            # Create request data
            data = {"Phone": chat_id, "Body": message}
            
            # Add context info if provided (for reply functionality)
            if context_info:
                if "stanza_id" in context_info and "participant" in context_info:
                    data["ContextInfo"] = {
                        "StanzaId": context_info["stanza_id"],
                        "Participant": context_info["participant"]
                    }
            
            # Make the request
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self.headers, json=data)
                response.raise_for_status()
                
                # Extract message ID from response
                response_data = response.json()
                if response_data.get("success"):
                    msg_id = response_data.get("data", {}).get("Id")
                    logger.info(f"Message sent successfully to {chat_id}, ID: {msg_id}")
                    return msg_id
                else:
                    logger.error(f"Failed to send message: {response_data}")
                    return None
                    
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error sending message to {chat_id}: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error sending message to {chat_id}: {e}")
            return None
    
    async def send_file(
        self, 
        chat_id: str, 
        file_path: str, 
        caption: str = "", 
        display_name: str = "", 
        context_info: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Send a file via WuzAPI
        
        Args:
            chat_id: The WhatsApp chat ID to send the file to
            file_path: Path to the file to send
            caption: Optional caption for images
            display_name: Optional display name for documents
            context_info: Optional context info for replying to messages
            
        Returns:
            Message ID if successful, None otherwise
        """
        try:
            # Determine file type
            image_extensions = ['jpg', 'jpeg', 'png', 'bmp', 'webp', 'gif']
            audio_extensions = ['mp3', 'wav', 'ogg', 'webm', 'flac', 'aac']
            document_extensions = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'zip', 'rar']
            
            # Get file extension
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None
                
            extension = file_path.split('.')[-1].lower()
            
            # Use filename as display name if not provided
            if not display_name:
                display_name = os.path.basename(file_path)
            
            # Encode file as base64
            with open(file_path, "rb") as file_handler:
                encoded_file = base64.b64encode(file_handler.read()).decode('utf-8')
            
            # Determine URL and data based on file type
            url = f"{self.base_url}/chat/send/"
            data = {"Phone": chat_id}
            
            if extension in image_extensions:
                url += "image"
                data["Image"] = f"data:image/{extension};base64,{encoded_file}"
                if caption:
                    data["Caption"] = caption
            elif extension in audio_extensions:
                url += "audio"
                data["Audio"] = f"data:audio/{extension};base64,{encoded_file}"
            else:
                # Default to document
                url += "document"
                data["Document"] = f"data:application/octet-stream;base64,{encoded_file}"
                data["FileName"] = display_name
            
            # Make the request
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self.headers, json=data)
                response.raise_for_status()
                
                # Extract message ID from response
                response_data = response.json()
                if response_data.get("success"):
                    msg_id = response_data.get("data", {}).get("Id")
                    logger.info(f"File sent successfully to {chat_id}, ID: {msg_id}")
                    return msg_id
                else:
                    logger.error(f"Failed to send file: {response_data}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error sending file to {chat_id}: {e}")
            return None
    
    async def send_reaction(self, chat_id: str, message_id: str, reaction: str) -> bool:
        """
        Send a reaction to a message via WuzAPI
        
        Args:
            chat_id: The WhatsApp chat ID
            message_id: The ID of the message to react to
            reaction: The reaction emoji
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/chat/react"
            data = {
                "Phone": chat_id,
                "Id": message_id,
                "Body": reaction
            }
            
            # Make the request
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self.headers, json=data)
                response.raise_for_status()
                
                # Check success
                response_data = response.json()
                if response_data.get("success"):
                    logger.info(f"Reaction sent successfully to message {message_id}")
                    return True
                else:
                    logger.error(f"Failed to send reaction: {response_data}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending reaction to message {message_id}: {e}")
            return False
    
    async def set_chat_presence(
        self, 
        chat_id: str, 
        state: Literal["composing", "paused", "recording"] = "composing", 
        media: bool = False
    ) -> bool:
        """
        Set the chat presence (typing indicator) via WuzAPI
        
        Args:
            chat_id: The WhatsApp chat ID
            state: The presence state (composing, paused, recording)
            media: Whether to show media presence
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/chat/presence"
            data = {
                "Phone": chat_id,
                "State": state
            }
            
            if media:
                data["Media"] = "audio"
            
            # Make the request
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self.headers, json=data)
                response.raise_for_status()
                
                # Check success
                response_data = response.json()
                if response_data.get("success"):
                    logger.info(f"Chat presence set successfully for {chat_id}")
                    return True
                else:
                    logger.error(f"Failed to set chat presence: {response_data}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error setting chat presence for {chat_id}: {e}")
            return False
    
    def sanitize_message(self, text: str) -> str:
        """
        Sanitize message text for WhatsApp formatting
        
        Args:
            text: The text to sanitize
            
        Returns:
            Sanitized text
        """
        # First handle combined formats (bold-italic)
        text = re.sub(r"\*\*_(.*?)_\*\*", r"*_\1_*", text)  # Bold-italic: **_text_** -> *_text_*
        text = re.sub(r"_\*\*(.*?)\*\*_", r"*_\1_*", text)  # Italic-bold: _**text**_ -> *_text_*
        
        # Then handle single formats
        text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)  # Bold: **text** -> *text*
        text = re.sub(r"#{1,3} (.*?)\n", r"*\1*\n", text)  # Headers -> Bold
        text = re.sub(r"~~(.*?)~~", r"~\1~", text)  # Strikethrough: ~~text~~ -> ~text~
        
        # Handle bullet points
        lines = text.split('\n')
        processed_lines = []
        for line in lines:
            # Skip empty lines or lines with just whitespace
            if not line.strip():
                processed_lines.append('')
                continue
            # Handle bullet points
            if line.strip().startswith('-'):
                line = re.sub(r'^- (.*?)$', r'• \1', line.strip())
            processed_lines.append(line)
        
        # Join lines and return
        return '\n'.join(processed_lines)

# Initialize WuzAPI handler
wuzapi_handler = WuzapiHandler()

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
            # Create a new chat settings for this conversation
            settings_id = str(uuid.uuid4())
            
            # Get or create web search tool
            web_search_tool = await get_or_create_web_search_tool(db)
            
            # Create default chat settings with web search tool
            db_chat_settings = ChatSettings(
                id=settings_id,
                name=f"Settings for {push_name if not is_group else group_name or 'Untitled Chat'}",
                description="Auto-generated chat settings",
                system_prompt="You are a friendly and laid back whatsapp assistant called Oats (Hebrew: אוטס).",
                model="gpt-4o-mini",
                enabled_tools=[web_search_tool.id]
            )
            
            # Add to database
            db.add(db_chat_settings)
            
            # Associate web search tool with chat settings
            db_chat_settings.tools = [web_search_tool]
            
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
                source_type=SourceType.WHATSAPP,
                chat_settings_id=settings_id  # Link to the chat settings
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
                source_type=conversation_data.source_type,
                chat_settings_id=settings_id  # Link to the chat settings
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
        # Get the conversation
        conversation = db.query(Conversation).filter(Conversation.chatid == chat_id).first()
        if not conversation:
            logger.warning(f"No conversation found for chat ID: {chat_id}. Cannot process message.")
            return "Error: Conversation not found"
            
        # Generate a UUID for the message ID
        message_id = str(uuid.uuid4())
        
        # Create a new user message
        user_message = Message(
            id=message_id,
            chatid=chat_id,
            sender=sender_jid,
            sender_name=sender_name,
            type=message_type,
            content=message_text,
            role="user"  # Assuming all incoming messages are from users
        )
        
        # Add to database
        db.add(user_message)
        db.commit()
        db.refresh(user_message)
        
        logger.info(f"Stored new message with ID: {message_id} for chat: {chat_id}")
        
        # Set chat presence to "composing" to show typing indicator
        await wuzapi_handler.set_chat_presence(chat_id, "composing")
        
        # Get response from OpenAI
        response_text = await get_openai_response(conversation, user_message, db)
        
        # Store the assistant's response
        assistant_message_id = str(uuid.uuid4())
        assistant_message = Message(
            id=assistant_message_id,
            chatid=chat_id,
            sender=None,  # No sender for assistant messages
            sender_name="Oats",
            type=MessageType.TEXT,
            content=response_text,
            role="assistant"
        )
        
        # Add to database
        db.add(assistant_message)
        db.commit()
        
        logger.info(f"Stored assistant response with ID: {assistant_message_id} for chat: {chat_id}")
        
        # Send the response via WuzAPI
        whatsapp_msg_id = await wuzapi_handler.send_message(chat_id, response_text)
        if whatsapp_msg_id:
            logger.info(f"Sent response to WhatsApp with ID: {whatsapp_msg_id}")
        else:
            logger.error(f"Failed to send response to WhatsApp")
        
        # Get recent messages to check for any tool results that should be sent to the user
        recent_msgs = db.query(Message).filter(
            Message.chatid == chat_id,
            Message.type == MessageType.TOOL_RESULT,
            Message.created_at > user_message.created_at
        ).all()
        
        for tool_result_msg in recent_msgs:
            # Send tool results to the user as well
            result_text = f"Tool result from {tool_result_msg.function_name}:\n\n{tool_result_msg.function_result}"
            await wuzapi_handler.send_message(chat_id, result_text)
            logger.info(f"Sent tool result for {tool_result_msg.function_name} to WhatsApp")
        
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
        
        # Skip processing if the message is from the bot itself
        if sender_jid and BOT_WHATSAPP_NUMBER in sender_jid:
            logger.info(f"Skipping message from bot itself: {sender_jid}")
            return {"status": "success", "message": "Skipped bot's own message"}

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
        # Skip processing if the chat presence is from the bot itself
        sender_jid = event_data.get("Sender")
        if sender_jid and BOT_WHATSAPP_NUMBER in sender_jid:
            logger.info(f"Skipping chat presence from bot itself: {sender_jid}")
            return {"status": "success", "message": "Skipped bot's own chat presence"}
            
        is_group_event = isinstance(event_data.get("Chat"), str) and "@g.us" in event_data.get("Chat")
        if is_group_event:
             logger.info(f"Client \'{client_name}\': Chat presence in Group Chat ID [{chat_id}]: {state}")
        else:
             logger.info(f"Client \'{client_name}\': Chat presence from User/Chat ID [{chat_id}]: {state}")
             
    elif event_type == "ReadReceipt":
        chat_id = event_data.get("Chat")
        # Skip processing if the read receipt is from the bot itself
        sender_jid = event_data.get("Sender")
        if sender_jid and BOT_WHATSAPP_NUMBER in sender_jid:
            logger.info(f"Skipping read receipt from bot itself: {sender_jid}")
            return {"status": "success", "message": "Skipped bot's own read receipt"}
            
        logger.info(f"Client \'{client_name}\': Read receipt for Chat ID [{chat_id}]. Data: {event_data}")
        
    elif event_type == "HistorySync":
        logger.info(f"Client \'{client_name}\': History sync event. Data: {event_data}")
    else:
        chat_id = event_data.get("Chat")
        # Skip processing if the event is from the bot itself
        sender_jid = event_data.get("Sender")
        if sender_jid and BOT_WHATSAPP_NUMBER in sender_jid:
            logger.info(f"Skipping event from bot itself: {sender_jid}")
            return {"status": "success", "message": "Skipped bot's own event"}
            
        logger.info(f"Client \'{client_name}\': Received unhandled event type \'{event_type}\' for chat {chat_id if chat_id else 'N/A'}. Data: {event_data}")

    return {"status": "success", "message": f"Webhook for event \'{event_type}\' received for client \'{client_name}\'"} 

@router.post("/test-openai-response", response_model=MessageResponse)
async def test_openai_response(message: MessageRequest, db: Session = Depends(get_db)):
    """
    Test endpoint for OpenAI integration.
    """
    try:
        # Get conversation
        conversation = db.query(Conversation).filter(Conversation.chatid == message.chat_id).first()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
            
        # Create temporary user message (not saved to DB)
        user_message = Message(
            id=str(uuid.uuid4()),
            chatid=message.chat_id,
            sender=message.sender_jid,
            sender_name=message.sender_name,
            type=message.message_type,
            content=message.message_text,
            role="user"
        )
        
        # Initialize the WuzAPI handler and test setting chat presence
        logger.info(f"Initializing WuzAPI handler")
        handler = WuzapiHandler()
        logger.info(f"Setting chat presence for {message.chat_id}")
        await handler.set_chat_presence(message.chat_id, "composing")
        
        # Get response from OpenAI
        response_text = await get_openai_response(conversation, user_message, db)
        
        # Test sending the response via WuzAPI
        logger.info(f"Sending response to WhatsApp: {message.chat_id}")
        whatsapp_msg_id = await handler.send_message(message.chat_id, response_text)
        if whatsapp_msg_id:
            logger.info(f"Successfully sent message to WhatsApp with ID: {whatsapp_msg_id}")
        else:
            logger.error(f"Failed to send message to WhatsApp")
        
        return MessageResponse(response_text=response_text)
        
    except Exception as e:
        logger.error(f"Error testing OpenAI response: {e}")
        raise HTTPException(status_code=500, detail=f"Error testing OpenAI response: {str(e)}") 