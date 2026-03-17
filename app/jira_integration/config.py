"""Configuration for Jira integration."""

import os
from dataclasses import dataclass
from typing import Tuple


@dataclass
class JiraConfig:
    """Jira API configuration."""

    url: str
    email: str
    token: str

    @classmethod
    def from_env(cls) -> "JiraConfig":
        """Load Jira configuration from environment variables."""
        return cls(
            url=os.environ["JIRA_URL"],
            email=os.environ["JIRA_EMAIL"],
            token=os.environ["JIRA_TOKEN"],
        )

    @property
    def auth(self) -> Tuple[str, str]:
        """Return Basic auth tuple (email, token)."""
        return (self.email, self.token)

    @property
    def base_api_url(self) -> str:
        """Return the base API URL for Jira REST API."""
        return f"{self.url}/rest/api/3"
