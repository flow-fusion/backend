"""Webhooks layer module.

This module contains the WEBHOOK LAYER which is responsible for:
1. Receiving HTTP requests from GitLab
2. Validating authentication tokens
3. Parsing and validating payloads
4. Storing events in the database
5. Queuing events for async processing

This is SEPARATE from the processing layer which handles async event processing.
"""

from app.webhooks.routes import router
from app.webhooks.services import WebhookService
from app.webhooks.models import NormalizedEvent, GitLabCommit
from app.webhooks.repositories import WebhookRepository

__all__ = [
    "router",
    "WebhookService",
    "WebhookRepository",
    "NormalizedEvent",
    "GitLabCommit",
]
