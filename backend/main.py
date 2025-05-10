from fastapi import FastAPI, Request, HTTPException, Form
from pydantic import BaseModel 
from typing import Any, Dict, Optional
import logging
import json
import os
import httpx # Import httpx

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# The webhook path now matches the one we\'ll configure for WuzAPI
WEBHOOK_PATH = "/backend/wuzapi_webhook"
# A simple token for a bit of security, WuzAPI doesn\'t support this directly
# in its webhook call, but good practice if you were to extend.
# For now, it\'s unused in validation.
EXPECTED_WEBHOOK_TOKEN = os.getenv("BACKEND_WEBHOOK_TOKEN", "a_secure_token_if_needed")

# WuzAPI details (internal Docker network)
WUZAPI_BASE_URL = "http://wuzapi:8080"

async def get_group_info(group_jid: str, user_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetches group information (name, participants) from WuzAPI.
    Returns a dictionary with {'name': group_name, 'participants': [...]}
    or None if fetching fails.
    """
    url = f"{WUZAPI_BASE_URL}/group/info"
    headers = {
        "Token": user_token
        # "Content-Type": "application/json" # No longer sending JSON body
    }
    # Parameters should be passed in the URL for a GET request
    params = {"groupJID": group_jid}
    
    try:
        async with httpx.AsyncClient() as client:
            # WuzAPI GET /group/info expects 'groupJID' as a query parameter
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            
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
                    return None # Or return participants if only name is missing but participants are there
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

# Define Pydantic models for the incoming payload
class WuzapiEventData(BaseModel): # Model for the actual event structure inside jsonData
    event: Dict[str, Any] # Or more specific models for different event types if needed
    type: str
    # You might want to add more specific fields here based on WuzAPI docs
    # For example, for a message:
    # class MessageInfo(BaseModel):
    #     Chat: str
    #     Sender: str
    #     # ... other fields
    # class MessageEvent(BaseModel):
    #     Info: MessageInfo
    #     Message: Dict[str, Any] # or a more specific model
    #
    # event: Optional[MessageEvent] = None # Making it optional or using Union for different event types

class WuzapiWebhookPayload(BaseModel):
    jsonData: str # This will be a JSON string
    token: str

@app.post(WEBHOOK_PATH)
# Change signature to accept Form data
async def wuzapi_webhook_handler(request: Request, jsonData: str = Form(...), token: str = Form(...)):
    """
    Handles incoming webhook events from WuzAPI, expecting application/x-www-form-urlencoded.
    """
    client_host = request.client.host if request.client else "unknown"

    # Log headers to see Content-Type etc.
    logger.info(f"Request Headers: {request.headers}")

    # With Form(...), jsonData and token are now directly available and URL-decoded
    logger.info(f"Form Data: jsonData='{jsonData}', token='{token}'")
    
    inner_payload_dict: Dict[str, Any]
    event_type: Optional[str] = None
    event_data: Dict[str, Any] = {}
    client_name: Optional[str] = token # Use token directly from Form

    try:
        # jsonData is already a string from the form data, now parse it as JSON
        inner_payload_dict = json.loads(jsonData)
        
        event_type = inner_payload_dict.get("type") 
        event_data = inner_payload_dict.get("event", {})

        logger.info(f"Client Token: {client_name}")
        logger.info(f"Parsed Event Type: {event_type}")
        logger.info(f"Parsed Event Data: {event_data}")

    except json.JSONDecodeError as e:
        # Log the problematic jsonData string itself
        logger.error(f"Failed to parse jsonData string. Error: {e}. jsonData content: {jsonData[:500]}")
        raise HTTPException(status_code=400, detail=f"Invalid jsonData format. Error: {e}")
    except HTTPException: # Re-raise HTTPExceptions directly
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during parsing: {e}")
        # Log the problematic jsonData string
        logger.error(f"jsonData during unexpected error: {jsonData[:500]}")
        raise HTTPException(status_code=500, detail=f"Internal server error during parsing: {e}")

    # Event processing logic (largely the same as before)
    if event_type == "Message":
        info_data = event_data.get("Info", {})
        message_content_data = event_data.get("Message", {})
        
        chat_id = info_data.get("Chat")
        sender_jid = info_data.get("Sender") 
        is_group_message = info_data.get("IsGroup", False)
        push_name = info_data.get("PushName", "Unknown User")

        text = None
        reaction_text = None

        if info_data.get("Type") == "reaction":
            reaction_message_data = message_content_data.get("reactionMessage", {})
            reaction_text = reaction_message_data.get("text")
            reacted_to_id = reaction_message_data.get("key", {}).get("ID")
            if is_group_message:
                group_display_name = chat_id # Default to JID
                group_info = await get_group_info(chat_id, client_name)
                if group_info and group_info.get("name"):
                    group_display_name = group_info["name"]
                logger.info(f"Client \'{client_name}\': Reaction in Group \'{group_display_name}\' [{chat_id}] by sender \'{push_name}\' ({sender_jid}). Reaction: \'{reaction_text}\' to message {reacted_to_id}")
            else:
                logger.info(f"Client \'{client_name}\': Reaction from {push_name} (Chat ID: [{chat_id}]). Reaction: \'{reaction_text}\' to message {reacted_to_id}")
        else:
            text = message_content_data.get("conversation")
            if not text:
                extended_text_message = message_content_data.get("extendedTextMessage", {})
                text = extended_text_message.get("text")
            
            if is_group_message:
                group_display_name = chat_id # Default to JID
                participant_count = "N/A"
                group_info = await get_group_info(chat_id, client_name)
                if group_info:
                    if group_info.get("name"):
                        group_display_name = group_info["name"]
                    if group_info.get("participants") is not None:
                        participant_count = len(group_info["participants"])
                
                logger.info(f"Client \'{client_name}\': Message in Group \'{group_display_name}\' [{chat_id}] (Participants: {participant_count}) by sender \'{push_name}\' ({sender_jid}): {text}")
            else:
                logger.info(f"Client \'{client_name}\': Message from {push_name} (Chat ID: [{chat_id}]): {text}")

    elif event_type == "ChatPresence":
        state = event_data.get("State")
        chat_id = event_data.get("Chat") # JID of the user/chat whose presence changed
        # Log if it might be a group presence if structure allows, otherwise assume user
        is_group_event = isinstance(event_data.get("Chat"), str) and "@g.us" in event_data.get("Chat")
        if is_group_event: # This is a guess, WuzAPI might not send group presence this way
             logger.info(f"Client \'{client_name}\': Chat presence in Group Chat ID [{chat_id}]: {state}")
        else:
             logger.info(f"Client \'{client_name}\': Chat presence from User/Chat ID [{chat_id}]: {state}")
    elif event_type == "ReadReceipt":
        chat_id = event_data.get("Chat") # JID of the chat (user or group) where receipts were updated
        logger.info(f"Client \'{client_name}\': Read receipt for Chat ID [{chat_id}]. Data: {event_data}")
    elif event_type == "HistorySync":
        # History sync can be complex, might not have a single chat_id in the top-level event_data
        logger.info(f"Client \'{client_name}\': History sync event. Data: {event_data}")
    else:
        chat_id = event_data.get("Chat") # Attempt to get chat_id for unhandled events
        logger.info(f"Client \'{client_name}\': Received unhandled event type \'{event_type}\' for chat {chat_id if chat_id else 'N/A'}. Data: {event_data}")

    # Revert to a more generic success message
    return {"status": "success", "message": f"Webhook for event \'{event_type}\' received for client \'{client_name}\'"}

@app.get("/")
async def root():
    return {"message": f"WuzAPI Webhook Handler running. POST events to {WEBHOOK_PATH}"}

if __name__ == "__main__":
    import uvicorn
    # Port 8000 is used internally in the container
    uvicorn.run(app, host="0.0.0.0", port=8000) 