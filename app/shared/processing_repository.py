"""Processing Repository for database operations during event processing."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import update, and_
from app.shared.models import Event, Commit, AISummary, Branch
from app.shared.logging_config import get_logger

logger = get_logger("processing_repository")


class ProcessingRepository:
    """
    Repository for database operations during event processing.
    
    Handles:
    - Event retrieval and status updates
    - Commit loading and status updates
    - AI summary persistence
    """

    def __init__(self, session: Session):
        self.session = session

    def get_event(self, event_id: int) -> Optional[Event]:
        """
        Fetch an event by ID.
        
        Args:
            event_id: The database ID of the event.
            
        Returns:
            Event object or None if not found.
        """
        event = self.session.query(Event).filter(Event.id == event_id).first()
        
        if event:
            logger.debug(f"Fetched event {event_id} with type {event.event_type}")
        
        return event

    def get_unprocessed_commits_for_event(self, event_id: int) -> List[Commit]:
        """
        Fetch all unprocessed commits for an event.

        Args:
            event_id: The database ID of the event.

        Returns:
            List of unprocessed Commit objects.
        """
        # Get event to find associated branch
        event = self.get_event(event_id)
        if not event or not event.branch_id:
            logger.debug(f"Event {event_id} has no branch, no commits to process")
            return []
        
        # Get commits through branch relationship
        commits = (
            self.session.query(Commit)
            .filter(
                and_(
                    Commit.branch_id == event.branch_id,
                    Commit.processed == False,
                )
            )
            .all()
        )

        logger.debug(f"Found {len(commits)} unprocessed commits for event {event_id}")
        return commits

    def get_commits_by_ids(self, commit_ids: List[int]) -> List[Commit]:
        """
        Fetch commits by their database IDs.
        
        Args:
            commit_ids: List of commit database IDs.
            
        Returns:
            List of Commit objects.
        """
        commits = (
            self.session.query(Commit)
            .filter(Commit.id.in_(commit_ids))
            .all()
        )
        return commits

    def mark_commits_as_processed(self, commit_ids: List[int]) -> int:
        """
        Mark commits as processed.
        
        Args:
            commit_ids: List of commit database IDs to mark as processed.
            
        Returns:
            Number of commits updated.
        """
        if not commit_ids:
            return 0
            
        result = (
            self.session.query(Commit)
            .filter(Commit.id.in_(commit_ids))
            .update(
                {"processed": True},
                synchronize_session=False,
            )
        )
        
        logger.debug(f"Marked {result} commits as processed")
        return result

    def mark_event_as_processed(self, event_id: int) -> None:
        """
        Mark an event as successfully processed.
        
        Args:
            event_id: The database ID of the event.
        """
        event = self.session.query(Event).filter(Event.id == event_id).first()
        if event:
            event.processed = True
            event.processing_error = None
            logger.debug(f"Marked event {event_id} as processed")

    def mark_event_as_failed(self, event_id: int, error_message: str) -> None:
        """
        Mark an event as failed with an error message.
        
        Args:
            event_id: The database ID of the event.
            error_message: The error message to store.
        """
        event = self.session.query(Event).filter(Event.id == event_id).first()
        if event:
            event.processing_error = error_message
            event.retry_count = (event.retry_count or 0) + 1
            logger.error(f"Marked event {event_id} as failed: {error_message}")

    def save_ai_summary(self, summary_data: Dict[str, Any]) -> AISummary:
        """
        Save an AI summary to the database.
        
        Args:
            summary_data: Dictionary containing summary data.
                Expected keys: jira_issue, summary_input_json, commit_count,
                              time_range_start, time_range_end, authors
                              
        Returns:
            The created AISummary object.
        """
        ai_summary = AISummary(
            jira_issue=summary_data["jira_issue"],
            summary_input_json=summary_data["summary_input_json"],
            commit_count=summary_data.get("commit_count"),
            time_range_start=summary_data.get("time_range_start"),
            time_range_end=summary_data.get("time_range_end"),
            authors=summary_data.get("authors"),
        )
        
        self.session.add(ai_summary)
        logger.info(
            f"Created AI summary for Jira issue {summary_data['jira_issue']} "
            f"with {summary_data.get('commit_count', 0)} commits"
        )
        
        return ai_summary

    def get_pending_ai_summaries(self, limit: int = 100) -> List[AISummary]:
        """
        Fetch AI summaries that haven't been processed yet.
        
        This will be used by the future Jira integration layer.
        
        Args:
            limit: Maximum number of summaries to return.
            
        Returns:
            List of unprocessed AISummary objects.
        """
        summaries = (
            self.session.query(AISummary)
            .filter(AISummary.processed == False)
            .order_by(AISummary.created_at)
            .limit(limit)
            .all()
        )
        return summaries

    def mark_ai_summary_as_processed(
        self, summary_id: int, jira_comment_id: Optional[int] = None
    ) -> None:
        """
        Mark an AI summary as processed.
        
        This will be used by the future Jira integration layer.
        
        Args:
            summary_id: The database ID of the AI summary.
            jira_comment_id: Optional ID of the posted Jira comment.
        """
        summary = self.session.query(AISummary).filter(AISummary.id == summary_id).first()
        if summary:
            summary.processed = True
            summary.processed_at = datetime.utcnow()
            if jira_comment_id is not None:
                summary.jira_comment_id = jira_comment_id
            logger.debug(f"Marked AI summary {summary_id} as processed")

    def get_commit_dedup_key(self, commit_hash: str, branch: str) -> str:
        """
        Generate a deduplication key for a commit.
        
        Args:
            commit_hash: Git commit hash.
            branch: Branch name.
            
        Returns:
            Deduplication key string.
        """
        return f"{commit_hash}:{branch}"

    def is_commit_processed(self, commit_hash: str, branch: str) -> bool:
        """
        Check if a commit has already been processed.
        
        Args:
            commit_hash: Git commit hash.
            branch: Branch name.

        Returns:
            True if commit was already processed.
        """
        # Get branch object by name
        branch_obj = self.session.query(Branch).filter(Branch.name == branch).first()
        if not branch_obj:
            return False
            
        existing = (
            self.session.query(Commit)
            .filter(
                and_(
                    Commit.commit_hash == commit_hash,
                    Commit.branch_id == branch_obj.id,
                    Commit.processed == True,
                )
            )
            .first()
        )
        return existing is not None

    def flush(self) -> None:
        """Flush pending changes to the database."""
        self.session.flush()

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()
