"""Webhook layer repositories.

These repositories handle database operations specific to the webhook layer.
They are separate from the processing layer repositories.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.shared.models import Branch, Commit, Event, MergeRequest, Repository
from app.webhooks.models import NormalizedEvent, GitLabCommit


class WebhookRepository:
    """
    Repository for storing webhook events and related data.
    
    This is the integration point between the webhook layer and the database.
    It converts NormalizedEvent into ORM models and persists them.
    """

    def __init__(self, db: Session):
        self.db = db

    def store_event(self, normalized_event: NormalizedEvent) -> Event:
        """
        Store a normalized webhook event and all related data.
        
        This method performs the following steps:
        1. Get or create repository
        2. Get or create branch (with Jira issue)
        3. Store commits
        4. Store merge request (if applicable)
        5. Store the event
        
        Args:
            normalized_event: Parsed and normalized webhook event
            
        Returns:
            The created Event ORM instance
        """
        # Step 1: Get or create repository
        repository = self._get_or_create_repository(normalized_event.repository)

        # Step 2: Get or create branch
        branch_id = None
        if normalized_event.branch:
            branch = self._get_or_create_branch(
                branch_name=normalized_event.branch,
                repository_id=repository.id,
                jira_issue=normalized_event.jira_issue,
            )
            branch_id = branch.id

            # Step 3: Store commits
            if normalized_event.commits:
                self._store_commits(branch_id, normalized_event.commits)

        # Step 4: Store merge request (if applicable)
        if normalized_event.mr_id and branch_id:
            self._get_or_create_merge_request(
                branch_id=branch_id,
                mr_id=normalized_event.mr_id,
                status=normalized_event.event_type,
                title=normalized_event.mr_title,
                merged_at=datetime.now() if normalized_event.event_type == "mr_merged" else None,
            )

        # Step 5: Store the event
        db_event = self._create_event(
            event_type=normalized_event.event_type,
            repository=normalized_event.repository,
            payload_json=normalized_event.raw_payload,
            branch=normalized_event.branch,
            jira_issue=normalized_event.jira_issue,
            author=normalized_event.author,
            branch_id=branch_id,
        )

        # Commit all changes
        self.db.commit()

        return db_event

    def _get_or_create_repository(self, name: str) -> Repository:
        """Get existing repository or create new one."""
        repo = self.db.query(Repository).filter(Repository.name == name).first()
        if repo:
            return repo

        repo = Repository(name=name)
        self.db.add(repo)
        self.db.flush()
        return repo

    def _get_or_create_branch(
        self,
        branch_name: str,
        repository_id: int,
        jira_issue: Optional[str] = None,
    ) -> Branch:
        """Get existing branch or create new one."""
        branch = (
            self.db.query(Branch)
            .filter(
                Branch.name == branch_name,
                Branch.repository_id == repository_id,
            )
            .first()
        )
        if branch:
            # Update Jira issue if provided
            if jira_issue and not branch.jira_issue:
                branch.jira_issue = jira_issue
            return branch

        branch = Branch(
            name=branch_name,
            repository_id=repository_id,
            jira_issue=jira_issue,
        )
        self.db.add(branch)
        self.db.flush()
        return branch

    def _store_commits(self, branch_id: int, commits: list[GitLabCommit]) -> None:
        """Store multiple commits for a branch."""
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Storing {len(commits)} commits for branch {branch_id}")
        
        for commit_data in commits:
            commit = Commit(
                commit_hash=commit_data.commit_id,
                branch_id=branch_id,
                author=commit_data.author_name,
                message=commit_data.message,
                timestamp=commit_data.timestamp,
            )
            self.db.add(commit)
            logger.debug(f"Added commit {commit_data.commit_id[:8]}")
        
        self.db.flush()
        logger.info(f"Stored {len(commits)} commits successfully")

    def _get_or_create_merge_request(
        self,
        branch_id: int,
        mr_id: int,
        status: str,
        title: Optional[str] = None,
        merged_at: Optional[datetime] = None,
    ) -> MergeRequest:
        """Get existing MR or create new one."""
        mr = (
            self.db.query(MergeRequest)
            .filter(
                MergeRequest.mr_id == mr_id,
                MergeRequest.branch_id == branch_id,
            )
            .first()
        )
        if mr:
            # Update status
            mr.status = status
            if merged_at:
                mr.merged_at = merged_at
            return mr

        mr = MergeRequest(
            branch_id=branch_id,
            mr_id=mr_id,
            status=status,
            title=title,
            merged_at=merged_at,
        )
        self.db.add(mr)
        self.db.flush()
        return mr

    def _create_event(
        self,
        event_type: str,
        repository: str,
        payload_json: dict[str, Any],
        branch: Optional[str] = None,
        jira_issue: Optional[str] = None,
        author: Optional[str] = None,
        branch_id: Optional[int] = None,
    ) -> Event:
        """Create a new event."""
        import json
        event = Event(
            event_type=event_type,
            repository=repository,
            payload_json=json.dumps(payload_json),
            branch=branch,
            jira_issue=jira_issue,
            author=author,
            branch_id=branch_id,
        )
        self.db.add(event)
        self.db.flush()
        return event
