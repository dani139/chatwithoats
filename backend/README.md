# ChatWithOats Backend

FastAPI-based backend service for the ChatWithOats application.

## Overview

The backend provides:
- WhatsApp integration via WuzAPI
- Conversation management
- Message storage and processing
- API endpoints for frontend communication

## Architecture

- **FastAPI**: Main web framework
- **SQLAlchemy**: Database ORM
- **PostgreSQL**: Primary database
- **WuzAPI**: WhatsApp client integration

## Key Components

- `main.py`: Application entry point and router configuration
- `db.py`: Database connection and session management
- `models.py`: SQLAlchemy and Pydantic models
- `wuzapi_router.py`: WhatsApp webhook handler and messaging logic
- `conversations_router.py`: Conversation CRUD endpoints

## API Endpoints

- `/wuzapi_webhook`: Receives events from WuzAPI
- `/api/conversations`: CRUD operations for conversations
- `/messages`: Process and respond to messages

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