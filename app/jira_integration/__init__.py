"""Jira Integration Layer.

This module provides integration with Jira API for:
- Posting AI-generated comments to Jira issues
- Transitioning Jira issues based on MR state
- Logging work entries

This is the FINAL layer that completes the pipeline:
GitLab → Webhook → Processing → AI Summary → Jira
"""

from app.jira_integration.jira_client import JiraClient, find_transition_id
from app.jira_integration.mr_processor import (
    MRProcessor,
    MergeRequest,
    Commit,
    MRState,
)
from app.jira_integration.config import JiraConfig

__all__ = [
    "JiraClient",
    "find_transition_id",
    "MRProcessor",
    "MergeRequest",
    "Commit",
    "MRState",
    "JiraConfig",
]
