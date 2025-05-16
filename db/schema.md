# ChatWithOats Database Schema

This document provides a clear overview of the database schema used in the ChatWithOats application.

## Enum Types

### MessageType
- `TEXT`: Text messages
- `VOICE`: Voice messages
- `IMAGE`: Image messages
- `MEDIA`: Other media messages
- `LOCATION`: Location messages
- `SYSTEM`: System messages
- `TOOL_CALL`: Tool call requests from the AI
- `TOOL_RESULT`: Results returned from tool executions

### SourceType
- `WHATSAPP`: Messages from WhatsApp
- `PORTAL`: Messages from the web portal

### ToolType
- `function`: Custom functions or API-based functions
- `web_search_preview`: OpenAI's web search functionality
- `file_search`: File search functionality

## Tables

### portal_users
Stores information about portal users.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | PK | Unique identifier for the user |
| username | String | NOT NULL | User's username |
| email | String | | User's email address |
| created_at | DateTime | NOT NULL, DEFAULT now() | When the user was created |
| updated_at | DateTime | | When the user was last updated |

### tools
Stores information about available AI tools.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | PK | Unique identifier for the tool |
| name | String | NOT NULL | Tool name |
| description | String | | Description of what the tool does |
| type | String | NOT NULL | Legacy column for backward compatibility |
| tool_type | String | | Type of tool (function, web_search_preview, file_search) |
| api_request_id | String | FK -> api_requests.id | Reference to API request for API-based tools |
| configuration | JSON | NOT NULL | Legacy column for backward compatibility |
| function_schema | JSON | | Direct OpenAI function schema for the tool |
| created_at | DateTime | NOT NULL, DEFAULT now() | When the tool was created |
| updated_at | DateTime | | When the tool was last updated |

### chat_settings
Stores settings for different chat configurations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | PK | Unique identifier for the chat settings |
| name | String | NOT NULL | Settings name |
| description | String | | Description of the settings |
| system_prompt | String | NOT NULL | System prompt to use with OpenAI |
| model | String | NOT NULL, DEFAULT 'gpt-4o-mini' | OpenAI model to use |

### chat_settings_tools
Association table for many-to-many relationship between chat settings and tools.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| chat_settings_id | String | PK, FK -> chat_settings.id | Reference to chat settings |
| tool_id | String | PK, FK -> tools.id | Reference to tool |

### api_requests
Stores information about API requests that can be used as tools.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | PK | Unique identifier for the API request |
| api_id | String | NOT NULL, FK -> apis.id | Reference to the API |
| path | String | NOT NULL | API endpoint path |
| method | String | NOT NULL | HTTP method (GET, POST, etc.) |
| description | String | | Description of the API request |
| request_body_schema | JSON | | Schema for the request body |
| response_schema | JSON | | Schema for the response |
| skip_parameters | JSON | | Parameters to skip when generating schema |
| constant_parameters | JSON | | Parameters with constant values |

### apis
Stores information about APIs that can be used as tools.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | PK | Unique identifier for the API |
| server | String | NOT NULL | API server URL |
| service | String | NOT NULL | Service name |
| provider | String | NOT NULL | API provider |
| version | String | NOT NULL | API version |
| description | String | | Description of the API |
| processed | Boolean | NOT NULL | Whether the API has been processed |

### conversations
Stores information about conversations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| chatid | String | PK | Unique identifier for the conversation |
| name | String | | Conversation name |
| is_group | Boolean | NOT NULL | Whether the conversation is a group |
| group_name | String | | Group name (for group conversations) |
| created_at | DateTime | NOT NULL, DEFAULT now() | When the conversation was created |
| updated_at | DateTime | | When the conversation was last updated |
| silent | Boolean | NOT NULL | Whether the AI should respond silently |
| enabled_apis | JSON | NOT NULL | APIs enabled for this conversation |
| paths | JSON | NOT NULL | Authorized API paths for this conversation |
| chat_settings_id | String | FK -> chat_settings.id | Reference to chat settings |
| portal_user_id | String | FK -> portal_users.id | Reference to portal user |
| source_type | String | NOT NULL, DEFAULT 'WHATSAPP' | Source of the conversation |

### conversation_participants
Stores information about participants in conversations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| number | String | PK | Participant's phone number |
| chatid | String | PK, FK -> conversations.chatid | Reference to conversation |

### messages
Stores messages in conversations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | String | PK | Unique identifier for the message |
| chatid | String | NOT NULL, FK -> conversations.chatid | Reference to conversation |
| sender | String | | Sender identifier |
| sender_name | String | | Sender name |
| type | String | NOT NULL | Message type (TEXT, VOICE, etc.) |
| content | String | | Message content |
| file_path | String | | Path to file (for media messages) |
| caption | String | | Caption for media messages |
| latitude | Float | | Latitude (for location messages) |
| longitude | Float | | Longitude (for location messages) |
| quoted_message_id | String | FK -> messages.id | Reference to quoted message |
| quoted_message_content | String | | Content of quoted message |
| role | String | | Message role (user, assistant, system) |
| tool_call_id | String | | ID for tool calls |
| function_name | String | | Function name for tool calls |
| function_arguments | String | | Function arguments for tool calls |
| function_result | String | | Function results for tool calls |
| created_at | DateTime | DEFAULT now() | When the message was created |

## Relationships

- A **portal_user** can have many **conversations**
- A **tool** can be associated with many **chat_settings** through **chat_settings_tools**
- A **tool** can be associated with one **api_request**
- An **api_request** can be associated with many **tools**
- An **api_request** belongs to one **api**
- An **api** can have many **api_requests**
- A **chat_settings** can be associated with many **tools** through **chat_settings_tools**
- A **chat_settings** can have many **conversations**
- A **conversation** belongs to one **chat_settings**
- A **conversation** belongs to one **portal_user**
- A **conversation** can have many **conversation_participants**
- A **conversation** can have many **messages**
- A **message** belongs to one **conversation**
- A **message** can quote another **message** 