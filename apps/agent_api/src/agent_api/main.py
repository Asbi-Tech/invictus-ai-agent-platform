"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_api.api.routes import router
from common.config import get_settings
from common.logging import get_logger, setup_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    setup_logging(
        log_level=settings.log_level,
        json_logs=settings.is_production,
    )
    logger = get_logger(__name__)
    logger.info(
        "Starting Invictus AI Copilot API",
        environment=settings.environment,
        version="0.1.0",
    )

    yield

    # Shutdown
    logger.info("Shutting down Invictus AI Copilot API")


app = FastAPI(
    title="Invictus AI Copilot API",
    description="AI Copilot Agent for Invictus AI wealth management platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - configure appropriately for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "environment": settings.environment,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Invictus AI Copilot API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
