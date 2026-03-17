"""Shared layer module.

This module contains SHARED components used by both Webhook and Processing layers:
- SQLAlchemy ORM models
- Database configuration and session management
- Application configuration
- Logging configuration

These components are infrastructure-level and do not contain business logic.
"""

from app.shared.config import get_settings, Settings
from app.shared.database import get_session, init_db, session_scope, Base
from app.shared.logging_config import get_logger, setup_logging
from app.shared.models import Event, Commit, Branch, MergeRequest, AISummary, Repository

__all__ = [
    # Config
    "get_settings",
    "Settings",
    # Database
    "get_session",
    "init_db",
    "session_scope",
    "Base",
    # Logging
    "get_logger",
    "setup_logging",
    # ORM Models
    "Event",
    "Commit",
    "Branch",
    "MergeRequest",
    "AISummary",
    "Repository",
]
