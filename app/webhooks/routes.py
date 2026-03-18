"""GitLab webhook API endpoints.

This module provides the webhook receiver endpoint that handles incoming
GitLab webhook events. It is part of the WEBHOOK LAYER.

The webhook layer is responsible for:
1. Receiving HTTP requests from GitLab
2. Validating authentication tokens
3. Parsing and validating payloads
4. Storing events in the database
5. Queuing events for async processing

It does NOT process events - that is handled by the PROCESSING LAYER.
"""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.shared.database import get_session
from app.webhooks.services import WebhookService

logger = logging.getLogger(__name__)

# Create router with prefix
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# Header names for GitLab webhooks
GITLAB_EVENT_HEADER = "X-Gitlab-Event"
GITLAB_TOKEN_HEADER = "X-Gitlab-Token"


@router.post("/gitlab", status_code=status.HTTP_200_OK)
async def gitlab_webhook(
    request: Request,
    db: Session = Depends(get_session),
    x_gitlab_event: Optional[str] = Header(default=None, alias=GITLAB_EVENT_HEADER),
    x_gitlab_token: Optional[str] = Header(default=None, alias=GITLAB_TOKEN_HEADER),
) -> dict[str, str]:
    """
    Receive and process GitLab webhook events.

    This endpoint handles GitLab Push Hook and Merge Request Hook events.
    It validates the secret token, parses the payload, extracts Jira issue keys,
    stores all data in the database, and queues for further processing.

    WEBHOOK LAYER - Does not process events, only receives and stores them.

    Args:
        request: FastAPI request object containing the webhook payload.
        db: Database session (injected by FastAPI).
        x_gitlab_event: Event type from GitLab (e.g., "Push Hook").
        x_gitlab_token: Secret token for authentication.

    Returns:
        Success response with event type and event_id for tracking.
        Possible status values:
        - "success": Event was stored and queued
        - "ignored": Event type is unknown (no action taken)

    Raises:
        HTTPException: 403 if token is invalid, 400 if payload is invalid.
    """
    # Step 1: Validate secret token (WEBHOOK LAYER)
    _validate_token(x_gitlab_token)

    # Step 2: Validate event type header (WEBHOOK LAYER)
    if not x_gitlab_event:
        logger.warning("Webhook request missing X-Gitlab-Event header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Gitlab-Event header",
        )

    # Step 3: Parse JSON payload (WEBHOOK LAYER)
    payload = await _parse_payload(request)

    # Step 4: Handle webhook (WEBHOOK LAYER)
    # This parses, stores, and queues the event
    service = WebhookService(db)
    result = service.handle_webhook(payload, x_gitlab_event)

    if result["status"] == "ignored":
        return result

    return result


def _validate_token(token: Optional[str]) -> None:
    """
    Validate the GitLab webhook secret token.

    WEBHOOK LAYER - HTTP authentication.

    Args:
        token: Token from X-Gitlab-Token header.

    Raises:
        HTTPException: 403 if token is missing or invalid.
    """
    from app.shared.config import get_settings

    settings = get_settings()

    if not token:
        logger.warning("Webhook request missing X-Gitlab-Token header")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing authentication token",
        )

    if token != settings.gitlab_webhook_secret:
        logger.warning("Invalid webhook token received")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication token",
        )


async def _parse_payload(request: Request) -> dict:
    """
    Parse and validate the JSON payload from the request.

    WEBHOOK LAYER - HTTP payload parsing.

    Args:
        request: FastAPI request object.

    Returns:
        Parsed JSON payload as dictionary.

    Raises:
        HTTPException: 400 if payload is invalid JSON or empty.
    """
    import json

    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    if not payload:
        logger.warning("Empty payload received")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty payload",
        )

    return payload
