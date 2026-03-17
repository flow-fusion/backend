"""Tests for GitContextService - Updated for unified models."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.shared.models import Commit, Branch
from app.processing.git_context_service import (
    GitContextService,
    GitContext,
    DiffSummary,
    MergeRequestInfo,
    GitContextServiceSync,
)


# =============================================================================
# DiffSummary Tests
# =============================================================================

class TestDiffSummary:
    """Tests for DiffSummary dataclass."""

    def test_to_summary_line_additions_only(self):
        """Test summary line with only additions."""
        summary = DiffSummary(
            filename="auth_service.py",
            additions=20,
            deletions=0,
            status="modified",
        )
        assert summary.to_summary_line() == "auth_service.py: +20 lines added"

    def test_to_summary_line_deletions_only(self):
        """Test summary line with only deletions."""
        summary = DiffSummary(
            filename="old_file.py",
            additions=0,
            deletions=15,
            status="deleted",
        )
        assert summary.to_summary_line() == "old_file.py: -15 lines removed"

    def test_to_summary_line_both(self):
        """Test summary line with both additions and deletions."""
        summary = DiffSummary(
            filename="controller.ts",
            additions=10,
            deletions=5,
            status="modified",
        )
        assert summary.to_summary_line() == "controller.ts: +10 lines added -5 lines removed"

    def test_to_summary_line_empty(self):
        """Test summary line with no changes."""
        summary = DiffSummary(
            filename="unchanged.txt",
            additions=0,
            deletions=0,
            status="modified",
        )
        assert summary.to_summary_line() == "unchanged.txt:"


# =============================================================================
# MergeRequestInfo Tests
# =============================================================================

class TestMergeRequestInfo:
    """Tests for MergeRequestInfo dataclass."""

    def test_to_dict(self):
        """Test converting to dictionary."""
        mr = MergeRequestInfo(
            title="Fix login bug",
            description="This fixes the redirect issue",
            author="Ivan",
            state="opened",
            web_url="https://gitlab.com/project/merge_requests/123",
        )

        result = mr.to_dict()

        assert result["title"] == "Fix login bug"
        assert result["description"] == "This fixes the redirect issue"
        assert result["author"] == "Ivan"
        assert result["state"] == "opened"
        assert "merge_requests/123" in result["web_url"]


# =============================================================================
# GitContext Tests
# =============================================================================

class TestGitContext:
    """Tests for GitContext dataclass."""

    def test_to_dict_empty(self):
        """Test converting empty context to dictionary."""
        context = GitContext()
        result = context.to_dict()

        assert result["changed_files"] == []
        assert result["diff_summary"] == []
        assert result["merge_request_title"] == ""
        assert result["merge_request_description"] == ""

    def test_to_dict_with_data(self):
        """Test converting context with data to dictionary."""
        diff_summary = DiffSummary(
            filename="test.py",
            additions=10,
            deletions=5,
            status="modified",
        )
        mr = MergeRequestInfo(title="Test MR", description="Test desc", author="Ivan")

        context = GitContext(
            changed_files=["test.py"],
            diff_summary=[diff_summary],
            merge_request=mr,
            repository_name="test-repo",
            branch_name="feature/test",
        )

        result = context.to_dict()

        assert result["changed_files"] == ["test.py"]
        assert len(result["diff_summary"]) == 1
        assert "test.py:" in result["diff_summary"][0]
        assert result["merge_request_title"] == "Test MR"
        assert result["merge_request_description"] == "Test desc"


# =============================================================================
# GitContextService Tests
# =============================================================================

class TestGitContextService:
    """Tests for GitContextService."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = GitContextService(
            gitlab_base_url="https://gitlab.test.com",
            gitlab_api_token="test-token",
        )

    def test_get_project_id_numeric(self):
        """Test project ID extraction for numeric ID."""
        result = self.service._get_project_id("12345")
        assert result == "12345"

    def test_get_project_id_path(self):
        """Test project ID extraction for path."""
        result = self.service._get_project_id("group/project")
        assert result == "group/project"

    def test_get_project_id_empty(self):
        """Test project ID extraction for empty input."""
        result = self.service._get_project_id("")
        assert result is None
        result = self.service._get_project_id(None)
        assert result is None

    def test_get_headers_with_token(self):
        """Test headers include authorization token."""
        headers = self.service._get_headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Content-Type"] == "application/json"

    def test_summarize_diff_empty(self):
        """Test diff summarization with empty input."""
        result = self.service._summarize_diff([])
        assert result == []

    def test_summarize_diff_single_file(self):
        """Test diff summarization for single file."""
        diff_data = [
            {
                "new_path": "auth_service.py",
                "diff": "\n+def login():\n+    pass\n-old_value = 1\n",
                "new_file": False,
                "deleted_file": False,
                "renamed_file": False,
            }
        ]

        result = self.service._summarize_diff(diff_data)

        assert len(result) == 1
        assert result[0].filename == "auth_service.py"
        assert result[0].additions == 2
        assert result[0].deletions == 1
        assert result[0].status == "modified"

    def test_summarize_diff_with_stats(self):
        """Test diff summarization using stats field."""
        diff_data = [
            {
                "new_path": "test.py",
                "diff": "",
                "stats": {"additions": 10, "deletions": 5},
                "new_file": True,
            }
        ]

        result = self.service._summarize_diff(diff_data)

        assert len(result) == 1
        assert result[0].additions == 10
        assert result[0].deletions == 5
        assert result[0].status == "added"

    def test_summarize_diff_deleted_file(self):
        """Test diff summarization for deleted file."""
        diff_data = [
            {
                "old_path": "old_file.py",
                "deleted_file": True,
            }
        ]

        result = self.service._summarize_diff(diff_data)

        assert len(result) == 1
        assert result[0].status == "deleted"

    def test_summarize_diff_renamed_file(self):
        """Test diff summarization for renamed file."""
        diff_data = [
            {
                "old_path": "old_name.py",
                "new_path": "new_name.py",
                "renamed_file": True,
            }
        ]

        result = self.service._summarize_diff(diff_data)

        assert len(result) == 1
        assert result[0].filename == "new_name.py"
        assert result[0].status == "renamed"

    def test_merge_diff_summaries(self):
        """Test merging diff summaries for same file."""
        summaries = [
            DiffSummary("test.py", 10, 5, "modified"),
            DiffSummary("test.py", 5, 3, "modified"),
            DiffSummary("other.py", 20, 0, "added"),
        ]

        result = self.service._merge_diff_summaries(summaries)

        assert len(result) == 2
        test_py = next(s for s in result if s.filename == "test.py")
        assert test_py.additions == 15
        assert test_py.deletions == 8

    def test_clear_cache(self):
        """Test clearing caches."""
        self.service._commit_cache["key"] = "value"
        self.service._diff_cache["key"] = "value"
        self.service._mr_cache["key"] = "value"

        self.service.clear_cache()

        assert len(self.service._commit_cache) == 0
        assert len(self.service._diff_cache) == 0
        assert len(self.service._mr_cache) == 0


