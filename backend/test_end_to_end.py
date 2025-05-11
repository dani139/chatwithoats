#!/usr/bin/env python3
import requests
import json
import logging
import time
import uuid
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API base URL
BASE_URL = "http://localhost:8000/api"

def test_web_search_tool():
    """Test web search tool functionality"""
    # Create chat settings with web search
    chat_settings_data = {
        "name": "Test Web Search End-to-End",
        "description": "Chat settings for testing web search",
        "system_prompt": "You are a helpful assistant. When asked about current events or facts, you should search for the most up-to-date information.",
        "model": "gpt-4o", # Use a model that supports web search
        "enabled_tools": []
    }
    
    logger.info("Creating chat settings with web search...")
    response = requests.post(f"{BASE_URL}/chat-settings", json=chat_settings_data)
    if response.status_code != 200:
        logger.error(f"Failed to create chat settings: {response.text}")
        return False
    
    chat_settings = response.json()
    settings_id = chat_settings["id"]
    logger.info(f"Created chat settings with ID: {settings_id}")
    
    # Verify the web search tool is enabled
    response = requests.get(f"{BASE_URL}/chat-settings/{settings_id}/openai-tools")
    if response.status_code != 200:
        logger.error(f"Failed to get OpenAI tools: {response.text}")
        return False
    
    tools = response.json()
    logger.info(f"Tools for chat settings: {json.dumps(tools)}")
    
    if len(tools) != 1 or tools[0].get("type") != "web_search":
        logger.error(f"Expected web search tool but got: {tools}")
        return False
    
    logger.info("Web search tool is correctly configured")
    
    # Create a conversation
    conversation_data = {
        "name": "Web Search Test Conversation",
        "is_group": False,
        "chat_settings_id": settings_id,
        "participants": ["test_user"],
        "source_type": "PORTAL"
    }
    
    logger.info("Creating conversation...")
    response = requests.post(f"{BASE_URL}/conversations", json=conversation_data)
    if response.status_code != 200:
        logger.error(f"Failed to create conversation: {response.text}")
        return False
    
    conversation = response.json()
    conversation_id = conversation["chatid"]
    logger.info(f"Created conversation with ID: {conversation_id}")
    
    # Send a message that requires web search
    message_data = {
        "content": "What are the latest developments in AI?",
        "user_id": "test123",
        "username": "tester"
    }
    
    logger.info("Sending message that should trigger web search...")
    response = requests.post(f"{BASE_URL}/conversations/{conversation_id}/portal-message", json=message_data)
    if response.status_code != 200:
        logger.error(f"Failed to send message: {response.text}")
        return False
    
    result = response.json()
    response_text = result.get("response_text", "")
    logger.info(f"Response: {response_text[:200]}...")
    
    # Check if we got a proper response (not an error)
    if "error" in response_text.lower():
        logger.error(f"Received error response: {response_text}")
        return False
    
    logger.info("Web search test completed successfully!")
    return True

