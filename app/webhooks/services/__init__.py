"""Webhook service layer.

This module contains the business logic for handling GitLab webhooks.
It coordinates parsing, validation, and storage of webhook events.
"""

import logging
from typing import Any, Optional

from app.shared.database import Session
from app.webhooks.models import NormalizedEvent
from app.webhooks.repositories import WebhookRepository
from app.webhooks.services.gitlab_parser import GitLabParser
from app.processing.webhook_integration import queue_event

logger = logging.getLogger(__name__)


class WebhookService:
    """
    Service for handling GitLab webhook events.
    
    This service is the main entry point for webhook processing. It:
    1. Parses incoming payloads
    2. Validates the data
    3. Stores events in the database
    4. Queues events for async processing
    
    This is the WEBHOOK LAYER - it does NOT process events,
    it only receives and stores them for later processing.
    """

    def __init__(self, db: Session):
        """
        Initialize the webhook service.
        
        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.parser = GitLabParser()
        self.repository = WebhookRepository(db)

    def handle_webhook(
        self,
        payload: dict[str, Any],
        event_type_header: str,
    ) -> dict[str, Any]:
        """
        Handle an incoming GitLab webhook.
        
        This is the main entry point for webhook handling. It performs:
        1. Parse and normalize the payload
        2. Store in database
        3. Queue for async processing
        
        Args:
            payload: Raw JSON payload from GitLab
            event_type_header: X-Gitlab-Event header value
            
        Returns:
            Dictionary with handling result:
            - status: "success", "ignored", or "error"
            - event_id: Database ID of the created event (if successful)
            - event_type: Normalized event type
            - jira_issue: Extracted Jira issue key (if any)
            
        Raises:
            ValueError: If payload is invalid
        """
        # Step 1: Parse and normalize
        normalized_event = self._parse_payload(payload, event_type_header)
        
        if normalized_event is None:
            return {"status": "ignored", "reason": "unknown_event_type"}

        # Step 2: Store in database
        db_event = self.repository.store_event(normalized_event)

        # Step 3: Queue for async processing (INTEGRATION POINT)
        # This is where webhook layer hands off to processing layer
        queue_event(db_event.id)

        logger.info(
            f"Successfully processed {event_type_header} for "
            f"{normalized_event.repository}/{normalized_event.branch}. "
            f"Event ID: {db_event.id}, queued for processing"
        )

        return {
            "status": "success",
            "event_id": str(db_event.id),
            "event_type": normalized_event.event_type,
            "repository": normalized_event.repository,
            "jira_issue": normalized_event.jira_issue or "none",
        }

    def _parse_payload(
        self,
        payload: dict[str, Any],
        event_type_header: str,
    ) -> Optional[NormalizedEvent]:
        """
        Parse and normalize the webhook payload.
        
        Args:
            payload: Raw JSON payload from GitLab
            event_type_header: X-Gitlab-Event header value
            
        Returns:
            NormalizedEvent if parsing succeeds, None if event type is unknown
            
        Raises:
            ValueError: If payload is invalid
        """
        if not payload:
            raise ValueError("Empty payload received")

        if not event_type_header:
            raise ValueError("Event type header is missing")

        return self.parser.parse(payload, event_type_header)
