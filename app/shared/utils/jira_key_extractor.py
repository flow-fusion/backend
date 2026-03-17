"""Jira key extraction utility."""

import re
from typing import Optional


class JiraKeyExtractor:
    """
    Utility class for extracting Jira issue keys from branch names.

    Jira issue keys follow the pattern: PROJECT-123
    where PROJECT is uppercase letters and 123 is a number.
    """

    JIRA_KEY_PATTERN = re.compile(r"[A-Z]+-\d+")

    @classmethod
    def extract(cls, branch_name: str) -> Optional[str]:
        """Extract the first Jira issue key found in a branch name."""
        if not branch_name:
            return None

        match = cls.JIRA_KEY_PATTERN.search(branch_name)
        return match.group(0) if match else None

    @classmethod
    def extract_all(cls, branch_name: str) -> list[str]:
        """Extract all Jira issue keys found in a branch name."""
        if not branch_name:
            return []
        return cls.JIRA_KEY_PATTERN.findall(branch_name)

    @classmethod
    def is_valid_jira_key(cls, key: str) -> bool:
        """Validate if a string is a valid Jira issue key format."""
        if not key:
            return False
        return bool(cls.JIRA_KEY_PATTERN.fullmatch(key))

    @classmethod
    def extract_from_ref(cls, ref: str) -> Optional[str]:
        """Extract Jira issue key from a Git ref."""
        if not ref:
            return None
        branch_name = cls.extract_branch_name_from_ref(ref)
        return cls.extract(branch_name)

    @staticmethod
    def extract_branch_name_from_ref(ref: str) -> str:
        """Extract the branch name from a Git ref."""
        if not ref:
            return ""
        prefix = "refs/heads/"
        if ref.startswith(prefix):
            return ref[len(prefix):]
        return ref
