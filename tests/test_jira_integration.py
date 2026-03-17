"""Unit tests for Jira integration."""

import pytest
from unittest.mock import Mock, patch, call

from app.jira_integration.config import JiraConfig
from app.jira_integration.jira_client import JiraClient, find_transition_id
from app.jira_integration.mr_processor import (
    MRProcessor,
    MergeRequest,
    Commit,
    MRState,
    MR_TO_JIRA_TRANSITION,
)


class TestFindTransitionId:
    """Tests for find_transition_id helper."""

    def test_finds_exact_match(self):
        transitions = [
            {"id": "11", "name": "To Do"},
            {"id": "21", "name": "In Progress"},
            {"id": "31", "name": "Done"},
        ]
        assert find_transition_id(transitions, "In Progress") == "21"

    def test_case_insensitive(self):
        transitions = [
            {"id": "11", "name": "To Do"},
            {"id": "21", "name": "IN PROGRESS"},
            {"id": "31", "name": "Done"},
        ]
        assert find_transition_id(transitions, "in progress") == "21"

    def test_returns_none_when_not_found(self):
        transitions = [
            {"id": "11", "name": "To Do"},
            {"id": "31", "name": "Done"},
        ]
        assert find_transition_id(transitions, "In Progress") is None

    def test_empty_transitions(self):
        assert find_transition_id([], "In Progress") is None


