from fastapi import FastAPI, Request
import logging
import os

# Import routers with relative imports
from wuzapi_router import router as wuzapi_router
from conversations_router import router as conversations_router
from chat_settings_router import router as chat_settings_router
from tools_router import router as tools_router
from portal_users_router import router as portal_users_router

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="ChatWithOats Backend API")

# Include routers
app.include_router(wuzapi_router) 
app.include_router(conversations_router, prefix="/api")
app.include_router(chat_settings_router, prefix="/api")
app.include_router(tools_router, prefix="/api")
app.include_router(portal_users_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "ChatWithOats Backend API. See /docs for API endpoints."}

# Add a health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Startup event to initialize database connection
@app.on_event("startup")
async def startup_db_client():
    logger.info("Starting up the FastAPI application")
    
    # Read directly from the .env file instead of environment variable
    try:
        with open("/app/.env", "r") as f:
            content = f.read()
            if "OPENAI_API_KEY=" in content:
                key_part = content.split("OPENAI_API_KEY=")[1]
                if "\n" in key_part:
                    openai_key = key_part.split("\n")[0]
                else:
                    openai_key = key_part
                # Clean up any whitespace and newlines
                openai_key = openai_key.replace("\n", "").strip()
                # Set it in the environment for the app to use
                os.environ["OPENAI_API_KEY"] = openai_key
                masked_key = openai_key[:6] + "..." if openai_key else "NOT SET"
                logger.info(f"Successfully read API key from .env file: {masked_key}")
            else:
                masked_key = "KEY NOT FOUND IN .ENV"
    except Exception as e:
        logger.error(f"Error reading API key from file: {str(e)}")
        # Fallback to environment variable
        openai_key = os.environ.get("OPENAI_API_KEY", "NOT SET")
        masked_key = openai_key[:6] + "..." if openai_key and openai_key != "NOT SET" else openai_key
        
    logger.info(f"OPENAI_API_KEY on startup: {masked_key}")
    
    # Also directly check what's actually in the environment
    env_key = os.environ.get("OPENAI_API_KEY", "NOT_SET")
    masked_env_key = env_key[:6] + "..." if env_key and len(env_key) > 6 else env_key
    logger.info(f"Environment OPENAI_API_KEY value: {masked_env_key}")
    
    # Database connection setup happens in the db.py module

# Shutdown event to close database connection
@app.on_event("shutdown")
async def shutdown_db_client():
    logger.info("Shutting down the FastAPI application")
    # Any cleanup needed for database connections

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 