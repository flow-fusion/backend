"""GitLab webhook payload parser.

This module parses raw GitLab webhook payloads into normalized internal structures.
It is part of the WEBHOOK LAYER and is not used by the processing layer.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from app.webhooks.models import NormalizedEvent, GitLabCommit
from app.shared.utils.jira_key_extractor import JiraKeyExtractor

logger = logging.getLogger(__name__)


class GitLabParser:
    """
    Parser for GitLab webhook payloads.
    
    This class handles parsing and normalization of different GitLab webhook
    event types (Push Hook, Merge Request Hook) into a consistent internal format.
    
    The parser performs the following steps:
    1. Validates the payload structure
    2. Detects the event type from the X-Gitlab-Event header
    3. Extracts relevant fields based on event type
    4. Extracts branch name from Git ref
    5. Extracts Jira issue key from branch name
    6. Normalizes commits data
    7. Returns a NormalizedEvent instance
    """

    # Supported event types from GitLab
    PUSH_EVENT = "Push Hook"
    MERGE_REQUEST_EVENT = "Merge Request Hook"

    # Normalized event types for merge requests
    MR_ACTION_OPENED = "mr_opened"
    MR_ACTION_MERGED = "mr_merged"
    MR_ACTION_UPDATED = "mr_updated"
    MR_ACTION_CLOSED = "mr_closed"
    MR_ACTION_APPROVED = "mr_approved"
    MR_ACTION_UNAPPROVED = "mr_unapproved"

    def __init__(self):
        """Initialize the GitLab parser."""
        self.jira_extractor = JiraKeyExtractor()

    def parse(
        self,
        payload: dict[str, Any],
        event_type_header: str,
    ) -> Optional[NormalizedEvent]:
        """
        Parse a GitLab webhook payload into a normalized event.
        
        Args:
            payload: Raw JSON payload from GitLab webhook
            event_type_header: Value of X-Gitlab-Event header
            
        Returns:
            NormalizedEvent if parsing succeeds, None if event type is unknown
            
        Raises:
            ValueError: If payload is invalid or missing required fields
        """
        if not payload:
            raise ValueError("Empty payload received")

        if not event_type_header:
            raise ValueError("Event type header is missing")

        # Route to appropriate parser based on event type
        if event_type_header == self.PUSH_EVENT:
            return self._parse_push_event(payload)
        elif event_type_header == self.MERGE_REQUEST_EVENT:
            return self._parse_merge_request_event(payload)
        else:
            logger.warning(f"Unknown event type received: {event_type_header}")
            return None

    def _parse_push_event(self, payload: dict[str, Any]) -> NormalizedEvent:
        """
        Parse a GitLab Push Hook event.
        
        Args:
            payload: Raw JSON payload from GitLab
            
        Returns:
            NormalizedEvent with push event data
            
        Raises:
            ValueError: If required fields are missing
        """
        # Extract required fields
        ref = self._get_field(payload, "ref", str)
        repository_data = self._get_field(payload, "repository", dict)
        repository_name = self._get_field(repository_data, "name", str)

        # Extract optional fields
        user_name = payload.get("user_name")
        commits_data = payload.get("commits", [])

        # Extract branch name from ref
        branch_name = self.jira_extractor.extract_branch_name_from_ref(ref)

        # Extract Jira issue key from branch name
        jira_issue = self.jira_extractor.extract(branch_name)

        # Parse commits
        commits = self._parse_commits(commits_data)

        # Log the event
        logger.info(
            f"Received push event | repo={repository_name} | "
            f"branch={branch_name} | jira_issue={jira_issue} | "
            f"commits={len(commits)}"
        )

        return NormalizedEvent(
            event_type="push",
            repository=repository_name,
            branch=branch_name,
            jira_issue=jira_issue,
            author=user_name,
            commits=commits,
            raw_payload=payload,
        )

    def _parse_merge_request_event(
        self,
        payload: dict[str, Any],
    ) -> NormalizedEvent:
        """
        Parse a GitLab Merge Request Hook event.
        
        Args:
            payload: Raw JSON payload from GitLab
            
        Returns:
            NormalizedEvent with merge request event data
            
        Raises:
            ValueError: If required fields are missing
        """
        # Extract object_attributes for MR details
        object_attributes = self._get_field(payload, "object_attributes", dict)

        # Extract action and map to normalized event type
        action = self._get_field(object_attributes, "action", str)
        event_type = self._map_mr_action_to_event_type(action)

        # Extract branch information
        source_branch = self._get_field(object_attributes, "source_branch", str)

        # Extract repository information
        repository_data = self._get_field(payload, "repository", dict)
        repository_name = self._get_field(repository_data, "name", str)

        # Extract Jira issue key from source branch
        jira_issue = self.jira_extractor.extract(source_branch)

        # Extract author
        user_data = payload.get("user", {})
        author = user_data.get("name") if user_data else None

        # Extract MR ID and title
        mr_id = object_attributes.get("iid")
        mr_title = object_attributes.get("title")

        # Parse commits if available
        commits_data = payload.get("commits", [])
        commits = self._parse_commits(commits_data)

        # Log the event
        logger.info(
            f"Received merge request event | action={action} | "
            f"repo={repository_name} | branch={source_branch} | "
            f"jira_issue={jira_issue} | mr_id={mr_id}"
        )

        return NormalizedEvent(
            event_type=event_type,
            repository=repository_name,
            branch=source_branch,
            jira_issue=jira_issue,
            author=author,
            commits=commits,
            raw_payload=payload,
            mr_id=mr_id,
            mr_title=mr_title,
            mr_action=action,
        )

    def _map_mr_action_to_event_type(self, action: str) -> str:
        """
        Map GitLab MR action to normalized event type.
        
        Args:
            action: Raw action from GitLab (open, merge, update, etc.)
            
        Returns:
            Normalized event type string
        """
        mapping = {
            "open": self.MR_ACTION_OPENED,
            "merge": self.MR_ACTION_MERGED,
            "update": self.MR_ACTION_UPDATED,
            "close": self.MR_ACTION_CLOSED,
            "approved": self.MR_ACTION_APPROVED,
            "unapproved": self.MR_ACTION_UNAPPROVED,
        }
        return mapping.get(action, f"mr_{action}")

    def _parse_commits(self, commits_data: list[Any]) -> list[GitLabCommit]:
        """
        Parse commit data from GitLab payload.
        
        Args:
            commits_data: List of commit dictionaries from GitLab
            
        Returns:
            List of GitLabCommit instances
        """
        commits = []
        for commit_data in commits_data:
            try:
                commit = self._parse_single_commit(commit_data)
                if commit:
                    commits.append(commit)
            except (ValueError, KeyError) as e:
                logger.warning(f"Failed to parse commit: {e}")
                continue
        return commits

    def _parse_single_commit(
        self,
        commit_data: dict[str, Any],
    ) -> Optional[GitLabCommit]:
        """
        Parse a single commit from GitLab payload.
        
        Args:
            commit_data: Commit dictionary from GitLab
            
        Returns:
            GitLabCommit instance, or None if parsing fails
        """
        commit_id = self._get_field(commit_data, "id", str)
        message = self._get_field(commit_data, "message", str)

        # Parse timestamp
        timestamp_raw = self._get_field(commit_data, "timestamp", str)
        timestamp = self._parse_timestamp(timestamp_raw)

        # Parse author
        author_data = commit_data.get("author", {})
        author_name = author_data.get("name", "") if author_data else ""
        author_email = author_data.get("email", "") if author_data else ""

        return GitLabCommit(
            commit_id=commit_id,
            message=message,
            timestamp=timestamp,
            author_name=author_name,
            author_email=author_email,
        )

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """
        Parse a timestamp string from GitLab into a datetime object.
        
        GitLab typically sends timestamps in ISO 8601 format.
        
        Args:
            timestamp_str: Timestamp string from GitLab
            
        Returns:
            Parsed datetime object
        """
        # Try ISO format first (most common)
        try:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        # Try common alternative formats
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue

        # Fallback to current time if parsing fails
        logger.warning(f"Could not parse timestamp: {timestamp_str}, using current time")
        return datetime.now()

    def _get_field(
        self,
        data: dict[str, Any],
        field: str,
        expected_type: type,
    ) -> Any:
        """
        Get a field from a dictionary with type validation.
        
        Args:
            data: Dictionary to extract field from
            field: Field name
            expected_type: Expected type of the field value
            
        Returns:
            Field value if found and valid
            
        Raises:
            ValueError: If field is missing or has wrong type
        """
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

        value = data[field]
        if not isinstance(value, expected_type):
            raise ValueError(
                f"Field '{field}' has wrong type: expected {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )

        return value
