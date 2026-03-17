"""
AI Concurs Backend - Main Application Entry Point.

Combined GitLab Webhook Receiver and Processing Service.

Usage:
    # Run FastAPI server (webhook receiver + API)
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    
    # Run background worker (event processing)
    python -m app.workers.worker --direct

Environment Variables:
    GITLAB_WEBHOOK_SECRET: Secret token for verifying GitLab webhooks (required)
    GITLAB_API_TOKEN: Token for GitLab API access (for context enrichment)
    DATABASE_URL: PostgreSQL connection URL
    REDIS_HOST: Redis host
    REDIS_PORT: Redis port
    LOG_LEVEL: Logging level
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.webhooks import router as webhooks_router
from app.shared.config import get_settings
from app.shared.database import init_db

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting AI Concurs Backend Service...")
    logger.info(f"Log level: {settings.LOG_LEVEL}")

    # Initialize database tables
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    logger.info("AI Concurs Backend Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down AI Concurs Backend Service...")


# Create FastAPI application
app = FastAPI(
    title="AI Concurs Backend",
    version="1.0.0",
    description="GitLab Webhook Receiver and AI Summary Generator for Jira",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include routers
app.include_router(webhooks_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint for monitoring and load balancers."""
    return {"status": "healthy"}


@app.get("/ready", tags=["health"])
async def readiness_check() -> dict[str, str]:
    """Readiness check endpoint for Kubernetes probes."""
    return {"status": "ready"}


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """Root endpoint with API information."""
    return {
        "service": "AI Concurs Backend",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "webhook": "/webhooks/gitlab",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
