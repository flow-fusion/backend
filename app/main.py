"""
FlowFusion - Main Application Entry Point.

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

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.webhooks import router as webhooks_router
from app.shared.config import get_settings
from app.shared.database import init_db, engine
from app.shared.logging_config import get_logger

logger = get_logger("main")

# Get settings and validate
settings = get_settings()
settings.validate_required()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION}...")
    logger.info(f"Log level: {settings.LOG_LEVEL}")
    logger.info(f"Debug mode: {settings.DEBUG}")

    # Initialize database tables
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    logger.info(f"{settings.APP_NAME} started successfully")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}...")
    # Cleanup: dispose database engine
    engine.dispose()
    logger.info(f"{settings.APP_NAME} shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="GitLab Webhook Receiver and AI Summary Generator for Jira",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,  # Disable docs in production
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# Security: TrustedHost middleware (for production)
if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"],  # Update with your domain in production
    )

# CORS middleware - configure appropriately for production
if settings.DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Production CORS settings - update with your domain
    allowed_origins = [
        origin.strip() for origin in settings.JIRA_URL.split(",") if origin.strip()
    ]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["POST", "GET", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Gitlab-Event", "X-Gitlab-Token"],
        )


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unhandled exceptions."""
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "path": request.url.path if not settings.DEBUG else str(exc),
        },
    )


# Include routers
app.include_router(webhooks_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """
    Health check endpoint for monitoring and load balancers.
    
    Returns basic health status without checking dependencies.
    """
    return {"status": "healthy", "version": settings.VERSION}


@app.get("/ready", tags=["health"])
async def readiness_check() -> dict:
    """
    Readiness check endpoint for Kubernetes probes.
    
    Checks database and Redis connectivity.
    """
    from sqlalchemy import text
    
    result = {"status": "ready", "checks": {}}
    
    # Check database
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        result["checks"]["database"] = "ok"
    except Exception as e:
        result["checks"]["database"] = f"error: {str(e)}"
        result["status"] = "not_ready"
    
    # Check Redis
    try:
        from app.processing.event_queue_service import EventQueueService
        queue_service = EventQueueService()
        queue_service.get_queue_stats()
        result["checks"]["redis"] = "ok"
    except Exception as e:
        result["checks"]["redis"] = f"error: {str(e)}"
        result["status"] = "not_ready"
    
    status_code = status.HTTP_200_OK if result["status"] == "ready" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=result)


@app.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "running",
        "endpoints": {
            "webhook": "/webhooks/gitlab",
            "health": "/health",
            "ready": "/ready",
            "docs": "/docs" if settings.DEBUG else "disabled in production",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
