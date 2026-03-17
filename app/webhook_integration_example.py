"""
Example webhook handler showing integration with the processing layer.

This file demonstrates how the existing webhook layer should integrate
with the new processing layer.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session
from app.models import Event, Commit
from app.processing.webhook_integration import queue_event
from app.core.logging_config import get_logger

logger = get_logger("webhook_example")


def handle_gitlab_webhook(
    session: Session,
    payload: Dict[str, Any],
) -> int:
    """
    Handle an incoming GitLab webhook.
    
    This is an example of how the existing webhook layer should
    integrate with the processing layer.
    
    Args:
        session: Database session.
        payload: Normalized webhook payload.
        
    Returns:
        Event ID.
    """
    # Extract event type
    event_type = payload.get("event_type", "unknown")
    
    # Create event record
    event = Event(
        event_type=event_type,
        payload_json=payload,
    )
    session.add(event)
    session.flush()  # Get event ID
    
    event_id = event.id
    
    # Process commits if present
    commits_data = payload.get("commits", [])
    branch = payload.get("branch")
    repository = payload.get("repository")
    jira_issue = payload.get("jira_issue")
    
    for commit_data in commits_data:
        commit = Commit(
            commit_id=commit_data.get("commit_id"),
            message=commit_data.get("message"),
            author=commit_data.get("author"),
            timestamp=commit_data.get("timestamp"),
            branch=branch,
            repository=repository,
            jira_issue=jira_issue,
            event_id=event_id,
        )
        session.add(commit)
    
    session.commit()
    
    # Queue event for async processing
    # This is the key integration point!
    queue_event(event_id)
    
    logger.info(f"Webhook processed: event_id={event_id}, type={event_type}")
    
    return event_id
