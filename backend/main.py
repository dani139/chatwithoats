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
    # Database connection setup happens in the db.py module

# Shutdown event to close database connection
@app.on_event("shutdown")
async def shutdown_db_client():
    logger.info("Shutting down the FastAPI application")
    # Any cleanup needed for database connections

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 