class TestJiraClient:
    """Tests for JiraClient class."""

    @pytest.fixture
    def config(self):
        return JiraConfig(
            url="https://test.atlassian.net",
            email="test@example.com",
            token="test_token",
        )

    @pytest.fixture
    def client(self, config):
        return JiraClient(config)

    def test_get_issue(self, client):
        mock_response = {"key": "PROJ-123", "fields": {"summary": "Test"}}
        with patch.object(client.session, "request") as mock_request:
            mock_request.return_value.json.return_value = mock_response
            mock_request.return_value.status_code = 200
            mock_request.return_value.raise_for_status = Mock()

            result = client.get_issue("PROJ-123")

            assert result == mock_response
            mock_request.assert_called_once()

    def test_add_comment(self, client):
        mock_comments = {"comments": []}
        mock_new_comment = {"id": "10001", "body": {"text": "Test comment"}}

        with patch.object(client.session, "request") as mock_request:
            mock_request.side_effect = [
                Mock(json=Mock(return_value=mock_comments), status_code=200, raise_for_status=Mock()),
                Mock(json=Mock(return_value=mock_new_comment), status_code=201, raise_for_status=Mock()),
            ]

            result = client.add_comment("PROJ-123", "Test comment")

            assert result == mock_new_comment
            assert mock_request.call_count == 2

    def test_add_comment_idempotent(self, client):
        """Test that duplicate comments are not added."""
        mock_comments = {
            "comments": [
                {"body": {"text": "Test comment"}}
            ]
        }

        with patch.object(client.session, "request") as mock_request:
            mock_request.return_value.json.return_value = mock_comments
            mock_request.return_value.status_code = 200
            mock_request.return_value.raise_for_status = Mock()

            result = client.add_comment("PROJ-123", "Test comment")

            assert result is None
            mock_request.assert_called_once()

    def test_get_transitions(self, client):
        mock_response = {
            "transitions": [
                {"id": "11", "name": "To Do"},
                {"id": "21", "name": "In Progress"},
            ]
        }

        with patch.object(client.session, "request") as mock_request:
            mock_request.return_value.json.return_value = mock_response
            mock_request.return_value.status_code = 200
            mock_request.return_value.raise_for_status = Mock()

            result = client.get_transitions("PROJ-123")

            assert len(result) == 2
            assert result[0]["id"] == "11"

    def test_transition_issue(self, client):
        mock_issue = {"fields": {"status": {"name": "To Do"}}}
        mock_transitions = {
            "transitions": [
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}}
            ]
        }

        with patch.object(client.session, "request") as mock_request:
            mock_request.side_effect = [
                Mock(json=Mock(return_value=mock_issue), status_code=200, raise_for_status=Mock()),
                Mock(json=Mock(return_value=mock_transitions), status_code=200, raise_for_status=Mock()),
                Mock(status_code=204, raise_for_status=Mock()),
            ]

            client.transition_issue("PROJ-123", "21")

            assert mock_request.call_count == 3

    def test_transition_issue_idempotent(self, client):
        """Test that transition is skipped if already in target status."""
        mock_issue = {"fields": {"status": {"name": "In Progress"}}}
        mock_transitions = {
            "transitions": [
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}}
            ]
        }

        with patch.object(client.session, "request") as mock_request:
            mock_request.side_effect = [
                Mock(json=Mock(return_value=mock_issue), status_code=200, raise_for_status=Mock()),
                Mock(json=Mock(return_value=mock_transitions), status_code=200, raise_for_status=Mock()),
            ]

            client.transition_issue("PROJ-123", "21")

            # Should only call get_issue and get_transitions, not POST transition
            assert mock_request.call_count == 2

    def test_retry_on_429(self, client):
        """Test retry logic on rate limit response."""
        with patch.object(client.session, "request") as mock_request:
            mock_request.side_effect = [
                Mock(status_code=429, headers={"Retry-After": "0"}, raise_for_status=Mock()),
                Mock(json=Mock(return_value={"key": "PROJ-123"}), status_code=200, raise_for_status=Mock()),
            ]

            result = client.get_issue("PROJ-123")

            assert result == {"key": "PROJ-123"}
            assert mock_request.call_count == 2

    def test_retry_on_5xx(self, client):
        """Test retry logic on server error response."""
        with patch.object(client.session, "request") as mock_request:
            mock_request.side_effect = [
                Mock(status_code=503, headers={}, raise_for_status=Mock(side_effect=Exception("503"))),
                Mock(json=Mock(return_value={"key": "PROJ-123"}), status_code=200, raise_for_status=Mock()),
            ]

            result = client.get_issue("PROJ-123")

            assert result == {"key": "PROJ-123"}
            assert mock_request.call_count == 2

    def test_add_worklog(self, client):
        mock_worklog = {"id": "10001", "timeSpent": "1h"}

        with patch.object(client.session, "request") as mock_request:
            mock_request.return_value.json.return_value = mock_worklog
            mock_request.return_value.status_code = 201
            mock_request.return_value.raise_for_status = Mock()

            result = client.add_worklog("PROJ-123", "1h", "Test worklog")

            assert result == mock_worklog


