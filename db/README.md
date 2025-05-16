# Database Schema for ChatWithOats

This directory contains the database schema for the ChatWithOats application.

## Files

- `schema.md`: A clear, descriptive representation of the database schema in Markdown format, suitable for documentation and understanding the data model. This file is designed to be easily read by both humans and LLMs.

- `schema.sql`: The SQL schema definition to initialize the database. This script creates all the tables, relationships, constraints, and indexes needed by the application.

## Database Overview

ChatWithOats uses PostgreSQL as its database. The database stores:

- Conversations and messages
- User information
- Chat settings and configurations
- Tool definitions and configurations
- API information for external services

## Making Database Changes

To make changes to the database schema:

1. **Edit the `schema.sql` file** with your changes (add/modify tables, columns, indexes, etc.)

2. **Tear down the database container and its volume**:
   ```bash
   docker compose -f docker-compose.dev.yml down -v postgres
   ```
   The `-v` flag is important as it removes the volume, ensuring the database is recreated from scratch

3. **Start the database container again**:
   ```bash
   docker compose -f docker-compose.dev.yml up -d postgres
   ```
   The container will initialize with your updated schema

4. **Verify your changes**:
   ```bash
   # Example: check table structure
   docker compose -f docker-compose.dev.yml exec postgres psql -U admin -d chatwithoats -c "\d table_name"

   # Example: check columns in a table
   docker compose -f docker-compose.dev.yml exec postgres psql -U admin -d chatwithoats -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'table_name' ORDER BY ordinal_position;"
   ```

5. **Start the backend service** to ensure it works with the updated schema:
   ```bash
   docker compose -f docker-compose.dev.yml up -d backend
   ```

6. **Update `schema.md`** to reflect your changes, ensuring the documentation stays in sync with the actual schema.

> **Note:** This approach rebuilds the database from scratch, so all existing data will be lost when making schema changes. This is typically acceptable in development but would require a migration strategy in production.

## Database Setup

To initialize a fresh database with the schema:

```bash
psql -U your_username -d your_database_name -f schema.sql
```

You can also use the schema during Docker deployment by mounting it as a volume:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/schema.sql:/docker-entrypoint-initdb.d/schema.sql
    # ...other configuration...
```

## Schema Design

The database follows a relational design with several key entities:

1. **Users and Conversations**: Manages user accounts and their conversations
2. **Messages**: Stores all message content and metadata
3. **Tools and APIs**: Configuration for OpenAI function calling and tools
4. **Chat Settings**: Controls AI behavior and available tools

See `schema.md` for a comprehensive overview of all tables, columns, and relationships. 