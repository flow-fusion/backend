"""Processing module initialization."""

from app.processing.event_queue_service import EventQueueService
from app.processing.event_processor import EventProcessor
from app.processing.commit_aggregator import CommitAggregator
from app.processing.ai_summary_builder import AISummaryBuilder

__all__ = [
    "EventQueueService",
    "EventProcessor",
    "CommitAggregator",
    "AISummaryBuilder",
]
