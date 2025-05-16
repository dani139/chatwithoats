#!/usr/bin/env python3
import unittest
import requests
import json
import time
import os
import pytest
from typing import Dict, Any, List, Optional

BASE_URL = "http://localhost:8000/api"

@pytest.mark.api
class APITest(unittest.TestCase):
    """
    API tests for ChatWithOats backend.
    
    These tests cover:
    1. Creating chat settings with and without tools
    2. Creating conversations
    3. Testing message responses with different tool configurations
    4. Testing web search functionality
    """
    
    def setUp(self):
        """Setup test data"""
        self.chat_settings_ids = []
        self.conversation_ids = []
        
    def tearDown(self):
        """Clean up created resources (not implemented for demo)"""
        # In a real test, we might delete the resources we created
        pass
    
    def test_01_create_chat_settings_without_tools(self):
        """Test creating chat settings without any tools"""
        # Create chat settings without web search
        data = {
            "name": "Test Settings - No Tools",
            "description": "Chat settings without any tools",
            "system_prompt": "You are a helpful assistant."
            # enabled_tools field removed as it's no longer used
        }
        response = requests.post(f"{BASE_URL}/chat-settings", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to create chat settings: {response.text}")
        
        chat_settings = response.json()
        settings_id = chat_settings["id"]
        self.chat_settings_ids.append(settings_id)
        
        # Get tools via the tools endpoint rather than enabled_tools field
        response = requests.get(f"{BASE_URL}/chat-settings/{settings_id}/tools")
        self.assertEqual(response.status_code, 200, f"Failed to get tools: {response.text}")
        
        tools = response.json()
        self.assertEqual(len(tools), 0, f"Expected no tools but found: {tools}")
        
        print(f"✓ Created chat settings without tools (ID: {settings_id})")
        return settings_id
    
    def test_02_create_chat_settings_second(self):
        """Test creating a second chat settings instance"""
        # Create second chat settings
        data = {
            "name": "Test Settings - Second Instance",
            "description": "Another chat settings instance for testing",
            "system_prompt": "You are a helpful assistant."
            # enabled_tools field removed as it's no longer used
        }
        response = requests.post(f"{BASE_URL}/chat-settings", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to create chat settings: {response.text}")
        
        chat_settings = response.json()
        settings_id = chat_settings["id"]
        self.chat_settings_ids.append(settings_id)
        
        # Get tools via the tools endpoint rather than enabled_tools field
        response = requests.get(f"{BASE_URL}/chat-settings/{settings_id}/tools")
        self.assertEqual(response.status_code, 200, f"Failed to get tools: {response.text}")
        
        tools = response.json()
        self.assertEqual(len(tools), 0, f"Expected 0 tools but found: {len(tools)}")
        
        # Get the OpenAI tools format - should be empty
        response = requests.get(f"{BASE_URL}/chat-settings/{settings_id}/openai-tools")
        self.assertEqual(response.status_code, 200, f"Failed to get OpenAI tools: {response.text}")
        
        tools = response.json()
        self.assertEqual(len(tools), 0, f"Expected 0 tools but found: {len(tools)}")
        
        print(f"✓ Created second chat settings (ID: {settings_id})")
        return settings_id
    
    # def test_03_create_chat_settings_with_web_search_and_speech(self):
    #     """Test creating chat settings with web search and speech tools"""
    #     # Create chat settings with web search
    #     data = {
    #         "name": "Test Settings - Web Search & Speech",
    #         "description": "Chat settings with web search and speech",
    #         "system_prompt": "You are a helpful assistant.",
    #         "enabled_tools": []
    #     }
    #     response = requests.post(f"{BASE_URL}/chat-settings", json=data)
    #     self.assertEqual(response.status_code, 200, f"Failed to create chat settings: {response.text}")
    #     
    #     chat_settings = response.json()
    #     settings_id = chat_settings["id"]
    #     self.chat_settings_ids.append(settings_id)
    #     
    #     # Get the speech tool ID
    #     response = requests.get(f"{BASE_URL}/tools")
    #     self.assertEqual(response.status_code, 200, f"Failed to get tools: {response.text}")
    #     
    #     tools = response.json()
    #     speech_tool_id = None
    #     for tool in tools:
    #         if tool["name"] == "text_to_speech" or "speech" in tool["name"].lower():
    #             speech_tool_id = tool["id"]
    #             break
    #     
    #     self.assertIsNotNone(speech_tool_id, "No speech tool found")
    #     
    #     # Add speech tool to chat settings
    #     response = requests.post(f"{BASE_URL}/chat-settings/{settings_id}/tools/{speech_tool_id}")
    #     self.assertEqual(response.status_code, 200, f"Failed to add speech tool: {response.text}")
    #     
    #     # Get the OpenAI tools format
    #     response = requests.get(f"{BASE_URL}/chat-settings/{settings_id}/openai-tools")
    #     self.assertEqual(response.status_code, 200, f"Failed to get OpenAI tools: {response.text}")
    #     
    #     tools = response.json()
    #     self.assertEqual(len(tools), 2, f"Expected 2 tools but found: {len(tools)}")
    #     
    #     # Verify tool types
    #     tool_types = [tool["type"] for tool in tools]
    #     self.assertIn("web_search_preview", tool_types, "Web search tool not found")
    #     self.assertIn("function", tool_types, "Function tool (speech) not found")
    #     
    #     print(f"✓ Created chat settings with web search and speech (ID: {settings_id})")
    #     return settings_id
    
    def test_04_create_conversation(self):
        """Test creating a conversation"""
        # Ensure we have chat settings to use
        if not self.chat_settings_ids:
            settings_id = self.test_01_create_chat_settings_without_tools()
        else:
            settings_id = self.chat_settings_ids[0]
        
        # Create conversation
        data = {
            "name": "Test Conversation",
            "is_group": False,
            "chat_settings_id": settings_id,
            "participants": ["test_user"],
            "source_type": "PORTAL"
        }
        response = requests.post(f"{BASE_URL}/conversations", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to create conversation: {response.text}")
        
        conversation = response.json()
        conversation_id = conversation["chatid"]
        self.conversation_ids.append(conversation_id)
        
        print(f"✓ Created conversation (ID: {conversation_id})")
        return conversation_id
    
    def test_05_send_simple_message_no_tools(self):
        """Test sending a simple message to a conversation without tools"""
        # Create chat settings without tools
        settings_id = self.test_01_create_chat_settings_without_tools()
        
        # Create conversation
        data = {
            "name": "Test Simple Message",
            "is_group": False,
            "chat_settings_id": settings_id,
            "participants": ["test_user"],
            "source_type": "PORTAL"
        }
        response = requests.post(f"{BASE_URL}/conversations", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to create conversation: {response.text}")
        
        conversation_id = response.json()["chatid"]
        self.conversation_ids.append(conversation_id)
        
        # Send message
        data = {
            "content": "What is 2+2?",
            "user_id": "test123",
            "username": "tester"
        }
        response = requests.post(f"{BASE_URL}/conversations/{conversation_id}/portal-message", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to send message: {response.text}")
        
        result = response.json()
        self.assertIn("response_text", result, "Response doesn't contain response_text")
        self.assertNotIn("error", result["response_text"].lower(), "Response contains error")
        
        # Response should be something like "2 + 2 equals 4"
        self.assertIn("4", result["response_text"], 
                    f"Expected answer with '4' but got: {result['response_text']}")
        
        print(f"✓ Simple message test passed: {result['response_text'][:20]}...")
    
    def test_06_send_knowledge_based_message(self):
        """Test sending a message that requires general knowledge"""
        # Create second chat settings
        settings_id = self.test_02_create_chat_settings_second()
        
        # Create conversation
        data = {
            "name": "Test Knowledge-Based Message",
            "is_group": False,
            "chat_settings_id": settings_id,
            "participants": ["test_user"],
            "source_type": "PORTAL"
        }
        response = requests.post(f"{BASE_URL}/conversations", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to create conversation: {response.text}")
        
        conversation_id = response.json()["chatid"]
        self.conversation_ids.append(conversation_id)
        
        # Send message that requires general knowledge
        data = {
            "content": "What is the capital of France?",
            "user_id": "test123",
            "username": "tester"
        }
        response = requests.post(f"{BASE_URL}/conversations/{conversation_id}/portal-message", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to send message: {response.text}")
        
        result = response.json()
        self.assertIn("response_text", result, "Response doesn't contain response_text")
        self.assertNotIn("error", result["response_text"].lower(), "Response contains error")
        
        # Response should mention Paris
        self.assertIn("Paris", result["response_text"], 
                    f"Expected answer with 'Paris' but got: {result['response_text']}")
        
        print(f"✓ Knowledge-based message test passed: {result['response_text'][:20]}...")

# Add other test classes here if needed

if __name__ == "__main__":
    unittest.main() 