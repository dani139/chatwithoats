import os
import sys
import httpx
from wuzapi_router import WuzapiHandler

# Test group ID
TEST_GROUP_ID = "120363402409737791@g.us"

def send_test_message():
    """Send a test message to WhatsApp group chat"""
    handler = WuzapiHandler()
    
    # Create a simple synchronous function to send a message
    message = "This is a test message to verify the fix for reaction loops."
    url = f"{handler.base_url}/chat/send/text"
    data = {"Phone": TEST_GROUP_ID, "Body": message}
    
    # Make the request
    response = httpx.post(url, headers=handler.headers, json=data, timeout=10.0)
    
    if response.status_code == 200:
        response_data = response.json()
        if response_data.get("success"):
            msg_id = response_data.get("data", {}).get("Id")
            print(f"Message sent successfully to {TEST_GROUP_ID}, ID: {msg_id}")
        else:
            print(f"Failed to send message: {response_data}")
    else:
        print(f"HTTP error: {response.status_code} - {response.text}")
    
if __name__ == "__main__":
    send_test_message() 