def test_api_tool():
    """Test API tool functionality"""
    # First, find or create a speech API tool
    logger.info("Looking for speech API tool...")
    response = requests.get(f"{BASE_URL}/tools")
    if response.status_code != 200:
        logger.error(f"Failed to get tools: {response.text}")
        return False
    
    tools = response.json()
    speech_tool_id = None
    
    for tool in tools:
        if tool["name"] == "text_to_speech" or "speech" in tool["name"].lower():
            speech_tool_id = tool["id"]
            break
    
    if not speech_tool_id:
        logger.info("No speech tool found, creating a new one...")
        # Create a new chat settings to get a speech tool created
        temp_settings_data = {
            "name": "Temp Settings for Speech",
            "description": "Temporary settings to get speech tool",
            "system_prompt": "You are a helpful assistant.",
            "model": "gpt-4o",
            "enabled_tools": []
        }
        
        response = requests.post(f"{BASE_URL}/chat-settings", json=temp_settings_data)
        if response.status_code != 200:
            logger.error(f"Failed to create temp chat settings: {response.text}")
            return False
        
        temp_settings_id = response.json()["id"]
        
        # Create speech tool associated with this settings
        response = requests.post(f"{BASE_URL}/tools/create-speech-tool/{temp_settings_id}")
        if response.status_code != 200:
            logger.error(f"Failed to create speech tool: {response.text}")
            return False
        
        speech_tool = response.json()
        speech_tool_id = speech_tool["id"]
    
    logger.info(f"Using speech tool with ID: {speech_tool_id}")
    
    # Create chat settings with speech tool
    chat_settings_data = {
        "name": "Test API Tool End-to-End",
        "description": "Chat settings for testing API tools",
        "system_prompt": "You are a helpful assistant. You can convert text to speech when requested.",
        "model": "gpt-4o", # Use a model that supports function tools
        "enabled_tools": []
    }
    
    logger.info("Creating chat settings...")
    response = requests.post(f"{BASE_URL}/chat-settings?add_web_search=false", json=chat_settings_data)
    if response.status_code != 200:
        logger.error(f"Failed to create chat settings: {response.text}")
        return False
    
    chat_settings = response.json()
    settings_id = chat_settings["id"]
    logger.info(f"Created chat settings with ID: {settings_id}")
    
    # Add the speech tool to the chat settings
    logger.info(f"Adding speech tool to chat settings...")
    response = requests.post(f"{BASE_URL}/chat-settings/{settings_id}/tools/{speech_tool_id}")
    if response.status_code != 200:
        logger.error(f"Failed to add speech tool: {response.text}")
        return False
    
    # Verify the speech tool is enabled
    response = requests.get(f"{BASE_URL}/chat-settings/{settings_id}/openai-tools")
    if response.status_code != 200:
        logger.error(f"Failed to get OpenAI tools: {response.text}")
        return False
    
    tools = response.json()
    logger.info(f"Tools for chat settings: {json.dumps(tools)}")
    
    if len(tools) != 1:
        logger.error(f"Expected 1 tool but got: {len(tools)}")
        return False
    
    if tools[0].get("type") != "function":
        logger.error(f"Expected function type but got: {tools[0].get('type')}")
        return False
    
    logger.info("Speech tool is correctly configured")
    
    # Create a conversation
    conversation_data = {
        "name": "API Tool Test Conversation",
        "is_group": False,
        "chat_settings_id": settings_id,
        "participants": ["test_user"],
        "source_type": "PORTAL"
    }
    
    logger.info("Creating conversation...")
    response = requests.post(f"{BASE_URL}/conversations", json=conversation_data)
    if response.status_code != 200:
        logger.error(f"Failed to create conversation: {response.text}")
        return False
    
    conversation = response.json()
    conversation_id = conversation["chatid"]
    logger.info(f"Created conversation with ID: {conversation_id}")
    
    # Send a message that should trigger the speech API tool
    message_data = {
        "content": "Please convert this text to speech: Hello, this is a test of the speech synthesis API.",
        "user_id": "test123",
        "username": "tester"
    }
    
    logger.info("Sending message that should trigger speech tool...")
    response = requests.post(f"{BASE_URL}/conversations/{conversation_id}/portal-message", json=message_data)
    if response.status_code != 200:
        logger.error(f"Failed to send message: {response.text}")
        return False
    
    result = response.json()
    response_text = result.get("response_text", "")
    logger.info(f"Response: {response_text[:200]}...")
    
    # Check if we got a proper response (not an error)
    if "error" in response_text.lower():
        logger.error(f"Received error response: {response_text}")
        return False
    
    logger.info("API tool test completed successfully!")
    return True

if __name__ == "__main__":
    logger.info("Starting tool tests...")
    
    # Test web search
    logger.info("Testing web search tool...")
    web_search_result = test_web_search_tool()
    
    # Test API tool
    logger.info("Testing API tool...")
    api_tool_result = test_api_tool()
    
    # Report results
    if web_search_result and api_tool_result:
        logger.info("All tests passed successfully!")
    else:
        logger.error("Tests failed!")
        if not web_search_result:
            logger.error("Web search test failed")
        if not api_tool_result:
            logger.error("API tool test failed") 