class TestGitContextServiceAsync:
    """Async tests for GitContextService."""

    @pytest.mark.asyncio
    async def test_get_commit_details_cached(self):
        """Test getting commit details from cache."""
        service = GitContextService()
        service._commit_cache["proj:abc123"] = {"id": "abc123"}

        result = await service.get_commit_details("proj", "abc123")

        assert result == {"id": "abc123"}

    @pytest.mark.asyncio
    async def test_get_commit_details_from_api(self):
        """Test getting commit details from API."""
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = {"id": "abc123", "message": "Fix bug"}
        mock_response.raise_for_status = Mock()
        mock_client.request.return_value = mock_response

        service = GitContextService(http_client=mock_client)
        result = await service.get_commit_details("proj", "abc123")

        assert result is not None
        assert result["id"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_commit_details_not_found(self):
        """Test getting commit details when not found."""
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_client.request.return_value = mock_response

        service = GitContextService(http_client=mock_client)
        result = await service.get_commit_details("proj", "invalid")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_diff_cached(self):
        """Test getting diff from cache."""
        service = GitContextService()
        service._diff_cache["proj:abc123"] = [{"new_path": "test.py"}]

        result = await service.get_commit_diff("proj", "abc123")

        assert result == [{"new_path": "test.py"}]

    @pytest.mark.asyncio
    async def test_get_merge_request_cached(self):
        """Test getting MR from cache."""
        service = GitContextService()
        cached_mr = MergeRequestInfo(title="Cached MR")
        service._mr_cache["proj:feature/test"] = cached_mr

        result = await service.get_merge_request_by_branch("proj", "feature/test")

        assert result is not None
        assert result.title == "Cached MR"

    @pytest.mark.asyncio
    async def test_get_merge_request_not_found(self):
        """Test getting MR when none exists."""
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_client.request.return_value = mock_response

        service = GitContextService(http_client=mock_client)
        result = await service.get_merge_request_by_branch("proj", "feature/test")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_merge_request_success(self):
        """Test getting MR successfully."""
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "title": "Fix login",
                "description": "Fixes login bug",
                "author": {"name": "Ivan"},
                "state": "opened",
            }
        ]
        mock_response.raise_for_status = Mock()
        mock_client.request.return_value = mock_response

        service = GitContextService(http_client=mock_client)
        result = await service.get_merge_request_by_branch("proj", "feature/login")

        assert result is not None
        assert result.title == "Fix login"
        assert result.author == "Ivan"

    @pytest.mark.asyncio
    async def test_load_context_empty_commits(self):
        """Test loading context with empty commits list."""
        service = GitContextService()
        result = await service.load_context([])

        assert result.changed_files == []
        assert result.diff_summary == []
        assert result.merge_request is None

    @pytest.mark.asyncio
    async def test_load_context_no_project_id(self):
        """Test loading context when project ID cannot be determined."""
        service = GitContextService()
        commits = [
            Commit(commit_hash="abc", branch_id=1, author="Ivan", message="test", timestamp=datetime.utcnow())
        ]

        result = await service.load_context(commits)

        assert result.changed_files == []

    @pytest.mark.asyncio
    async def test_load_context_with_mock(self):
        """Test loading context with mocked API."""
        mock_client = AsyncMock()

        diff_response = Mock()
        diff_response.json.return_value = [
            {
                "new_path": "test.py",
                "diff": "\n+new line\n-old line\n",
                "stats": {"additions": 5, "deletions": 2},
            }
        ]
        diff_response.raise_for_status = Mock()

        mr_response = Mock()
        mr_response.json.return_value = [
            {
                "title": "Test MR",
                "description": "Test description",
                "author": {"name": "Ivan"},
                "state": "opened",
            }
        ]
        mr_response.raise_for_status = Mock()

        mock_client.request.side_effect = [diff_response, mr_response]

        service = GitContextService(http_client=mock_client)
        commits = [
            Commit(
                commit_hash="abc123",
                branch_id=1,
                author="Ivan",
                message="test",
                timestamp=datetime.utcnow(),
            )
        ]

        # Mock branch relationship using MagicMock with proper SQLAlchemy attributes
        mock_branch = MagicMock()
        mock_branch.name = "feature/test"
        mock_branch.repository = MagicMock()
        mock_branch.repository.name = "test-repo"
        commits[0].branch = mock_branch

        result = await service.load_context(commits)

        assert "test.py" in result.changed_files
        assert len(result.diff_summary) == 1
        assert result.merge_request is not None
        assert result.merge_request.title == "Test MR"


