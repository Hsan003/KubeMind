"""
FastAPI application entry point
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config.settings import get_settings
from app.api.logs_routes import router
# from app.storage.database import init_db

settings = get_settings()

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version="1",
    description="AI-powered incident analyzer for Kubernetes clusters",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# app.include_router(router)
app.include_router(router)

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "hello world",
        "version": "1.1.67",
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        port=6767
    )
