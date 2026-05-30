"""
FastAPI application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config.settings import get_settings
from app.api.logs_routes import router as logs_router
from app.api.events import router as events_router
from app.api.routes import router as metrics_router
#from app.storage.database import init_db

settings = get_settings()

# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
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
app.include_router(logs_router)
app.include_router(events_router)
app.include_router(metrics_router)

"""
@app.on_event("startup")
async def startup_event() -> None:
    #Initialize lightweight startup dependencies.
    init_db()
"""


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT
    )
