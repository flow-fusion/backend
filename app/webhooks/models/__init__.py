"""Webhook-specific data models.

These are NOT SQLAlchemy ORM models - they are simple dataclasses
used for parsing and validating webhook payloads.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class GitLabCommit:
    """
    Represents a single commit from a GitLab webhook payload.
    
    This is a transient data structure used during webhook parsing.
    Not persisted to database directly.
    """
    commit_id: str
    message: str
    timestamp: datetime
    author_name: str
    author_email: str = ""


@dataclass
class NormalizedEvent:
    """
    Normalized internal event representation.
    
    This structure provides a consistent format for all GitLab webhook events,
    regardless of the original payload structure. Used by WebhookService to
    store data in the database.
    
    Attributes:
        event_type: Normalized event type (push, mr_opened, mr_merged, etc.)
        repository: Repository name
        branch: Branch name (without refs/heads/ prefix)
        jira_issue: Extracted Jira issue key, or None
        author: Event author/committer name
        commits: List of commits associated with this event
        raw_payload: Original raw payload for reference
        mr_id: GitLab merge request ID (for MR events)
        mr_title: Merge request title (for MR events)
        mr_action: Original MR action from GitLab
    """
    event_type: str
    repository: str
    branch: Optional[str]
    jira_issue: Optional[str]
    author: Optional[str]
    commits: list[GitLabCommit] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    mr_id: Optional[int] = None
    mr_title: Optional[str] = None
    mr_action: Optional[str] = None
