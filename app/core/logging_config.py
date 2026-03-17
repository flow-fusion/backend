"""Logging configuration."""

import logging
import sys
from pythonjsonlogger import jsonlogger
from .config import get_settings


def setup_logging() -> logging.Logger:
    """Configure application logging."""
    settings = get_settings()

    logger = logging.getLogger("ai_concurs")
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    if settings.LOG_FORMAT == "json":
        # JSON formatter for structured logging
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    else:
        # Standard formatter
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(f"ai_concurs.{name}")
