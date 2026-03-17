"""Tests for the processing layer."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from app.models import Event, Commit, AISummary
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
        """Test filtering out processed commits."""
        commits = [
            Commit(commit_id="abc123", message="fix bug", branch="feature/PROJ-123"),
            Commit(commit_id="def456", message="add feature", branch="feature/PROJ-123"),
            Commit(commit_id="ghi789", message="", branch="feature/PROJ-123"),  # Empty message
            Commit(commit_id="jkl012", message="Merge branch", branch="feature/PROJ-123"),  # Merge
        ]
        
        processed_hashes = {"abc123"}  # First commit already processed
        
        result = self.aggregator.filter_unprocessed_commits(commits, processed_hashes)
        
        # Should only return the second commit (others filtered)
        assert len(result) == 1
        assert result[0].commit_id == "def456"

    def test_group_by_jira_issue(self):
        """Test grouping commits by Jira issue."""
        commits = [
            Commit(commit_id="abc", message="fix 1", branch="feature/PROJ-123-a"),
            Commit(commit_id="def", message="fix 2", branch="feature/PROJ-123-b"),
            Commit(commit_id="ghi", message="fix 3", branch="feature/ABC-456"),
            Commit(commit_id="jkl", message="fix 4", branch="main"),  # No Jira
        ]
        
        grouped = self.aggregator.group_by_jira_issue(commits)
        
        assert "PROJ-123" in grouped
        assert "ABC-456" in grouped
        assert None in grouped  # Commits without Jira
        assert len(grouped["PROJ-123"]) == 2
        assert len(grouped["ABC-456"]) == 1
        assert len(grouped[None]) == 1


class TestAISummaryBuilder:
    """Tests for AISummaryBuilder."""

    def setup_method(self):
        self.builder = AISummaryBuilder()

    def test_build_summary_input(self):
        """Test building AI summary input."""
        now = datetime.utcnow()
        commits = [
            Commit(
                commit_id="abc123",
                message="Fix login bug",
                author="Ivan",
                timestamp=now,
                branch="feature/PROJ-123",
                repository="my-repo",
            ),
            Commit(
                commit_id="def456",
                message="Add retry logic",
                author="Ivan",
                timestamp=now + timedelta(minutes=10),
                branch="feature/PROJ-123",
                repository="my-repo",
            ),
        ]
        
        summary = self.builder.build_summary_input("PROJ-123", commits)
        
        assert summary["jira_issue"] == "PROJ-123"
        assert len(summary["commit_messages"]) == 2
        assert "Fix login bug" in summary["commit_messages"]
        assert "Add retry logic" in summary["commit_messages"]
        assert summary["authors"] == ["Ivan"]
        assert summary["commit_count"] == 2
        assert summary["repository"] == "my-repo"
        assert summary["branch"] == "feature/PROJ-123"

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
            Commit(author="Ivan <ivan@example.com>"),
            Commit(author="Maria <maria@example.com>"),
            Commit(author="Ivan <ivan@example.com>"),  # Duplicate
            Commit(author="John"),
        ]
        
        authors = self.builder._extract_authors(commits)
        
        assert len(authors) == 3
        assert "Ivan" in authors
        assert "Maria" in authors
        assert "John" in authors

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
        mock_redis.sismember.return_value = False  # Not processed, not in queue
        
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
        mock_redis.sismember.return_value = True  # Already processed
        
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
        
        from app.repositories.processing_repository import ProcessingRepository
        
        repo = ProcessingRepository(mock_session)
        result = repo.mark_commits_as_processed([1, 2, 3])
        
        assert result == 3
        mock_filter.update.assert_called_once_with({"processed": True}, synchronize_session=False)
