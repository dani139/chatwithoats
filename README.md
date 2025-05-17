# chatwithoats

## Database Migrations

For details on how to manage database schema changes and run migrations, please see the [Database Migrations Readme](db/README.md).

## WuzAPI (WhatsApp API)

For instructions on setting up, administering, and pairing the WuzAPI service, refer to the [WuzAPI Quick Guide](wuzapi/README.md).

## Backend Service

For information about the backend API, database models, and WhatsApp integration, see the [Backend Documentation](backend/README.md).

## OpenAI Tools Integration

ChatWithOats now features a powerful integration with OpenAI's function calling and tools system. The application supports:

- Web search tools using OpenAI's built-in web_search_preview type
- Custom function tools with direct schema definitions
- API-based function tools generated from OpenAPI specifications

Tools can be assigned to specific chat settings to control which capabilities are available in each conversation.

### Tool Types

- **Web Search Tools**: Allow the AI to search the web for up-to-date information
- **Function Tools**: Enable custom code execution with parameters defined by JSON Schema
- **API-based Function Tools**: Connect to external APIs by importing their OpenAPI specifications

### Creating Tools

Tools can be created via the API endpoints:
- `/tools` - Create individual tools
- `/tools/import-openapi` - Import an entire OpenAPI specification to create multiple API-based tools

### Assigning Tools to Chats

Once created, tools can be assigned to chat settings via:
- `/chat-settings/{settings_id}/tools/{tool_id}` - Add a tool to chat settings

## Tests

For information about running tests and test organization, see the [Tests Documentation](tests/README.md).

## Setup Fixes
for sql reads, find command so i wont need to press enter, it gets stuck.
have it clear logs before running docker every time.

## Future


add to tests if failed to print backend logs.
add maybe coverage , so when failed

add user login, have flow withouth gmail. but maybe impl together with gmail oath.

linking of portal user with whatsahh phone number

having object for whatsapp conversation, so also has chat config, but also has silent mode and maybe more.

implement database idea
implement ui elements idea

consider implemeting farmer idea, where all primitives can be used with ai, and chat has full context of actions and history.
