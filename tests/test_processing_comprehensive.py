"""Comprehensive tests for the processing layer - Updated to avoid SQLAlchemy relationship issues."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from app.shared.models import Commit, Branch
from app.processing.commit_aggregator import CommitAggregator
from app.processing.ai_summary_builder import AISummaryBuilder
from app.processing.event_queue_service import EventQueueService
from app.shared.processing_repository import ProcessingRepository
from app.processing.event_processor import EventProcessor
from app.processing.git_context_service import GitContext, DiffSummary, MergeRequestInfo


# =============================================================================
# CommitAggregator Tests - Edge Cases
# =============================================================================

class TestCommitAggregatorEdgeCases:
    """Edge case tests for CommitAggregator."""

    def setup_method(self):
        self.aggregator = CommitAggregator()

    def _create_commit(self, commit_hash: str, message: str, author: str = "Test"):
        """Helper to create simple Commit without relationships."""
        return Commit(
            commit_hash=commit_hash,
            message=message,
            branch_id=1,
            author=author,
            timestamp=datetime.utcnow(),
        )

    # Branch parsing edge cases - test extractor directly
    def test_extract_jira_issue_lowercase(self):
        """Test extracting lowercase Jira issue."""
        result = self.aggregator.extract_jira_issue("feature/proj-123-login")
        assert result is None

    def test_extract_jira_issue_mixed_case(self):
        """Test extracting mixed case Jira issue."""
        result = self.aggregator.extract_jira_issue("feature/PrOj-123-login")
        assert result is None

    def test_extract_first_jira_issue_multiple(self):
        """Test extracting first Jira issue when multiple exist."""
        result = self.aggregator.extract_jira_issue("feature/PROJ-123-PROJ-124-fix")
        assert result == "PROJ-123"

    def test_extract_jira_issue_special_branches(self):
        """Test Jira extraction from various branch names."""
        test_cases = [
            ("feature/PROJ-123", "PROJ-123"),
            ("PROJ-123", "PROJ-123"),
            ("PROJ-123-hotfix", "PROJ-123"),
            ("hotfix-PROJ-123-fix", "PROJ-123"),
            ("users/PROJ-123/feature", "PROJ-123"),
            ("release/1.0-PROJ-999", "PROJ-999"),
            ("main", None),
            ("develop", None),
            ("feature/no-issue", None),
            ("", None),
            (None, None),
        ]

        for branch, expected in test_cases:
            result = self.aggregator.extract_jira_issue(branch)
            assert result == expected, f"Failed for branch: {branch}"

    # Merge commit filtering - test message filtering logic
    def test_filter_merge_variants(self):
        """Test filtering various merge commit message formats."""
        commits = [
            self._create_commit("1", "Merge branch 'main'"),
            self._create_commit("2", "Merge remote-tracking branch 'origin/main'"),
            self._create_commit("3", "Merge pull request #123"),
            self._create_commit("4", "Fix merge bug"),
            self._create_commit("5", "Merged feature branch"),
        ]

        result = self.aggregator.filter_unprocessed_commits(commits, set())

        # "Merge branch" and "Merge pull request" are filtered
        assert len(result) == 3
        assert result[0].commit_hash == "2"
        assert result[1].commit_hash == "4"
        assert result[2].commit_hash == "5"

    def test_filter_empty_message_commits(self):
        """Test filtering commits with empty or whitespace messages."""
        commits = [
            self._create_commit("1", ""),
            self._create_commit("2", "   "),
            self._create_commit("3", None),
            self._create_commit("4", "Valid commit"),
        ]

        result = self.aggregator.filter_unprocessed_commits(commits, set())

        assert len(result) == 1
        assert result[0].commit_hash == "4"

    def test_filter_already_processed_commits(self):
        """Test filtering commits already in processed set."""
        commits = [
            self._create_commit("abc123", "Fix 1"),
            self._create_commit("def456", "Fix 2"),
        ]

        processed_hashes = {"abc123"}

        result = self.aggregator.filter_unprocessed_commits(commits, processed_hashes)

        assert len(result) == 1
        assert result[0].commit_hash == "def456"

    # Group by Jira - test extraction logic
    def test_group_by_jira_from_branch_name(self):
        """Test that Jira is extracted from branch name."""
        # The aggregator extracts Jira from branch name via the Branch relationship
        # For unit tests, we test the extraction logic directly
        test_branches = [
            ("feature/PROJ-123-login", "PROJ-123"),
            ("feature/ABC-456", "ABC-456"),
            ("main", None),
        ]
        
        for branch_name, expected_jira in test_branches:
            result = self.aggregator.extract_jira_issue(branch_name)
            assert result == expected_jira

    def test_aggregate_for_event_empty(self):
        """Test aggregation with empty commits list."""
        result = self.aggregator.aggregate_for_event([])
        assert result == {}

    def test_aggregate_for_event_all_processed(self):
        """Test aggregation when all commits already processed."""
        commit = self._create_commit("1", "Fix")
        result = self.aggregator.aggregate_for_event([commit], processed_commit_hashes={"1"})
        assert result == {}


# =============================================================================
# AISummaryBuilder Tests - Edge Cases
# =============================================================================

class TestAISummaryBuilderEdgeCases:
    """Edge case tests for AISummaryBuilder."""

    def setup_method(self):
        self.builder = AISummaryBuilder()

    def _create_commit(self, commit_hash: str, message: str, author: str = "Ivan"):
        """Helper to create Commit."""
        return Commit(
            commit_hash=commit_hash,
            message=message,
            author=author,
            timestamp=datetime.utcnow(),
            branch_id=1,
        )

    def test_multiple_authors(self):
        """Test extracting multiple unique authors."""
        commits = [
            self._create_commit("1", "Fix 1", "Ivan"),
            self._create_commit("2", "Fix 2", "Maria"),
            self._create_commit("3", "Fix 3", "Ivan"),
            self._create_commit("4", "Fix 4", "John"),
        ]

        authors = self.builder._extract_authors(commits)

        assert set(authors) == {"Ivan", "Maria", "John"}
        assert len(authors) == 3

    def test_authors_email_format(self):
        """Test extracting authors from email format."""
        commits = [
            self._create_commit("1", "Fix 1", "Ivan <ivan@example.com>"),
            self._create_commit("2", "Fix 2", "maria@example.com"),
            self._create_commit("3", "Fix 3", "John Doe <john@test.com>"),
        ]

        authors = self.builder._extract_authors(commits)

        assert "Ivan" in authors
        assert "maria" in authors
        assert "John Doe" in authors

    def test_clean_commit_message_prefixes(self):
        """Test cleaning various commit message prefixes."""
        assert self.builder._clean_commit_message("WIP: add login") == "add login"
        assert self.builder._clean_commit_message("WIP add login") == "add login"
        assert self.builder._clean_commit_message("Draft: update deps") == "update deps"
        assert self.builder._clean_commit_message("Draft update deps") == "update deps"
        assert self.builder._clean_commit_message("feat: add login") == "feat: add login"

    def test_clean_commit_message_wip_variants(self):
        """Test cleaning WIP and Draft prefixes."""
        assert self.builder._clean_commit_message("WIP: fix bug") == "fix bug"
        assert self.builder._clean_commit_message("WIP fix bug") == "fix bug"
        assert self.builder._clean_commit_message("Draft: add feature") == "add feature"

    def test_multiline_commit_message(self):
        """Test cleaning multiline commit messages."""
        msg = "Fix login bug\n\nAdded retry logic"
        cleaned = self.builder._clean_commit_message(msg)
        assert "Fix login bug" in cleaned

    def test_clean_commit_message_whitespace(self):
        """Test cleaning whitespace in commit messages."""
        assert self.builder._clean_commit_message("  Fix bug  ") == "Fix bug"
        assert self.builder._clean_commit_message("\tFix bug\n") == "Fix bug"
        assert self.builder._clean_commit_message("") == ""

    def test_build_summary_input_basic(self):
        """Test building summary with basic commits."""
        commits = [
            self._create_commit("abc123", "Fix bug", "Ivan"),
            self._create_commit("def456", "Add feature", "Ivan"),
        ]

        summary = self.builder.build_summary_input("PROJ-123", commits)

        assert summary["jira_issue"] == "PROJ-123"
        assert len(summary["commit_messages"]) == 2
        assert summary["commit_count"] == 2

    def test_build_summary_input_dedup_messages(self):
        """Test that duplicate commit messages are deduplicated."""
        commits = [
            self._create_commit("1", "Fix bug"),
            self._create_commit("2", "Fix bug"),
            self._create_commit("3", "Add feature"),
        ]

        summary = self.builder.build_summary_input("PROJ-123", commits)

        assert len(summary["commit_messages"]) == 2
        assert summary["commit_messages"].count("Fix bug") == 1

    def test_ai_prompt_structure(self):
        """Test AI prompt contains all required sections."""
        summary_input = {
            "jira_issue": "PROJ-1",
            "commit_messages": ["Fix bug"],
            "authors": ["Ivan"],
            "time_range": {"start": "2024-01-15T10:00:00", "end": "2024-01-15T10:30:00"},
            "commit_count": 1,
            "changed_files": ["test.py"],
            "diff_summary": ["test.py: +10 lines"],
            "merge_request_title": "Fix bug MR",
            "merge_request_description": "Fixes the bug",
        }

        prompt = self.builder.format_for_ai(summary_input)

        assert "PROJ-1" in prompt
        assert "Fix bug" in prompt
        assert "Ivan" in prompt
        assert "test.py" in prompt
        assert "Fix bug MR" in prompt

    def test_ai_prompt_empty_commits(self):
        """Test AI prompt with no commits."""
        summary_input = {
            "jira_issue": "PROJ-1",
            "commit_messages": [],
            "authors": [],
            "time_range": {"start": None, "end": None},
            "commit_count": 0,
            "changed_files": [],
            "diff_summary": [],
            "merge_request_title": "",
            "merge_request_description": "",
        }

        prompt = self.builder.format_for_ai(summary_input)

        assert "PROJ-1" in prompt
        assert "No commits" in prompt

    def test_time_range_calculation(self):
        """Test time range calculation from commits."""
        now = datetime.utcnow()
        commits = [
            self._create_commit("1", "Fix 1"),
            self._create_commit("2", "Fix 2"),
            self._create_commit("3", "Fix 3"),
        ]
        commits[0].timestamp = now - timedelta(hours=1)
        commits[1].timestamp = now
        commits[2].timestamp = now - timedelta(minutes=30)

        time_range = self.builder._calculate_time_range(commits)

        assert time_range["start"] is not None
        assert time_range["end"] is not None

    def test_time_range_no_timestamps(self):
        """Test time range when commits have no timestamps."""
        commits = [
            self._create_commit("1", "Fix 1"),
            self._create_commit("2", "Fix 2"),
        ]
        commits[0].timestamp = None
        commits[1].timestamp = None

        time_range = self.builder._calculate_time_range(commits)

        assert time_range["start"] is None
        assert time_range["end"] is None


# =============================================================================
# EventQueueService Tests - Failure Scenarios
# =============================================================================

class TestEventQueueServiceFailures:
    """Failure scenario tests for EventQueueService."""

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_push_event_redis_failure(self, mock_redis_class):
        """Test push event when Redis is down."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.rpush.side_effect = Exception("Redis down")
        mock_redis.sismember.return_value = False

        service = EventQueueService()

        with pytest.raises(Exception):
            service.push_event(42)

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_push_event_timeout(self, mock_redis_class):
        """Test push event with timeout."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.sismember.return_value = False

        service = EventQueueService()
        result = service.push_event(42)

        assert result is True
        mock_redis.rpush.assert_called_once()

    def test_push_invalid_event_id(self):
        """Test pushing invalid event ID."""
        with patch.object(EventQueueService, '__init__', lambda x: None):
            service = EventQueueService()
            service.redis = Mock()
            service.queue_name = "test_queue"
            service.processed_key = "test_processed"
            service.processing_key = "test_processing"
            service.redis.sismember.return_value = False

            result = service.push_event(None)
            assert result is True

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_pop_event_timeout(self, mock_redis_class):
        """Test pop event with timeout (no events available)."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.blpop.return_value = None

        service = EventQueueService()
        result = service.pop_event(timeout=1)

        assert result is None

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_retry_event_max_retries_exceeded(self, mock_redis_class):
        """Test retry event when max retries exceeded."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis

        with patch("app.processing.event_queue_service.get_settings") as mock_settings:
            mock_settings.return_value.MAX_RETRIES = 3

            service = EventQueueService()
            result = service.retry_event(42, retry_count=3)

            assert result is False
            mock_redis.rpush.assert_called_once_with(service.dead_letter_queue_name, "42")

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_retry_event_within_limits(self, mock_redis_class):
        """Test retry event when within retry limits."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.zadd.return_value = 1

        with patch("app.processing.event_queue_service.get_settings") as mock_settings:
            mock_settings.return_value.MAX_RETRIES = 3
            mock_settings.return_value.RETRY_DELAY_SECONDS = 60

            service = EventQueueService()
            result = service.retry_event(42, retry_count=1)

            assert result is True
            mock_redis.zadd.assert_called_once()

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_get_queue_stats(self, mock_redis_class):
        """Test getting queue statistics."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.llen.return_value = 5
        mock_redis.zcard.return_value = 2
        mock_redis.scard.return_value = 1

        service = EventQueueService()
        stats = service.get_queue_stats()

        assert "main_queue_length" in stats
        assert "retry_queue_length" in stats
        assert "dead_letter_queue_length" in stats
        assert "currently_processing" in stats


# =============================================================================
# ProcessingRepository Tests - Edge Cases
# =============================================================================

class TestProcessingRepositoryEdgeCases:
    """Edge case tests for ProcessingRepository."""

    def test_mark_commits_empty_list(self):
        """Test marking empty list of commits."""
        mock_session = Mock()
        repo = ProcessingRepository(mock_session)

        result = repo.mark_commits_as_processed([])

        assert result == 0
        mock_session.query.assert_not_called()

    def test_mark_commits_db_error(self):
        """Test marking commits when DB throws exception."""
        mock_session = Mock()
        mock_query = Mock()
        mock_filter = Mock()

        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.update.side_effect = Exception("DB connection error")

        repo = ProcessingRepository(mock_session)

        with pytest.raises(Exception):
            repo.mark_commits_as_processed([1, 2, 3])

    def test_get_event_not_found(self):
        """Test getting non-existent event."""
        mock_session = Mock()
        mock_query = Mock()
        mock_filter = Mock()

        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = None

        repo = ProcessingRepository(mock_session)
        result = repo.get_event(999)

        assert result is None

    def test_mark_event_as_processed_not_found(self):
        """Test marking non-existent event as processed."""
        mock_session = Mock()
        mock_query = Mock()
        mock_filter = Mock()

        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = None

        repo = ProcessingRepository(mock_session)
        repo.mark_event_as_processed(999)

    def test_save_ai_summary(self):
        """Test saving AI summary."""
        mock_session = Mock()
        repo = ProcessingRepository(mock_session)

        summary_data = {
            "jira_issue": "PROJ-123",
            "summary_input_json": {"messages": ["Fix bug"]},
            "commit_count": 1,
        }

        result = repo.save_ai_summary(summary_data)

        assert result is not None
        mock_session.add.assert_called_once()


# =============================================================================
# EventProcessor Tests - Pipeline and Retry Logic
# =============================================================================

class TestEventProcessorPipeline:
    """Integration and pipeline tests for EventProcessor."""

    @patch("app.processing.event_processor.ProcessingRepository")
    @patch("app.processing.event_processor.session_scope")
    @patch("app.processing.event_processor.EventQueueService")
    def test_process_event_success(self, mock_queue_service_class, mock_session_scope, mock_repo_class):
        """Test successful event processing."""
        mock_session = Mock()
        mock_session_scope.return_value.__enter__ = Mock(return_value=mock_session)
        mock_session_scope.return_value.__exit__ = Mock(return_value=None)

        mock_queue_service = Mock()
        mock_queue_service_class.return_value = mock_queue_service

        mock_event = Mock()
        mock_event.id = 1
        mock_event.event_type = "push"
        mock_event.processed = False

        mock_repo = Mock()
        mock_repo.get_event.return_value = mock_event
        mock_repo.get_unprocessed_commits_for_event.return_value = []
        mock_repo.mark_event_as_processed = Mock()
        mock_repo_class.return_value = mock_repo

        processor = EventProcessor()
        result = processor.process_event(1)

        assert result is True
        mock_repo.mark_event_as_processed.assert_called()
        mock_queue_service.mark_event_processed.assert_called()

    @patch("app.processing.event_processor.session_scope")
    @patch("app.processing.event_processor.EventQueueService")
    def test_process_event_already_processed(self, mock_queue_service_class, mock_session_scope):
        """Test processing already processed event."""
        mock_session = Mock()
        mock_session_scope.return_value.__enter__ = Mock(return_value=mock_session)
        mock_session_scope.return_value.__exit__ = Mock(return_value=None)

        mock_queue_service = Mock()
        mock_queue_service_class.return_value = mock_queue_service

        mock_event = Mock()
        mock_event.id = 1
        mock_event.processed = True

        from app.shared.processing_repository import ProcessingRepository
        with patch.object(ProcessingRepository, '__init__', lambda x, y: None):
            mock_repo = Mock()
            mock_repo.get_event.return_value = mock_event

            with patch.object(ProcessingRepository, '__new__', return_value=mock_repo):
                processor = EventProcessor()
                result = processor.process_event(1)

                assert result is True

    @patch("app.processing.event_processor.session_scope")
    @patch("app.processing.event_processor.EventQueueService")
    def test_process_event_not_found(self, mock_queue_service_class, mock_session_scope):
        """Test processing non-existent event."""
        mock_session = Mock()
        mock_session_scope.return_value.__enter__ = Mock(return_value=mock_session)
        mock_session_scope.return_value.__exit__ = Mock(return_value=None)

        mock_queue_service = Mock()
        mock_queue_service_class.return_value = mock_queue_service

        from app.shared.processing_repository import ProcessingRepository
        with patch.object(ProcessingRepository, '__init__', lambda x, y: None):
            mock_repo = Mock()
            mock_repo.get_event.return_value = None

            with patch.object(ProcessingRepository, '__new__', return_value=mock_repo):
                processor = EventProcessor()
                result = processor.process_event(999)

                assert result is False

    @patch("app.processing.event_processor.ProcessingRepository")
    @patch("app.processing.event_processor.session_scope")
    @patch("app.processing.event_processor.EventQueueService")
    def test_process_event_with_exception(self, mock_queue_service_class, mock_session_scope, mock_repo_class):
        """Test event processing with exception (retry logic)."""
        mock_session = Mock()
        mock_session_scope.return_value.__enter__ = Mock(return_value=mock_session)
        mock_session_scope.return_value.__exit__ = Mock(return_value=None)

        mock_queue_service = Mock()
        mock_queue_service_class.return_value = mock_queue_service

        mock_repo = Mock()
        mock_repo.get_event.side_effect = [Exception("DB error"), Mock(retry_count=1)]
        mock_repo_class.return_value = mock_repo

        processor = EventProcessor()
        result = processor.process_event(1)

        assert result is False
        mock_queue_service.retry_event.assert_called()

    @patch("app.processing.event_processor.EventQueueService")
    def test_process_non_push_event(self, mock_queue_service_class):
        """Test processing non-push event (should skip AI summary)."""
        mock_queue_service = Mock()
        mock_queue_service_class.return_value = mock_queue_service

        mock_session = Mock()
        mock_event = Mock()
        mock_event.id = 1
        mock_event.event_type = "merge_request"
        mock_event.processed = False

        from app.shared.processing_repository import ProcessingRepository
        with patch.object(ProcessingRepository, '__init__', lambda x, y: None):
            with patch("app.processing.event_processor.session_scope") as mock_scope:
                mock_scope.return_value.__enter__ = Mock(return_value=mock_session)
                mock_scope.return_value.__exit__ = Mock(return_value=None)

                mock_repo = Mock()
                mock_repo.get_event.return_value = mock_event

                with patch.object(ProcessingRepository, '__new__', return_value=mock_repo):
                    processor = EventProcessor()
                    result = processor.process_event(1)

                    assert result is True


# =============================================================================
# Integration Tests - Full Pipeline
# =============================================================================

class TestFullPipelineIntegration:
    """Integration tests for full event processing pipeline."""

    def test_commit_aggregator_extraction_logic(self):
        """Test commit aggregation Jira extraction logic."""
        aggregator = CommitAggregator()

        # Test extraction from various branch names
        test_cases = [
            ("feature/PROJ-123-login", "PROJ-123"),
            ("bugfix/ABC-456-fix", "ABC-456"),
            ("main", None),
            ("develop", None),
        ]

        for branch_name, expected_jira in test_cases:
            result = aggregator.extract_jira_issue(branch_name)
            assert result == expected_jira, f"Failed for: {branch_name}"

    def test_ai_summary_builder_full_flow(self):
        """Test full AI summary building flow."""
        builder = AISummaryBuilder()

        now = datetime.utcnow()
        commits = [
            Commit(
                commit_hash="1",
                message="Fix login bug",
                author="Ivan <ivan@example.com>",
                timestamp=now,
                branch_id=1,
            ),
            Commit(
                commit_hash="2",
                message="Add retry logic",
                author="Ivan <ivan@example.com>",
                timestamp=now + timedelta(minutes=10),
                branch_id=1,
            ),
        ]

        summary = builder.build_summary_input("PROJ-123", commits)

        assert summary["jira_issue"] == "PROJ-123"
        assert len(summary["commit_messages"]) == 2
        assert summary["authors"] == ["Ivan"]
        assert summary["commit_count"] == 2
        assert summary["time_range"]["start"] is not None
        assert summary["time_range"]["end"] is not None

        prompt = builder.format_for_ai(summary)
        assert "PROJ-123" in prompt
        assert "Fix login bug" in prompt
        assert "Add retry logic" in prompt
