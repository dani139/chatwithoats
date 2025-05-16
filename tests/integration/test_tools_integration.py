#!/usr/bin/env python3
import unittest
import requests
import json
import time
import os
from typing import Dict, Any, List, Optional

BASE_URL = "http://localhost:8000/api"

class ToolsIntegrationTest(unittest.TestCase):
    """
    Integration tests for testing tools functionality with the ChatWithOats API.
    
    These tests cover:
    1. Creating chat settings with and without web search
    2. Creating conversations
    3. Testing message responses with no tools
    4. Testing message responses with web search
    5. Testing speech API tool functionality
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
            "system_prompt": "You are a helpful assistant.",
            "enabled_tools": []
        }
        response = requests.post(f"{BASE_URL}/chat-settings?add_web_search=false", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to create chat settings: {response.text}")
        
        chat_settings = response.json()
        settings_id = chat_settings["id"]
        self.chat_settings_ids.append(settings_id)
        
        # Verify no tools are enabled
        self.assertEqual(len(chat_settings["enabled_tools"]), 0, 
                        f"Expected no tools but found: {chat_settings['enabled_tools']}")
        
        print(f"✓ Created chat settings without tools (ID: {settings_id})")
        return settings_id
    
    def test_02_create_chat_settings_with_web_search(self):
        """Test creating chat settings with web search tool"""
        # Create chat settings with web search
        data = {
            "name": "Test Settings - Web Search",
            "description": "Chat settings with web search",
            "system_prompt": "You are a helpful assistant.",
            "enabled_tools": []
        }
        response = requests.post(f"{BASE_URL}/chat-settings", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to create chat settings: {response.text}")
        
        chat_settings = response.json()
        settings_id = chat_settings["id"]
        self.chat_settings_ids.append(settings_id)
        
        # Verify web search tool is enabled
        self.assertEqual(len(chat_settings["enabled_tools"]), 1, 
                        f"Expected 1 tool but found: {len(chat_settings['enabled_tools'])}")
        
        # Get the OpenAI tools format
        response = requests.get(f"{BASE_URL}/chat-settings/{settings_id}/openai-tools")
        self.assertEqual(response.status_code, 200, f"Failed to get OpenAI tools: {response.text}")
        
        tools = response.json()
        self.assertEqual(len(tools), 1, f"Expected 1 tool but found: {len(tools)}")
        self.assertEqual(tools[0]["type"], "web_search_preview",
                         f"Expected web_search_preview tool but found: {tools[0]}")
        
        print(f"✓ Created chat settings with web search (ID: {settings_id})")
        return settings_id
    
    def test_03_create_chat_settings_with_web_search_and_speech(self):
        """Test creating chat settings with web search and speech tools"""
        # Create chat settings with web search
        data = {
            "name": "Test Settings - Web Search & Speech",
            "description": "Chat settings with web search and speech",
            "system_prompt": "You are a helpful assistant.",
            "enabled_tools": []
        }
        response = requests.post(f"{BASE_URL}/chat-settings", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to create chat settings: {response.text}")
        
        chat_settings = response.json()
        settings_id = chat_settings["id"]
        self.chat_settings_ids.append(settings_id)
        
        # Get the speech tool ID
        response = requests.get(f"{BASE_URL}/tools")
        self.assertEqual(response.status_code, 200, f"Failed to get tools: {response.text}")
        
        tools = response.json()
        speech_tool_id = None
        for tool in tools:
            if tool["name"] == "text_to_speech" or "speech" in tool["name"].lower():
                speech_tool_id = tool["id"]
                break
        
        self.assertIsNotNone(speech_tool_id, "No speech tool found")
        
        # Add speech tool to chat settings
        response = requests.post(f"{BASE_URL}/chat-settings/{settings_id}/tools/{speech_tool_id}")
        self.assertEqual(response.status_code, 200, f"Failed to add speech tool: {response.text}")
        
        # Get the OpenAI tools format
        response = requests.get(f"{BASE_URL}/chat-settings/{settings_id}/openai-tools")
        self.assertEqual(response.status_code, 200, f"Failed to get OpenAI tools: {response.text}")
        
        tools = response.json()
        self.assertEqual(len(tools), 2, f"Expected 2 tools but found: {len(tools)}")
        
        # Verify tool types
        tool_types = [tool["type"] for tool in tools]
        self.assertIn("web_search_preview", tool_types, "Web search tool not found")
        self.assertIn("function", tool_types, "Function tool (speech) not found")
        
        print(f"✓ Created chat settings with web search and speech (ID: {settings_id})")
        return settings_id
    
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
    
    def test_06_send_web_search_message(self):
        """Test sending a message that requires web search"""
        # Create chat settings with web search
        settings_id = self.test_02_create_chat_settings_with_web_search()
        
        # Create conversation
        data = {
            "name": "Test Web Search",
            "is_group": False,
            "chat_settings_id": settings_id,
            "participants": ["test_user"],
            "source_type": "PORTAL"
        }
        response = requests.post(f"{BASE_URL}/conversations", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to create conversation: {response.text}")
        
        conversation_id = response.json()["chatid"]
        self.conversation_ids.append(conversation_id)
        
        # Send message requiring web search
        data = {
            "content": "What is the current stock price of Apple (AAPL)?",
            "user_id": "test123",
            "username": "tester"
        }
        response = requests.post(f"{BASE_URL}/conversations/{conversation_id}/portal-message", json=data)
        self.assertEqual(response.status_code, 200, f"Failed to send message: {response.text}")
        
        result = response.json()
        self.assertIn("response_text", result, "Response doesn't contain response_text")
        self.assertNotIn("error", result["response_text"].lower(), "Response contains error")
        
        # Response should contain stock information
        has_stock_info = any(term in result["response_text"].lower() for term in 
                            ["aapl", "apple", "stock", "price", "market"])
        self.assertTrue(has_stock_info, 
                      f"Expected stock info but got: {result['response_text'][:100]}...")
        
        print(f"✓ Web search test passed: {result['response_text'][:20]}...")
    
    def test_07_test_speech_api(self):
        """Test the speech API tool directly"""
        # Get the speech tool ID
        response = requests.get(f"{BASE_URL}/tools")
        self.assertEqual(response.status_code, 200, f"Failed to get tools: {response.text}")
        
        tools = response.json()
        speech_tool_id = None
        for tool in tools:
            if tool["name"] == "text_to_speech" or "speech" in tool["name"].lower():
                speech_tool_id = tool["id"]
                break
        
        self.assertIsNotNone(speech_tool_id, "No speech tool found")
        
        # Execute speech tool directly
        data = {
            "tool_id": speech_tool_id,
            "arguments": {
                "model": "tts-1",
                "input": "This is a test of the speech API integration.",
                "voice": "alloy"
            }
        }
        
        # Use binary output to file
        response = requests.post(
            f"{BASE_URL}/tools/execute", 
            json=data,
            stream=True
        )
        self.assertEqual(response.status_code, 200, f"Failed to execute speech tool: {response.text}")
        
        # If successful, the response will either be binary audio data or a success message
        if response.headers.get('content-type') == 'audio/mpeg':
            # Save to file
            with open("test_speech_output.mp3", "wb") as f:
                for chunk in response.iter_content(chunk_size=128):
                    f.write(chunk)
            self.assertTrue(os.path.exists("test_speech_output.mp3"), "Speech output file not created")
            self.assertTrue(os.path.getsize("test_speech_output.mp3") > 0, "Speech output file is empty")
            print(f"✓ Speech API test passed: Generated audio file (test_speech_output.mp3)")
        else:
            # Text response indicating success
            self.assertIn("audio", response.text.lower(), 
                        f"Expected audio success message but got: {response.text}")
            print(f"✓ Speech API test passed: {response.text[:50]}...")


if __name__ == "__main__":
    unittest.main() 