class TestGitContextServiceSync:
    """Tests for synchronous wrapper."""

    @patch("app.processing.git_context_service.GitContextService")
    def test_load_context_sync(self, mock_service_class):
        """Test synchronous context loading."""
        mock_service = AsyncMock()
        mock_service.load_context = AsyncMock(return_value=GitContext())
        mock_service.__aenter__ = AsyncMock(return_value=mock_service)
        mock_service.__aexit__ = AsyncMock(return_value=None)
        mock_service_class.return_value = mock_service

        sync_service = GitContextServiceSync()
        commits = [
            Commit(commit_hash="abc", branch_id=1, author="Ivan", message="test", timestamp=datetime.utcnow())
        ]
        result = sync_service.load_context(commits)

        assert isinstance(result, GitContext)


class TestGitContextServiceErrorHandling:
    """Error handling tests for GitContextService."""

    @pytest.mark.asyncio
    async def test_request_timeout(self):
        """Test request with timeout."""
        import httpx

        mock_client = AsyncMock()
        mock_client.request.side_effect = httpx.TimeoutException("Timeout")

        service = GitContextService(http_client=mock_client)
        service.retry_count = 1

        result = await service._request("GET", "test/endpoint")

        assert result is None

    @pytest.mark.asyncio
    async def test_request_404(self):
        """Test request with 404 response."""
        import httpx

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_client.request.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=Mock(),
            response=mock_response,
        )

        service = GitContextService(http_client=mock_client)
        result = await service._request("GET", "test/endpoint")

        assert result is None

    @pytest.mark.asyncio
    async def test_request_http_error(self):
        """Test request with HTTP error."""
        import httpx

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 500
        mock_client.request.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=Mock(),
            response=mock_response,
        )

        service = GitContextService(http_client=mock_client)
        service.retry_count = 1

        result = await service._request("GET", "test/endpoint")

        assert result is None

    @pytest.mark.asyncio
    async def test_request_no_client(self):
        """Test request without initialized client."""
        service = GitContextService(http_client=None)
        service._client = None

        result = await service._request("GET", "test/endpoint")

        assert result is None

    @pytest.mark.asyncio
    async def test_load_context_graceful_failure(self):
        """Test that load_context continues gracefully on API failure."""
        mock_client = AsyncMock()
        mock_client.request.side_effect = Exception("API Error")

        service = GitContextService(http_client=mock_client)
        service.retry_count = 1

        commits = [
            Commit(
                commit_hash="abc",
                branch_id=1,
                author="Ivan",
                message="test",
                timestamp=datetime.utcnow(),
            )
        ]

        result = await service.load_context(commits)

        assert isinstance(result, GitContext)
        assert result.changed_files == []
