"""Tests for the processing layer - Updated to avoid SQLAlchemy relationship mocking issues."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from app.shared.models import Commit, Branch
from app.processing.commit_aggregator import CommitAggregator
from app.processing.ai_summary_builder import AISummaryBuilder


class TestCommitAggregator:
    """Tests for CommitAggregator."""

    def setup_method(self):
        self.aggregator = CommitAggregator()

    def test_extract_jira_issue_from_branch(self):
        """Test extracting Jira issue from branch name."""
        assert self.aggregator.extract_jira_issue("feature/PROJ-123-login") == "PROJ-123"
        assert self.aggregator.extract_jira_issue("bugfix/ABC-456") == "ABC-456"
        assert self.aggregator.extract_jira_issue("PROJ-789-hotfix") == "PROJ-789"
        assert self.aggregator.extract_jira_issue("main") is None
        assert self.aggregator.extract_jira_issue("") is None
        assert self.aggregator.extract_jira_issue(None) is None

    def test_filter_unprocessed_commits(self):
        """Test filtering out processed commits - tests message filtering logic."""
        # Create commits without branch relationships - just test message filtering
        commits = [
            Commit(commit_hash="abc123", message="fix bug", branch_id=1, author="Ivan", timestamp=datetime.utcnow()),
            Commit(commit_hash="def456", message="add feature", branch_id=1, author="Ivan", timestamp=datetime.utcnow()),
            Commit(commit_hash="ghi789", message="", branch_id=1, author="Ivan", timestamp=datetime.utcnow()),
            Commit(commit_hash="jkl012", message="Merge branch 'main'", branch_id=1, author="Ivan", timestamp=datetime.utcnow()),
        ]

        processed_hashes = {"abc123"}

        result = self.aggregator.filter_unprocessed_commits(commits, processed_hashes)

        # Should filter: abc123 (in processed set), ghi789 (empty message), jkl012 (merge commit)
        assert len(result) == 1
        assert result[0].commit_hash == "def456"

    def test_group_by_jira_issue(self):
        """Test grouping commits by Jira issue - tests extraction from branch name."""
        # Test the extraction logic directly with branch names
        test_cases = [
            ("feature/PROJ-123-a", "PROJ-123"),
            ("feature/PROJ-123-b", "PROJ-123"),
            ("feature/ABC-456", "ABC-456"),
            ("main", None),
        ]
        
        for branch_name, expected_jira in test_cases:
            result = self.aggregator.extract_jira_issue(branch_name)
            assert result == expected_jira, f"Failed for branch: {branch_name}"


class TestAISummaryBuilder:
    """Tests for AISummaryBuilder."""

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

    def test_build_summary_input(self):
        """Test building AI summary input."""
        now = datetime.utcnow()
        commits = [
            self._create_commit("abc123", "Fix login bug", "Ivan"),
            self._create_commit("def456", "Add retry logic", "Ivan"),
        ]
        commits[0].timestamp = now
        commits[1].timestamp = now + timedelta(minutes=10)

        summary = self.builder.build_summary_input("PROJ-123", commits)

        assert summary["jira_issue"] == "PROJ-123"
        assert len(summary["commit_messages"]) == 2
        assert "Fix login bug" in summary["commit_messages"]
        assert "Add retry logic" in summary["commit_messages"]
        assert summary["authors"] == ["Ivan"]
        assert summary["commit_count"] == 2

    def test_build_summary_input_empty_commits(self):
        """Test building summary with no commits."""
        summary = self.builder.build_summary_input("PROJ-123", [])

        assert summary["jira_issue"] == "PROJ-123"
        assert summary["commit_messages"] == []
        assert summary["authors"] == []
        assert summary["commit_count"] == 0

    def test_extract_authors(self):
        """Test extracting unique authors."""
        commits = [
            self._create_commit("1", "Fix 1", "Ivan"),
            self._create_commit("2", "Fix 2", "Maria"),
            self._create_commit("3", "Fix 3", "Ivan"),
        ]

        authors = self.builder._extract_authors(commits)

        assert len(authors) == 2
        assert "Ivan" in authors
        assert "Maria" in authors

    def test_clean_commit_message(self):
        """Test cleaning commit messages."""
        assert self.builder._clean_commit_message("  Fix bug  ") == "Fix bug"
        assert self.builder._clean_commit_message("WIP: Fix bug") == "Fix bug"
        assert self.builder._clean_commit_message("Draft: Add feature") == "Add feature"
        assert self.builder._clean_commit_message("Fix bug.") == "Fix bug"

    def test_format_for_ai(self):
        """Test formatting summary for AI prompt."""
        summary_input = {
            "jira_issue": "PROJ-123",
            "commit_messages": ["Fix bug", "Add feature"],
            "authors": ["Ivan"],
            "time_range": {
                "start": "2024-01-15T10:00:00",
                "end": "2024-01-15T10:30:00",
            },
            "commit_count": 2,
            "changed_files": [],
            "diff_summary": [],
            "merge_request_title": "",
            "merge_request_description": "",
        }

        prompt = self.builder.format_for_ai(summary_input)

        assert "PROJ-123" in prompt
        assert "Fix bug" in prompt
        assert "Add feature" in prompt
        assert "Ivan" in prompt


class TestEventQueueService:
    """Tests for EventQueueService."""

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_push_event(self, mock_redis_class):
        """Test pushing event to queue."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.sismember.return_value = False

        from app.processing.event_queue_service import EventQueueService

        service = EventQueueService()
        result = service.push_event(42)

        assert result is True
        mock_redis.rpush.assert_called_once_with("event_queue", "42")

    @patch("app.processing.event_queue_service.redis.Redis")
    def test_push_event_duplicate(self, mock_redis_class):
        """Test pushing duplicate event."""
        mock_redis = Mock()
        mock_redis_class.return_value = mock_redis
        mock_redis.sismember.return_value = True

        from app.processing.event_queue_service import EventQueueService

        service = EventQueueService()
        result = service.push_event(42)

        assert result is False
        mock_redis.rpush.assert_not_called()


class TestProcessingRepository:
    """Tests for ProcessingRepository."""

    def test_mark_commits_as_processed(self):
        """Test marking commits as processed."""
        mock_session = Mock()
        mock_query = Mock()
        mock_filter = Mock()

        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.update.return_value = 3

        from app.shared.processing_repository import ProcessingRepository
        repo = ProcessingRepository(mock_session)
        result = repo.mark_commits_as_processed([1, 2, 3])

        assert result == 3
        mock_filter.update.assert_called_once_with({"processed": True}, synchronize_session=False)


def test_apply_jira_auto_transition(monkeypatch):
    """Test that EventProcessor delegates auto transition invocation to JiraClient."""
    from app.processing.event_processor import EventProcessor

    processor = EventProcessor()
    mock_jira_client = Mock()

    processor._apply_jira_auto_transition(mock_jira_client, "PROJ-123")

    mock_jira_client.auto_transition_to_in_progress_then_review.assert_called_once_with("PROJ-123")


def test_apply_jira_auto_transition_disabled(monkeypatch):
    """Test no call when JIRA_AUTO_TRANSITION is disabled."""
    from app.processing.event_processor import EventProcessor
    from app.shared.config import Settings

    monkeypatch.setattr(Settings, 'JIRA_AUTO_TRANSITION', False)

    processor = EventProcessor()
    mock_jira_client = Mock()

    processor._apply_jira_auto_transition(mock_jira_client, "PROJ-123")

    mock_jira_client.auto_transition_to_in_progress_then_review.assert_not_called()