class TestMRProcessor:
    """Tests for MRProcessor class."""

    @pytest.fixture
    def config(self):
        return Mock()

    @pytest.fixture
    def jira_client(self):
        client = Mock(spec=JiraClient)
        client.get_issue.return_value = {"fields": {"status": {"name": "To Do"}}}
        client.get_transitions.return_value = [
            {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
            {"id": "31", "name": "Done", "to": {"name": "Done"}},
        ]
        client.add_comment.return_value = {"id": "10001"}
        return client

    @pytest.fixture
    def processor(self, config, jira_client):
        return MRProcessor(config, jira_client)

    def test_extract_jira_issue_key_from_title(self, processor):
        mr = MergeRequest(
            iid=1,
            project_id=1,
            source_branch="feature",
            target_branch="main",
            title="PROJ-123: Add new feature",
            description=None,
            state=MRState.OPENED,
            web_url="https://gitlab.com/proj/-/merge_requests/1",
            author={"name": "Test"},
        )

        key = processor._extract_jira_issue_key(mr)
        assert key == "PROJ-123"

    def test_extract_jira_issue_key_from_description(self, processor):
        mr = MergeRequest(
            iid=1,
            project_id=1,
            source_branch="feature",
            target_branch="main",
            title="Add new feature",
            description="This implements PROJ-456",
            state=MRState.OPENED,
            web_url="https://gitlab.com/proj/-/merge_requests/1",
            author={"name": "Test"},
        )

        key = processor._extract_jira_issue_key(mr)
        assert key == "PROJ-456"

    def test_extract_jira_issue_key_not_found(self, processor):
        mr = MergeRequest(
            iid=1,
            project_id=1,
            source_branch="feature",
            target_branch="main",
            title="Add new feature",
            description="No issue key here",
            state=MRState.OPENED,
            web_url="https://gitlab.com/proj/-/merge_requests/1",
            author={"name": "Test"},
        )

        key = processor._extract_jira_issue_key(mr)
        assert key is None

    def test_process_mr_adds_comment(self, processor, jira_client):
        mr = MergeRequest(
            iid=1,
            project_id=1,
            source_branch="feature",
            target_branch="main",
            title="PROJ-123: Add new feature",
            description="Test description",
            state=MRState.OPENED,
            web_url="https://gitlab.com/proj/-/merge_requests/1",
            author={"name": "Test"},
        )
        commits = [
            Commit(
                id="abc123",
                message="Add feature",
                author_name="Test",
                author_email="test@example.com",
                timestamp="2024-01-01T00:00:00Z",
            )
        ]

        result = processor.process_mr(mr, commits)

        assert result["success"] is True
        assert result["issue_key"] == "PROJ-123"
        assert result["comment_added"] is True
        jira_client.add_comment.assert_called_once()

    def test_process_mr_applies_transition(self, processor, jira_client):
        mr = MergeRequest(
            iid=1,
            project_id=1,
            source_branch="feature",
            target_branch="main",
            title="PROJ-123: Add new feature",
            description="Test description",
            state=MRState.OPENED,
            web_url="https://gitlab.com/proj/-/merge_requests/1",
            author={"name": "Test"},
        )
        commits = []

        result = processor.process_mr(mr, commits)

        assert result["transition_applied"] is True
        jira_client.transition_issue.assert_called_once_with("PROJ-123", "21")

    def test_process_mr_no_issue_key(self, processor, jira_client):
        mr = MergeRequest(
            iid=1,
            project_id=1,
            source_branch="feature",
            target_branch="main",
            title="Add new feature",
            description=None,
            state=MRState.OPENED,
            web_url="https://gitlab.com/proj/-/merge_requests/1",
            author={"name": "Test"},
        )
        commits = []

        result = processor.process_mr(mr, commits)

        assert result["success"] is False
        assert result["issue_key"] is None
        jira_client.add_comment.assert_not_called()
        jira_client.transition_issue.assert_not_called()

    def test_transition_mapping_open_to_in_progress(self):
        assert MR_TO_JIRA_TRANSITION[MRState.OPENED] == "In Progress"

    def test_transition_mapping_approved_to_review(self):
        assert MR_TO_JIRA_TRANSITION[MRState.APPROVED] == "Review"

    def test_transition_mapping_merged_to_done(self):
        assert MR_TO_JIRA_TRANSITION[MRState.MERGED] == "Done"

    def test_generate_ai_summary(self, processor):
        mr = MergeRequest(
            iid=42,
            project_id=1,
            source_branch="feature/new",
            target_branch="main",
            title="Add amazing feature",
            description="This is a great feature",
            state=MRState.OPENED,
            web_url="https://gitlab.com/proj/-/merge_requests/42",
            author={"name": "John Doe"},
        )
        commits = [
            Commit(
                id="abc123",
                message="Initial commit",
                author_name="John",
                author_email="john@example.com",
                timestamp="2024-01-01T00:00:00Z",
            )
        ]

        summary = processor._generate_ai_summary(mr, commits)

        assert "AI Summary for MR !42" in summary
        assert "Add amazing feature" in summary
        assert "feature/new" in summary
        assert "main" in summary
        assert "John Doe" in summary
        assert "Initial commit" in summary
        assert "This is a great feature" in summary
