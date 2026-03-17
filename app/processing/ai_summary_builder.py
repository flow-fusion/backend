"""AI Summary Builder for preparing commit data for AI summarization."""

from typing import Dict, List, Any, Optional
from datetime import datetime
from app.models import Commit
from app.core.logging_config import get_logger

logger = get_logger("ai_summary_builder")


class AISummaryBuilder:
    """
    Builder for creating structured AI summary input data.
    
    Responsibilities:
    - Transform commit data into AI-ready format
    - Aggregate commit messages
    - Collect metadata (authors, time range)
    - Generate structured JSON for AI processing
    """

    def __init__(self):
        pass

    def build_summary_input(
        self,
        jira_issue: str,
        commits: List[Commit],
    ) -> Dict[str, Any]:
        """
        Build structured input for AI summarization.
        
        Args:
            jira_issue: The Jira issue key.
            commits: List of commits belonging to this Jira issue.
            
        Returns:
            Dictionary containing structured data for AI processing.
            
        Example output:
            {
                "jira_issue": "PROJ-123",
                "commit_messages": [
                    "fix login crash",
                    "add retry logic",
                    "refactor auth service"
                ],
                "authors": ["Ivan"],
                "time_range": {
                    "start": "2024-01-15T10:00:00Z",
                    "end": "2024-01-15T10:20:00Z"
                },
                "commit_count": 3,
                "repository": "repo_name",
                "branch": "feature/PROJ-123-login"
            }
        """
        if not commits:
            logger.warning(f"No commits provided for Jira issue {jira_issue}")
            return self._create_empty_summary(jira_issue)

        # Extract commit messages (cleaned and deduplicated)
        commit_messages = self._extract_commit_messages(commits)
        
        # Extract unique authors
        authors = self._extract_authors(commits)
        
        # Calculate time range
        time_range = self._calculate_time_range(commits)
        
        # Get repository and branch info
        repository = commits[0].repository if commits else None
        branch = commits[0].branch if commits else None
        
        summary_input = {
            "jira_issue": jira_issue,
            "commit_messages": commit_messages,
            "authors": authors,
            "time_range": time_range,
            "commit_count": len(commits),
            "repository": repository,
            "branch": branch,
        }
        
        logger.info(
            f"Built AI summary input for {jira_issue}: "
            f"{len(commit_messages)} commits from {len(authors)} author(s)"
        )
        
        return summary_input

    def _extract_commit_messages(self, commits: List[Commit]) -> List[str]:
        """
        Extract and clean commit messages.
        
        Args:
            commits: List of Commit objects.
            
        Returns:
            List of cleaned commit messages.
        """
        messages = []
        seen_messages = set()
        
        for commit in commits:
            if not commit.message:
                continue
                
            # Clean the message
            cleaned = self._clean_commit_message(commit.message)
            
            # Skip empty or duplicate messages
            if not cleaned or cleaned in seen_messages:
                continue
            
            seen_messages.add(cleaned)
            messages.append(cleaned)
        
        return messages

    def _clean_commit_message(self, message: str) -> str:
        """
        Clean a commit message for AI processing.
        
        Args:
            message: Raw commit message.
            
        Returns:
            Cleaned commit message.
        """
        if not message:
            return ""
        
        # Strip whitespace
        cleaned = message.strip()
        
        # Remove common prefixes that don't add value
        prefixes_to_remove = [
            "[",
            "WIP:",
            "WIP ",
            "Draft:",
            "Draft ",
        ]
        
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        
        # Remove trailing punctuation normalization
        cleaned = cleaned.rstrip(".")
        
        return cleaned

    def _extract_authors(self, commits: List[Commit]) -> List[str]:
        """
        Extract unique author names from commits.
        
        Args:
            commits: List of Commit objects.
            
        Returns:
            List of unique author names.
        """
        authors = set()
        
        for commit in commits:
            if commit.author:
                # Handle both name and email formats
                author = commit.author.strip()
                if "@" in author:
                    # Extract name from email format "Name <email>"
                    if "<" in author:
                        author = author.split("<")[0].strip()
                    else:
                        # Just email, use as-is or extract username
                        author = author.split("@")[0]
                
                if author:
                    authors.add(author)
        
        return sorted(list(authors))

    def _calculate_time_range(self, commits: List[Commit]) -> Dict[str, Optional[str]]:
        """
        Calculate the time range covered by commits.
        
        Args:
            commits: List of Commit objects.
            
        Returns:
            Dictionary with start and end timestamps.
        """
        timestamps = [
            c.timestamp for c in commits
            if c.timestamp is not None
        ]
        
        if not timestamps:
            return {
                "start": None,
                "end": None,
            }
        
        start_time = min(timestamps)
        end_time = max(timestamps)
        
        return {
            "start": start_time.isoformat() if start_time else None,
            "end": end_time.isoformat() if end_time else None,
        }

    def _create_empty_summary(self, jira_issue: str) -> Dict[str, Any]:
        """
        Create an empty summary structure.
        
        Args:
            jira_issue: The Jira issue key.
            
        Returns:
            Empty summary dictionary.
        """
        return {
            "jira_issue": jira_issue,
            "commit_messages": [],
            "authors": [],
            "time_range": {
                "start": None,
                "end": None,
            },
            "commit_count": 0,
            "repository": None,
            "branch": None,
        }

    def build_for_batch(
        self,
        jira_issue: str,
        commit_batches: List[List[Commit]],
    ) -> List[Dict[str, Any]]:
        """
        Build AI summary inputs for multiple commit batches.
        
        Args:
            jira_issue: The Jira issue key.
            commit_batches: List of commit batches.
            
        Returns:
            List of summary input dictionaries.
        """
        summaries = []
        
        for i, batch in enumerate(commit_batches):
            if not batch:
                continue
                
            summary = self.build_summary_input(jira_issue, batch)
            summary["batch_index"] = i
            summary["total_batches"] = len(commit_batches)
            summaries.append(summary)
        
        return summaries

    def format_for_ai(self, summary_input: Dict[str, Any]) -> str:
        """
        Format summary input as a prompt for AI processing.
        
        This method prepares the data in a format suitable for
        sending to an AI model for natural language generation.
        
        Args:
            summary_input: Dictionary from build_summary_input().
            
        Returns:
            Formatted prompt string for AI.
        """
        jira_issue = summary_input.get("jira_issue", "Unknown")
        commit_messages = summary_input.get("commit_messages", [])
        authors = summary_input.get("authors", [])
        time_range = summary_input.get("time_range", {})
        commit_count = summary_input.get("commit_count", 0)
        
        # Build the prompt
        prompt_parts = [
            f"Generate a progress update for Jira issue {jira_issue}.",
            "",
            "Summary of work completed:",
            "",
        ]
        
        if commit_count > 0:
            prompt_parts.append(f"Number of commits: {commit_count}")
            
            if authors:
                prompt_parts.append(f"Authors: {', '.join(authors)}")
            
            if time_range.get("start") and time_range.get("end"):
                prompt_parts.append(
                    f"Time range: {time_range['start']} to {time_range['end']}"
                )
            
            prompt_parts.append("")
            prompt_parts.append("Commit messages:")
            for i, msg in enumerate(commit_messages, 1):
                prompt_parts.append(f"  {i}. {msg}")
        else:
            prompt_parts.append("No commits to summarize.")
        
        prompt_parts.append("")
        prompt_parts.append(
            "Please generate a concise, professional summary of the work completed. "
            "Focus on what was accomplished and any notable changes."
        )
        
        return "\n".join(prompt_parts)
