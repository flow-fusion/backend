"""Event Processor for processing events from the queue."""

import asyncio
from typing import Optional, Set
from sqlalchemy.orm import Session
from app.core.database import session_scope
from app.core.logging_config import get_logger
from app.processing.event_queue_service import EventQueueService
from app.processing.commit_aggregator import CommitAggregator
from app.processing.ai_summary_builder import AISummaryBuilder
from app.processing.git_context_service import GitContextService, GitContext
from app.repositories.processing_repository import ProcessingRepository
from app.models import Event

logger = get_logger("event_processor")


class EventProcessor:
    """
    Worker that processes events from the Redis queue.

    Responsibilities:
    - Pull events from queue
    - Deduplicate events
    - Group commits by Jira issue
    - Create AI summaries with Git context
    - Mark events and commits as processed
    - Handle errors and retries
    """

    def __init__(
        self,
        queue_service: Optional[EventQueueService] = None,
        commit_aggregator: Optional[CommitAggregator] = None,
        ai_summary_builder: Optional[AISummaryBuilder] = None,
        git_context_service: Optional[GitContextService] = None,
    ):
        self.queue_service = queue_service or EventQueueService()
        self.commit_aggregator = commit_aggregator or CommitAggregator()
        self.ai_summary_builder = ai_summary_builder or AISummaryBuilder()
        self.git_context_service = git_context_service
        self._processed_commit_hashes: Set[str] = set()

    def process_event(self, event_id: int) -> bool:
        """
        Process a single event.
        
        Args:
            event_id: The database ID of the event to process.
            
        Returns:
            True if processing succeeded, False otherwise.
        """
        logger.info(f"Processing event id={event_id}")
        
        try:
            with session_scope() as session:
                repo = ProcessingRepository(session)
                
                # Fetch event
                event = repo.get_event(event_id)
                if not event:
                    logger.error(f"Event {event_id} not found in database")
                    return False
                
                # Check if already processed
                if event.processed:
                    logger.info(f"Event {event_id} already processed, skipping")
                    return True
                
                # Check event type - only process push events for now
                if event.event_type != "push":
                    logger.info(f"Skipping event {event_id} with type {event.event_type}")
                    repo.mark_event_as_processed(event_id)
                    return True
                
                # Get unprocessed commits
                commits = repo.get_unprocessed_commits_for_event(event_id)
                logger.info(f"Found {len(commits)} commits for event {event_id}")
                
                if not commits:
                    logger.info(f"No unprocessed commits for event {event_id}")
                    repo.mark_event_as_processed(event_id)
                    self.queue_service.mark_event_processed(event_id)
                    return True
                
                # Filter out already processed commits (in-memory dedup)
                unprocessed_commits = self._filter_truly_unprocessed(commits, repo)
                
                if not unprocessed_commits:
                    logger.info(f"All commits for event {event_id} already processed")
                    repo.mark_event_as_processed(event_id)
                    self.queue_service.mark_event_processed(event_id)
                    return True
                
                # Group commits by Jira issue
                grouped = self.commit_aggregator.group_by_jira_issue(unprocessed_commits)

                # Process each Jira issue group
                summaries_created = 0
                for jira_issue, issue_commits in grouped.items():
                    if jira_issue is None:
                        # Skip commits without Jira issue
                        logger.info(
                            f"Skipping {len(issue_commits)} commits without Jira issue"
                        )
                        # Still mark them as processed to avoid reprocessing
                        commit_ids = [c.id for c in issue_commits]
                        repo.mark_commits_as_processed(commit_ids)
                        continue

                    logger.info(f"Grouped under issue {jira_issue}: {len(issue_commits)} commits")

                    # Load Git context for this group of commits
                    git_context = self._load_git_context(issue_commits)

                    # Build AI summary input with Git context
                    summary_input = self.ai_summary_builder.build_summary_input(
                        jira_issue, issue_commits, git_context
                    )

                    # Save AI summary to database
                    repo.save_ai_summary({
                        "jira_issue": jira_issue,
                        "summary_input_json": summary_input,
                        "commit_count": len(issue_commits),
                        "time_range_start": summary_input["time_range"]["start"],
                        "time_range_end": summary_input["time_range"]["end"],
                        "authors": summary_input["authors"],
                    })

                    summaries_created += 1

                    # Mark commits as processed
                    commit_ids = [c.id for c in issue_commits]
                    repo.mark_commits_as_processed(commit_ids)

                    # Update in-memory cache
                    for commit in issue_commits:
                        self._processed_commit_hashes.add(
                            f"{commit.commit_id}:{commit.branch}"
                        )
                
                logger.info(
                    f"Created AI summary batch for event {event_id}: "
                    f"{summaries_created} summaries, {len(unprocessed_commits)} commits"
                )
                
                # Mark event as processed
                repo.mark_event_as_processed(event_id)
                
            # Mark as processed in queue
            self.queue_service.mark_event_processed(event_id)
            
            logger.info(f"Successfully processed event {event_id}")
            return True
            
        except Exception as e:
            logger.exception(f"Error processing event {event_id}: {str(e)}")
            self._handle_processing_error(event_id, str(e))
            return False

    def _filter_truly_unprocessed(
        self,
        commits: list,
        repo: ProcessingRepository,
    ) -> list:
        """
        Filter commits that are truly unprocessed.
        
        This performs additional deduplication beyond the database flag.
        
        Args:
            commits: List of Commit objects.
            repo: ProcessingRepository instance.
            
        Returns:
            List of truly unprocessed commits.
        """
        unprocessed = []
        
        for commit in commits:
            dedup_key = f"{commit.commit_id}:{commit.branch}"
            
            # Check in-memory cache first
            if dedup_key in self._processed_commit_hashes:
                logger.debug(f"Commit {commit.commit_id[:8]} in processed cache")
                continue
            
            # Check in database
            if repo.is_commit_processed(commit.commit_id, commit.branch):
                logger.debug(f"Commit {commit.commit_id[:8]} already processed in DB")
                self._processed_commit_hashes.add(dedup_key)
                continue
            
            unprocessed.append(commit)
        
        return unprocessed

    def _load_git_context(
        self,
        commits: list,
    ) -> Optional[GitContext]:
        """
        Load Git context for a list of commits.
        
        Args:
            commits: List of Commit objects.
            
        Returns:
            GitContext or None if loading fails or service not configured.
        """
        if not self.git_context_service:
            logger.debug("Git context service not configured, skipping Git context")
            return None
        
        if not commits:
            return None
        
        try:
            # Run async Git context loading in a sync context
            git_context = self._run_async(
                self.git_context_service.load_context(commits)
            )
            return git_context
        except Exception as e:
            logger.warning(f"Failed to load Git context (continuing without): {e}")
            return None

    def _run_async(self, coro):
        """Run an async coroutine in a sync context."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            # If loop is already running, we're in an async context
            # This shouldn't happen in the worker, but handle it gracefully
            logger.warning("Event loop is running, cannot load Git context synchronously")
            return None
        
        return loop.run_until_complete(coro)

    def _handle_processing_error(self, event_id: int, error_message: str) -> None:
        """
        Handle a processing error with retry logic.
        
        Args:
            event_id: The database ID of the failed event.
            error_message: The error message.
        """
        with session_scope() as session:
            repo = ProcessingRepository(session)
            repo.mark_event_as_failed(event_id, error_message)
            
            # Get updated retry count
            event = repo.get_event(event_id)
            retry_count = event.retry_count if event else 0
        
        # Queue for retry
        self.queue_service.retry_event(event_id, retry_count)

    def run_worker(self, poll_timeout: int = 5) -> None:
        """
        Run the worker in a continuous loop.
        
        Args:
            poll_timeout: Timeout in seconds when polling for new events.
        """
        logger.info("Starting event processor worker")
        
        while True:
            try:
                # Process scheduled retries first
                self.queue_service.process_scheduled_retries()
                
                # Pop event from queue (blocking with timeout)
                event_id = self.queue_service.pop_event(timeout=poll_timeout)
                
                if event_id is None:
                    # No events available, continue polling
                    continue
                
                # Process the event
                self.process_event(event_id)
                
            except KeyboardInterrupt:
                logger.info("Worker interrupted, shutting down")
                break
            except Exception as e:
                logger.exception(f"Worker error: {str(e)}")
                # Continue processing - don't crash the worker

    def process_single_event(self, event_id: int) -> bool:
        """
        Process a single event (for testing/manual invocation).
        
        Args:
            event_id: The database ID of the event to process.
            
        Returns:
            True if processing succeeded.
        """
        return self.process_event(event_id)
