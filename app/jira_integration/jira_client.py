"""Jira API client with retry logic and idempotent operations."""

import logging
import time
from typing import Any, Optional

import requests

from app.jira_integration.config import JiraConfig

logger = logging.getLogger(__name__)


def find_transition_id(transitions: list[dict[str, Any]], name: str) -> Optional[str]:
    """
    Find transition ID by name.

    Args:
        transitions: List of available transitions from Jira API.
        name: Transition name to find (case-insensitive).

    Returns:
        Transition ID if found, None otherwise.
    """
    name_lower = name.lower()
    for transition in transitions:
        if transition.get("name", "").lower() == name_lower:
            return transition["id"]
    return None


class JiraClient:
    """
    Jira REST API client with Basic authentication.

    Supports retry logic for 429 and 5xx errors.
    All operations are idempotent.
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds

    def __init__(self, config: JiraConfig, use_bearer_auth: bool = False):
        """
        Initialize Jira client.

        Args:
            config: Jira configuration with URL and credentials.
            use_bearer_auth: Use Bearer token auth instead of Basic (default: False).
        """
        self.config = config
        self.base_url = config.base_api_url
        self.session = requests.Session()
        
        # Handle authentication
        if use_bearer_auth:
            # Bearer token authentication (for Jira Cloud/Corporate)
            self.session.headers.update({
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            })
        else:
            # Basic authentication with email:token
            self.session.auth = (config.email, config.token)
            
            self.session.headers.update({
                "Accept": "application/json",
                "Content-Type": "application/json",
            })

    def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, etc.).
            endpoint: API endpoint (relative to base_api_url, e.g., "myself" or "issue/PROJ-123").
            json: JSON payload for request body.
            params: Query parameters.

        Returns:
            Parsed JSON response or None for 204 No Content.

        Raises:
            requests.RequestException: If all retries fail.
        """
        # base_api_url already includes /rest/api/3, just add endpoint
        url = f"{self.base_url}/{endpoint}"
        
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                )

                # DEBUG: Print response info
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Jira API {method} {url}: {response.status_code}")
                logger.debug(f"Response headers: {dict(response.headers)}")
                logger.debug(f"Response body (first 500 chars): {response.text[:500]}")

                # Handle rate limiting and server errors with retry
                if response.status_code in (429, *range(500, 600)):
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else self.RETRY_DELAY * (attempt + 1)
                    logger.warning(
                        "Jira API returned %s, retrying in %.1fs (attempt %d/%d)",
                        response.status_code,
                        delay,
                        attempt + 1,
                        self.MAX_RETRIES,
                    )
                    time.sleep(delay)
                    continue

                # Check if response is JSON
                content_type = response.headers.get("Content-Type", "")
                if "application/json" not in content_type:
                    logger.warning(f"Response is not JSON: {content_type}")
                    logger.warning(f"Response: {response.text[:200]}")

                response.raise_for_status()

                # Handle 204 No Content
                if response.status_code == 204:
                    return None

                return response.json()

            except requests.RequestException as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY * (attempt + 1)
                    logger.warning(
                        "Jira API request failed: %s, retrying in %.1fs (attempt %d/%d)",
                        e,
                        delay,
                        attempt + 1,
                        self.MAX_RETRIES,
                    )
                    time.sleep(delay)
                else:
                    logger.error("Jira API request failed after %d attempts: %s", self.MAX_RETRIES, e)
                    raise

        # Should not reach here, but just in case
        raise last_error or requests.RequestException("Max retries exceeded")

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        """
        Get Jira issue by key.

        Args:
            issue_key: Jira issue key (e.g., "PROJ-123").

        Returns:
            Issue data as dictionary.
        """
        logger.info("Fetching Jira issue: %s", issue_key)
        return self._request("GET", f"issue/{issue_key}")

    def add_comment(self, issue_key: str, text: str) -> Optional[dict[str, Any]]:
        """
        Add comment to Jira issue.

        Idempotent: checks for duplicate comments before adding.

        Args:
            issue_key: Jira issue key (e.g., "PROJ-123").
            text: Comment text.

        Returns:
            Created comment data or None if duplicate exists.
        """
        logger.info("Adding comment to Jira issue: %s", issue_key)

        # Check for duplicate comment (idempotency)
        existing_comments = self._request("GET", f"issue/{issue_key}/comment")
        if existing_comments and "comments" in existing_comments:
            for comment in existing_comments["comments"]:
                if comment.get("body", {}).get("text") == text:
                    logger.info("Duplicate comment found for %s, skipping", issue_key)
                    return None

        # Add new comment (API v2 format)
        # Jira Server/Data Center uses simple "body" field, not rich text
        result = self._request(
            "POST",
            f"issue/{issue_key}/comment",
            json={"body": text},
        )

        if result:
            comment_id = result.get("id", "unknown")
            logger.info("Added comment %s to Jira issue: %s", comment_id, issue_key)

        return result

    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get available transitions for an issue.

        Args:
            issue_key: Jira issue key (e.g., "PROJ-123").

        Returns:
            List of available transitions.
        """
        logger.info("Fetching transitions for Jira issue: %s", issue_key)
        result = self._request("GET", f"issue/{issue_key}/transitions")
        return result.get("transitions", []) if result else []

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        """
        Transition issue to a new status.

        Idempotent: checks current status before transitioning.

        Args:
            issue_key: Jira issue key (e.g., "PROJ-123").
            transition_id: ID of the transition to execute.
        """
        logger.info("Transitioning Jira issue %s with transition %s", issue_key, transition_id)

        # Get current issue status (idempotency check)
        issue = self.get_issue(issue_key)
        current_status = issue.get("fields", {}).get("status", {}).get("name", "")

        # Get available transitions
        transitions = self.get_transitions(issue_key)
        target_transition = next(
            (t for t in transitions if t["id"] == transition_id),
            None,
        )

        if not target_transition:
            logger.warning("Transition %s not available for issue %s", transition_id, issue_key)
            return

        target_status = target_transition.get("to", {}).get("name", "")

        # Skip if already in target status
        if current_status.lower() == target_status.lower():
            logger.info(
                "Issue %s already in status '%s', skipping transition %s",
                issue_key,
                current_status,
                transition_id,
            )
            return

        # Execute transition
        self._request(
            "POST",
            f"issue/{issue_key}/transitions",
            json={"transition": {"id": transition_id}},
        )

        logger.info(
            "Transitioned Jira issue %s from '%s' to '%s' using transition %s",
            issue_key,
            current_status,
            target_status,
            transition_id,
        )

    def add_worklog(
        self,
        issue_key: str,
        time_spent: str,
        comment: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Add worklog entry to Jira issue.

        Args:
            issue_key: Jira issue key (e.g., "PROJ-123").
            time_spent: Time spent in Jira format (e.g., "1h", "30m", "1d").
            comment: Optional worklog comment.

        Returns:
            Created worklog data.
        """
        logger.info("Adding worklog to Jira issue: %s (%s)", issue_key, time_spent)

        payload: dict[str, Any] = {"timeSpent": time_spent}
        if comment:
            payload["comment"] = {"type": "text", "text": comment}

        result = self._request("POST", f"issue/{issue_key}/worklog", json=payload)
        logger.info("Added worklog to Jira issue: %s", issue_key)
        return result
