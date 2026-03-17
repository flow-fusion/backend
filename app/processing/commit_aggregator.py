"""Commit Aggregator for grouping commits by Jira issue."""

import re
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from app.models import Commit
from app.core.config import get_settings
from app.core.logging_config import get_logger

logger = get_logger("commit_aggregator")


class CommitAggregator:
    """
    Aggregator for grouping commits by Jira issue and time window.
    
    Responsibilities:
    - Extract Jira issue keys from branch names
    - Group commits by Jira issue
    - Apply time window batching
    - Filter out processed/duplicate commits
    """

    # Pattern to match Jira issue keys in branch names
    # Examples: feature/PROJ-123-login, bugfix/ABC-456, PROJ-789-hotfix
    JIRA_ISSUE_PATTERN = re.compile(r"(?<![A-Z0-9])([A-Z]+-\d+)(?![A-Z0-9])")

    def __init__(self, batch_window_minutes: Optional[int] = None):
        settings = get_settings()
        self.batch_window_minutes = batch_window_minutes or settings.COMMIT_BATCH_WINDOW_MINUTES

    def extract_jira_issue(self, branch_name: str) -> Optional[str]:
        """
        Extract Jira issue key from a branch name.
        
        Args:
            branch_name: The Git branch name.
            
        Returns:
            Jira issue key (e.g., 'PROJ-123') or None if not found.
            
        Examples:
            >>> extract_jira_issue("feature/PROJ-123-login")
            'PROJ-123'
            >>> extract_jira_issue("main")
            None
        """
        if not branch_name:
            return None
            
        match = self.JIRA_ISSUE_PATTERN.search(branch_name)
        if match:
            issue_key = match.group(1)
            logger.debug(f"Extracted Jira issue {issue_key} from branch {branch_name}")
            return issue_key
        
        logger.debug(f"No Jira issue found in branch {branch_name}")
        return None

    def filter_unprocessed_commits(
        self,
        commits: List[Commit],
        processed_commit_hashes: set,
    ) -> List[Commit]:
        """
        Filter out commits that have already been processed.
        
        Args:
            commits: List of Commit objects to filter.
            processed_commit_hashes: Set of already processed commit hashes.
            
        Returns:
            List of unprocessed Commit objects.
        """
        unprocessed = []
        for commit in commits:
            dedup_key = f"{commit.commit_id}:{commit.branch}"
            
            if commit.commit_id in processed_commit_hashes:
                logger.debug(f"Skipping already processed commit {commit.commit_id[:8]}")
                continue
            
            if commit.processed:
                logger.debug(f"Skipping commit {commit.commit_id[:8]} marked as processed in DB")
                continue
            
            # Skip merge commits (optional, can be configured)
            if self._is_merge_commit(commit.message):
                logger.debug(f"Skipping merge commit {commit.commit_id[:8]}")
                continue
            
            # Skip commits without messages
            if not commit.message or not commit.message.strip():
                logger.debug(f"Skipping commit {commit.commit_id[:8]} without message")
                continue
            
            unprocessed.append(commit)
        
        logger.info(f"Filtered {len(commits)} commits down to {len(unprocessed)} unprocessed")
        return unprocessed

    def _is_merge_commit(self, message: Optional[str]) -> bool:
        """Check if a commit message indicates a merge commit."""
        if not message:
            return False
        return message.startswith("Merge branch") or message.startswith("Merge pull request")

    def group_by_jira_issue(
        self,
        commits: List[Commit],
    ) -> Dict[str, List[Commit]]:
        """
        Group commits by their Jira issue key.
        
        Args:
            commits: List of Commit objects to group.
            
        Returns:
            Dictionary mapping Jira issue keys to lists of commits.
            Commits without a Jira issue are grouped under None key.
        """
        grouped: Dict[str, List[Commit]] = defaultdict(list)
        
        for commit in commits:
            # Try to get Jira issue from commit's jira_issue field first
            jira_issue = commit.jira_issue
            
            # If not set, try to extract from branch name
            if not jira_issue and commit.branch:
                jira_issue = self.extract_jira_issue(commit.branch)
            
            # Group by Jira issue (or None if not found)
            grouped[jira_issue].append(commit)
        
        # Log grouping results
        for jira_issue, issue_commits in grouped.items():
            if jira_issue:
                logger.info(f"Grouped {len(issue_commits)} commits under Jira issue {jira_issue}")
            else:
                logger.info(f"Found {len(issue_commits)} commits without Jira issue")
        
        return dict(grouped)

    def apply_time_window_batching(
        self,
        commits: List[Commit],
    ) -> List[List[Commit]]:
        """
        Group commits into batches based on time windows.
        
        Commits within the same time window are grouped together
        to reduce the number of AI requests.
        
        Args:
            commits: List of Commit objects to batch.
            
        Returns:
            List of commit batches.
        """
        if not commits:
            return []
        
        # Sort commits by timestamp
        sorted_commits = sorted(
            commits,
            key=lambda c: c.timestamp or datetime.min,
        )
        
        batches: List[List[Commit]] = []
        current_batch: List[Commit] = []
        batch_start_time: Optional[datetime] = None
        
        for commit in sorted_commits:
            commit_time = commit.timestamp or datetime.utcnow()
            
            if batch_start_time is None:
                # Start new batch
                batch_start_time = commit_time
                current_batch = [commit]
            elif commit_time - batch_start_time <= timedelta(minutes=self.batch_window_minutes):
                # Add to current batch
                current_batch.append(commit)
            else:
                # Time window exceeded, start new batch
                if current_batch:
                    batches.append(current_batch)
                    logger.debug(
                        f"Created batch with {len(current_batch)} commits "
                        f"from {batch_start_time} to {current_batch[-1].timestamp}"
                    )
                batch_start_time = commit_time
                current_batch = [commit]
        
        # Don't forget the last batch
        if current_batch:
            batches.append(current_batch)
            logger.debug(f"Created final batch with {len(current_batch)} commits")
        
        logger.info(f"Created {len(batches)} batches from {len(commits)} commits")
        return batches

    def aggregate_for_event(
        self,
        commits: List[Commit],
        processed_commit_hashes: Optional[set] = None,
    ) -> Dict[str, List[Commit]]:
        """
        Full aggregation pipeline for an event's commits.
        
        Args:
            commits: List of Commit objects from an event.
            processed_commit_hashes: Optional set of already processed commit hashes.
            
        Returns:
            Dictionary mapping Jira issue keys to lists of commits.
        """
        if not commits:
            logger.debug("No commits to aggregate")
            return {}
        
        # Filter unprocessed commits
        if processed_commit_hashes:
            commits = self.filter_unprocessed_commits(commits, processed_commit_hashes)
        else:
            commits = [c for c in commits if not c.processed]
        
        if not commits:
            logger.info("All commits already processed")
            return {}
        
        # Group by Jira issue
        grouped = self.group_by_jira_issue(commits)
        
        return grouped
