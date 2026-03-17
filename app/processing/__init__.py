"""Processing layer module.

This module contains the BACKEND PROCESSING LAYER which is responsible for:
1. Processing events from the Redis queue
2. Loading Git context from GitLab API
3. Building AI summaries
4. Storing AI-ready data

This is SEPARATE from the webhook layer which only receives and stores events.
"""

from app.processing.event_queue_service import EventQueueService
from app.processing.event_processor import EventProcessor
from app.processing.commit_aggregator import CommitAggregator
from app.processing.ai_summary_builder import AISummaryBuilder
from app.processing.git_context_service import GitContextService, GitContext, DiffSummary, MergeRequestInfo

__all__ = [
    "EventQueueService",
    "EventProcessor",
    "CommitAggregator",
    "AISummaryBuilder",
    "GitContextService",
    "GitContext",
    "DiffSummary",
    "MergeRequestInfo",
]
