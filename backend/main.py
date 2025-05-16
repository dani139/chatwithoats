from fastapi import FastAPI, Request
import logging
import os
from dotenv import load_dotenv

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
    
    # Use python-dotenv to load environment variables
    try:
        # Load .env file
        load_dotenv("/app/.env")
        
        # Get OpenAI API key from environment
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            logger.error("OpenAI API key is empty or not found in .env file")
            raise ValueError("OpenAI API key cannot be empty")
            
        # Log masked key for verification
        masked_key = key[:6] + "..." if len(key) > 6 else "[INVALID KEY]"
        logger.info(f"OPENAI_API_KEY loaded from .env: {masked_key}")
            
    except Exception as e:
        logger.error(f"Failed to load OpenAI API key: {str(e)}")
        raise ValueError(f"Application startup failed: {str(e)}")
    
    # Database connection setup happens in the db.py module

# Shutdown event to close database connection
@app.on_event("shutdown")
async def shutdown_db_client():
    logger.info("Shutting down the FastAPI application")
    # Any cleanup needed for database connections

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 