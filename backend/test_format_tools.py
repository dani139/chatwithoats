#!/usr/bin/env python3
import json
import logging
from tools_router import format_tools_for_openai
from models import Tool, ToolType

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_openai_tool_formatting():
    """Test the formatting of OpenAI tools"""
    # Create a test OpenAI tool with web_search type
    web_search_tool = Tool(
        id="test-web-search",
        name="Web Search",
        description="Search the web for information",
        type=ToolType.OPENAI_TOOL,
        configuration={"type": "web_search"}
    )
    
    # Create a test API tool that will be converted to function type
    api_tool = Tool(
        id="test-api",
        name="Test API",
        description="A test API tool",
        type=ToolType.API_TOOL,
        configuration={
            "endpoint": "/api/test",
            "method": "POST",
            "server_url": "https://example.com",
            "params": {
                "query": {
                    "required": True,
                    "schema": {"type": "string"},
                    "description": "Search query"
                }
            },
            "body_schema": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Input text"
                    }
                },
                "required": ["input"]
            }
        }
    )
    
    # Format the tools
    tools = [web_search_tool, api_tool]
    formatted_tools = format_tools_for_openai(tools)
    
    # Print the results
    logger.info(f"Formatted {len(formatted_tools)} tools:")
    for i, tool in enumerate(formatted_tools):
        logger.info(f"Tool {i+1}: {json.dumps(tool, indent=2)}")
    
    # Verify the results
    assert len(formatted_tools) == 2, f"Expected 2 tools, got {len(formatted_tools)}"
    
    # Check web search tool
    assert formatted_tools[0]["type"] == "web_search", "Web search tool should have type='web_search'"
    
    # Check API tool converted to function
    assert formatted_tools[1]["type"] == "function", "API tool should be formatted as function"
    assert formatted_tools[1]["name"] == "test_api", f"API tool name incorrect: {formatted_tools[1]['name']}"
    assert "input" in formatted_tools[1]["parameters"]["properties"], "API tool should have 'input' parameter"
    
    logger.info("All tests passed!")

if __name__ == "__main__":
    test_openai_tool_formatting() 