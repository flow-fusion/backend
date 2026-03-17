"""Tests for webhook integration and worker modules."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from app.models import Commit
from app.processing.webhook_integration import WebhookIntegrationService, queue_event
from app.workers.worker import Worker, process_event_job, enqueue_event
from app.processing.commit_aggregator import CommitAggregator
from app.processing.ai_summary_builder import AISummaryBuilder
from app.repositories.processing_repository import ProcessingRepository


# =============================================================================
# WebhookIntegrationService Tests
# =============================================================================

class TestWebhookIntegrationService:
    """Tests for WebhookIntegrationService."""

    @patch("app.processing.webhook_integration.EventQueueService")
    def test_queue_event_for_processing_success(self, mock_queue_service_class):
        """Test successful event queuing from webhook."""
        mock_queue_service = Mock()
        mock_queue_service.push_event.return_value = True
        mock_queue_service_class.return_value = mock_queue_service

        service = WebhookIntegrationService()
        result = service.queue_event_for_processing(42)

        assert result is True
        mock_queue_service.push_event.assert_called_once_with(42)

    @patch("app.processing.webhook_integration.EventQueueService")
    def test_queue_event_for_processing_duplicate(self, mock_queue_service_class):
        """Test queuing duplicate event."""
        mock_queue_service = Mock()
        mock_queue_service.push_event.return_value = False
        mock_queue_service_class.return_value = mock_queue_service

        service = WebhookIntegrationService()
        result = service.queue_event_for_processing(42)

        assert result is False

    @patch("app.processing.webhook_integration.EventQueueService")
    def test_get_queue_status(self, mock_queue_service_class):
        """Test getting queue status."""
        mock_queue_service = Mock()
        mock_queue_service.get_queue_stats.return_value = {
            "main_queue_length": 5,
            "retry_queue_length": 2,
        }
        mock_queue_service_class.return_value = mock_queue_service

        service = WebhookIntegrationService()
        stats = service.get_queue_status()

        assert "main_queue_length" in stats
        assert "retry_queue_length" in stats

    @patch("app.processing.webhook_integration.EventQueueService")
    def test_queue_event_convenience_function(self, mock_queue_service_class):
        """Test convenience queue_event function."""
        mock_queue_service = Mock()
        mock_queue_service.push_event.return_value = True
        mock_queue_service_class.return_value = mock_queue_service

        result = queue_event(42)

        assert result is True


# =============================================================================
# Worker Tests
# =============================================================================

class TestWorker:
    """Tests for Worker class."""

    @patch("app.workers.worker.init_db")
    @patch("app.workers.worker.EventQueueService")
    @patch("app.workers.worker.EventProcessor")
    def test_worker_initialize(self, mock_processor_class, mock_queue_service_class, mock_init_db):
        """Test worker initialization."""
        worker = Worker(use_rq=False)
        worker.initialize()

        mock_init_db.assert_called_once()
        mock_queue_service_class.assert_called_once()
        mock_processor_class.assert_called_once()

        assert worker.event_processor is not None
        assert worker.queue_service is not None

    @patch("app.workers.worker.init_db")
    @patch("app.workers.worker.EventQueueService")
    @patch("app.workers.worker.EventProcessor")
    def test_worker_stop(self, mock_processor_class, mock_queue_service_class, mock_init_db):
        """Test worker stop."""
        worker = Worker(use_rq=False)
        worker._running = True

        worker.stop()

        assert worker._running is False

    @patch("app.workers.worker.init_db")
    @patch("app.workers.worker.EventQueueService")
    @patch("app.workers.worker.EventProcessor")
    def test_worker_direct_mode(self, mock_processor_class, mock_queue_service_class, mock_init_db):
        """Test worker in direct mode."""
        mock_processor = Mock()
        mock_processor_class.return_value = mock_processor

        worker = Worker(use_rq=False)
        worker.initialize()

        # Verify initialization
        assert worker.event_processor is not None
        assert worker.queue_service is not None
        assert worker._running is False


class TestWorkerRQMode:
    """Tests for RQ mode worker."""

    @patch("app.workers.worker.init_db")
    @patch("app.workers.worker.EventQueueService")
    @patch("app.workers.worker.EventProcessor")
    def test_worker_rq_mode_initialization(
        self, mock_processor_class, mock_queue_service_class, mock_init_db
    ):
        """Test worker in RQ mode initialization."""
        worker = Worker(use_rq=True)
        worker.initialize()

        # Verify initialization
        assert worker.event_processor is not None
        assert worker.queue_service is not None
        assert worker.use_rq is True


class TestProcessEventJob:
    """Tests for process_event_job RQ job function."""

    @patch("app.workers.worker.EventProcessor")
    def test_process_event_job_success(self, mock_processor_class):
        """Test successful event processing job."""
        mock_processor = Mock()
        mock_processor.process_event.return_value = True
        mock_processor_class.return_value = mock_processor

        result = process_event_job(42)

        assert result is True
        mock_processor.process_event.assert_called_once_with(42)

    @patch("app.workers.worker.EventProcessor")
    def test_process_event_job_failure(self, mock_processor_class):
        """Test failed event processing job."""
        mock_processor = Mock()
        mock_processor.process_event.side_effect = Exception("Processing failed")
        mock_processor_class.return_value = mock_processor

        with pytest.raises(Exception):
            process_event_job(42)


class TestEnqueueEvent:
    """Tests for enqueue_event function."""

    @patch("app.workers.worker.redis.Redis")
    @patch("app.workers.worker.Queue")
    def test_enqueue_event(self, mock_queue_class, mock_redis_class):
        """Test enqueueing event for processing."""
        mock_queue = Mock()
        mock_job = Mock()
        mock_job.id = "job-123"
        mock_queue.enqueue.return_value = mock_job
        mock_queue_class.return_value = mock_queue

        with patch("app.workers.worker.Connection"):
            job_id = enqueue_event(42)

        assert job_id == "job-123"
        mock_queue.enqueue.assert_called_once()


# =============================================================================
# EventQueueService Additional Tests
# =============================================================================

class TestEventQueueServiceAdditional:
    """Additional tests for EventQueueService."""

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_mark_event_processed(self, mock_redis_class):
        """Test marking event as processed."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis

        from app.processing.event_queue_service import EventQueueService
        service = EventQueueService()
        service.mark_event_processed(42)

        mock_redis.srem.assert_called_once()
        mock_redis.sadd.assert_called_once()
        mock_redis.expire.assert_called_once()

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_process_scheduled_retries(self, mock_redis_class):
        """Test processing scheduled retries."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.zrangebyscore.return_value = ["1", "2", "3"]
        mock_redis.rpush.return_value = 3

        from app.processing.event_queue_service import EventQueueService
        service = EventQueueService()
        result = service.process_scheduled_retries()

        assert result == 3
        mock_redis.zrem.assert_called_once()
        mock_redis.rpush.assert_called_once()

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_process_scheduled_retries_empty(self, mock_redis_class):
        """Test processing scheduled retries when none due."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.zrangebyscore.return_value = []

        from app.processing.event_queue_service import EventQueueService
        service = EventQueueService()
        result = service.process_scheduled_retries()

        assert result == 0

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_is_event_processed_true(self, mock_redis_class):
        """Test checking if event is processed (returns True)."""
        mock_redis = Mock()
        mock_redis.sismember.return_value = True
        mock_redis_class.return_value = mock_redis

        from app.processing.event_queue_service import EventQueueService
        service = EventQueueService()
        result = service.is_event_processed(42)

        assert result is True

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_is_event_processed_false(self, mock_redis_class):
        """Test checking if event is processed (returns False)."""
        mock_redis = Mock()
        mock_redis.sismember.return_value = False
        mock_redis_class.return_value = mock_redis

        from app.processing.event_queue_service import EventQueueService
        service = EventQueueService()
        result = service.is_event_processed(42)

        assert result is False

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_clear_queue(self, mock_redis_class):
        """Test clearing all queues."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis

        from app.processing.event_queue_service import EventQueueService
        service = EventQueueService()
        service.clear_queue()

        assert mock_redis.delete.call_count >= 5


# =============================================================================
# CommitAggregator Time Window Tests
# =============================================================================

class TestCommitAggregatorTimeWindow:
    """Tests for time window batching in CommitAggregator."""

    def test_apply_time_window_batching(self):
        """Test applying time window batching to commits."""
        aggregator = CommitAggregator(batch_window_minutes=30)

        now = datetime.utcnow()
        commits = [
            Commit(
                commit_id="1",
                message="Fix 1",
                branch="feature/PROJ-1",
                timestamp=now,
            ),
            Commit(
                commit_id="2",
                message="Fix 2",
                branch="feature/PROJ-1",
                timestamp=now + timedelta(minutes=10),
            ),
            Commit(
                commit_id="3",
                message="Fix 3",
                branch="feature/PROJ-1",
                timestamp=now + timedelta(minutes=20),
            ),
            Commit(
                commit_id="4",
                message="Fix 4",
                branch="feature/PROJ-1",
                timestamp=now + timedelta(minutes=50),  # New batch
            ),
        ]

        batches = aggregator.apply_time_window_batching(commits)

        # Should create 2 batches (first 3 within 30 min, last one in new batch)
        assert len(batches) == 2
        assert len(batches[0]) == 3  # First 3 commits within 30 min
        assert len(batches[1]) == 1  # Last commit in new batch

    def test_apply_time_window_batching_empty(self):
        """Test time window batching with empty commits."""
        aggregator = CommitAggregator()

        batches = aggregator.apply_time_window_batching([])

        assert batches == []

    def test_apply_time_window_batching_single_commit(self):
        """Test time window batching with single commit."""
        aggregator = CommitAggregator()

        now = datetime.utcnow()
        commits = [
            Commit(
                commit_id="1",
                message="Fix 1",
                branch="feature/PROJ-1",
                timestamp=now,
            ),
        ]

        batches = aggregator.apply_time_window_batching(commits)

        assert len(batches) == 1
        assert len(batches[0]) == 1

    def test_apply_time_window_batching_no_timestamps(self):
        """Test time window batching when commits have no timestamps."""
        aggregator = CommitAggregator()

        commits = [
            Commit(commit_id="1", message="Fix 1", branch="feature/PROJ-1", timestamp=None),
            Commit(commit_id="2", message="Fix 2", branch="feature/PROJ-1", timestamp=None),
        ]

        batches = aggregator.apply_time_window_batching(commits)

        # When no timestamps, both get datetime.min and are grouped together
        assert len(batches) == 1
        assert len(batches[0]) == 2


# =============================================================================
# AISummaryBuilder Additional Tests
# =============================================================================

class TestAISummaryBuilderAdditional:
    """Additional tests for AISummaryBuilder."""

    def test_build_for_batch(self):
        """Test building summaries for multiple batches."""
        builder = AISummaryBuilder()

        now = datetime.utcnow()
        batch1 = [
            Commit(commit_id="1", message="Fix 1", branch="feature/PROJ-1", timestamp=now),
        ]
        batch2 = [
            Commit(commit_id="2", message="Fix 2", branch="feature/PROJ-1", timestamp=now),
        ]

        summaries = builder.build_for_batch("PROJ-1", [batch1, batch2])

        assert len(summaries) == 2
        assert summaries[0]["batch_index"] == 0
        assert summaries[1]["batch_index"] == 1
        assert summaries[0]["total_batches"] == 2

    def test_build_for_batch_empty(self):
        """Test building summaries for empty batches."""
        builder = AISummaryBuilder()

        summaries = builder.build_for_batch("PROJ-1", [])

        assert summaries == []

    def test_build_for_batch_with_empty_batch(self):
        """Test building summaries with empty batch in list."""
        builder = AISummaryBuilder()

        now = datetime.utcnow()
        batch1 = [
            Commit(commit_id="1", message="Fix 1", branch="feature/PROJ-1", timestamp=now),
        ]

        summaries = builder.build_for_batch("PROJ-1", [batch1, []])

        assert len(summaries) == 1  # Empty batch skipped


# =============================================================================
# ProcessingRepository Additional Tests
# =============================================================================

class TestProcessingRepositoryAdditional:
    """Additional tests for ProcessingRepository."""

    def test_mark_event_as_failed(self):
        """Test marking event as failed."""
        mock_session = Mock()
        mock_query = Mock()
        mock_filter = Mock()
        mock_event = Mock()
        mock_event.retry_count = 0

        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = mock_event

        from app.repositories.processing_repository import ProcessingRepository
        repo = ProcessingRepository(mock_session)
        repo.mark_event_as_failed(42, "Test error")

        assert mock_event.processing_error == "Test error"
        assert mock_event.retry_count == 1

    def test_get_pending_ai_summaries(self):
        """Test getting pending AI summaries."""
        mock_session = Mock()
        mock_query = Mock()
        mock_filter = Mock()
        mock_order = Mock()
        mock_limit = Mock()

        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.order_by.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        mock_limit.all.return_value = [Mock(), Mock()]

        from app.repositories.processing_repository import ProcessingRepository
        repo = ProcessingRepository(mock_session)
        result = repo.get_pending_ai_summaries(limit=100)

        assert len(result) == 2

    def test_mark_ai_summary_as_processed(self):
        """Test marking AI summary as processed."""
        mock_session = Mock()
        mock_query = Mock()
        mock_filter = Mock()
        mock_summary = Mock()

        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = mock_summary

        from app.repositories.processing_repository import ProcessingRepository
        repo = ProcessingRepository(mock_session)
        repo.mark_ai_summary_as_processed(42, jira_comment_id=123)

        assert mock_summary.processed is True
        assert mock_summary.processed_at is not None
        assert mock_summary.jira_comment_id == 123

    def test_flush_commit_rollback(self):
        """Test flush, commit, and rollback methods."""
        mock_session = Mock()

        from app.repositories.processing_repository import ProcessingRepository
        repo = ProcessingRepository(mock_session)

        repo.flush()
        repo.commit()
        repo.rollback()

        mock_session.flush.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_called_once()
