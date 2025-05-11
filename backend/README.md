# ChatWithOats Backend

FastAPI-based backend service for the ChatWithOats application.

## Key Files

- `main.py`: Application entry point and API router configuration
- `db.py`: Database connection and session management
- `models.py`: SQLAlchemy and Pydantic models for database entities and API schemas
- `wuzapi_router.py`: WhatsApp webhook handler and messaging logic
- `conversations_router.py`: Conversation CRUD operations endpoints
- `tools_router.py`: API tool management, OpenAPI import, and tool execution
- `openai_helper.py`: OpenAI API integration, message processing, and tool execution

## Features

- WhatsApp integration via WuzAPI
- Conversation management and message handling
- OpenAI API integration for AI assistant responses
- Tool execution framework for API integrations
- OpenAPI specification import for creating API tools
- Text-to-speech capability via OpenAI API

## Environment Variables

- `OPENAI_API_KEY`: OpenAI API key for AI assistant and speech functionality
- `DATABASE_URL`: PostgreSQL connection string
- `WUZAPI_TOKEN`: Authentication token for WhatsApp API

## Development

```bash
# Start the backend service
docker compose -f docker-compose.dev.yml up -d backend

# View logs
docker compose -f docker-compose.dev.yml logs -f backend

# Rebuild after changes to dependencies
docker compose -f docker-compose.dev.yml up --build -d backend
```

## Database

The backend uses PostgreSQL with tables for:
- Conversations
- Messages
- Conversation participants 