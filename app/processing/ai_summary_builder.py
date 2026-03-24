"""AI Summary Builder for preparing commit data for AI summarization."""

from typing import Dict, List, Any, Optional
from datetime import datetime
from app.shared.models import Commit
from app.shared.logging_config import get_logger
from app.processing.git_context_service import GitContext

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
        git_context: Optional[GitContext] = None,
        mr_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build structured input for AI summarization.

        Args:
            jira_issue: The Jira issue key.
            commits: List of commits belonging to this Jira issue.
            git_context: Optional Git context with changed files, diff summaries, and MR info.

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
                "branch": "feature/PROJ-123-login",
                "changed_files": ["auth_service.py", "login_controller.ts"],
                "diff_summary": [
                    "auth_service.py: +20 lines added, -3 lines removed",
                    "login_controller.ts: +15 lines added"
                ],
                "merge_request_title": "Fix login issues",
                "merge_request_description": "This MR fixes the login redirect bug..."
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

        # Get repository and branch info from Git context or first commit's branch relationship
        repository = None
        branch_name = None
        
        if git_context:
            repository = git_context.repository_name
            branch_name = git_context.branch_name
        elif commits and commits[0].branch:
            # Get branch info from relationship
            branch_obj = commits[0].branch
            branch_name = branch_obj.name if branch_obj else None
            # Repository would need to come from the branch's relationship
            if branch_obj and hasattr(branch_obj, 'repository'):
                repository = branch_obj.repository.name if branch_obj.repository else None

        summary_input = {
            "jira_issue": jira_issue,
            "commit_messages": commit_messages,
            "authors": authors,
            "time_range": time_range,
            "commit_count": len(commits),
            "repository": repository,
            "branch": branch_name,
        }

        # Add Git context if available
        if git_context:
            summary_input["changed_files"] = git_context.changed_files
            summary_input["diff_summary"] = git_context.diff_summary
            summary_input["merge_request_title"] = git_context.merge_request.title if git_context.merge_request else ""
            summary_input["merge_request_description"] = git_context.merge_request.description if git_context.merge_request else ""
            summary_input["merge_request_author"] = git_context.merge_request.author if git_context.merge_request else ""
            logger.info(
                f"Added Git context: {len(git_context.changed_files)} files, "
                f"MR: {git_context.merge_request.title if git_context.merge_request else 'None'}"
            )
        else:
            # Provide empty defaults
            summary_input["changed_files"] = []
            summary_input["diff_summary"] = []
            summary_input["merge_request_title"] = ""
            # Use mr_description if provided (from event payload)
            summary_input["merge_request_description"] = mr_description or ""
            summary_input["merge_request_author"] = ""

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
        changed_files = summary_input.get("changed_files", [])
        diff_summary = summary_input.get("diff_summary", [])
        merge_request_title = summary_input.get("merge_request_title", "")
        merge_request_description = summary_input.get("merge_request_description", "")
        reviewers = summary_input.get("reviewers", [])

        # Build the prompt in Russian
        prompt_parts = [
            f"Сгенерируй краткий прогресс-апдейт для Jira задачи {jira_issue}.",
            "",
        ]

        # Add MR description if available
        if merge_request_description:
            prompt_parts.append("📋 **Описание Merge Request:**")
            prompt_parts.append(merge_request_description[:500])  # Truncate
            prompt_parts.append("")

        # Add commit messages
        if commit_messages:
            prompt_parts.append("📝 **Коммиты (список сообщений):**")
            for msg in commit_messages:
                prompt_parts.append(f"- {msg}")
            prompt_parts.append("")

        # Add changed files
        if changed_files:
            prompt_parts.append("📁 **Изменённые файлы:**")
            for f in changed_files[:15]:
                prompt_parts.append(f"- {f}")
            prompt_parts.append("")

        # Add diff summary
        if diff_summary:
            prompt_parts.append("📊 **Изменения (строки кода):**")
            for d in diff_summary[:15]:
                prompt_parts.append(f"- {d}")
            prompt_parts.append("")

        # Add MR title
        if merge_request_title:
            prompt_parts.append(f"🔀 **Merge Request:** {merge_request_title}")
            prompt_parts.append("")

        # Add reviewer username (for mention)
        if reviewers:
            reviewer_usernames = [r.get("username", "") for r in reviewers if r.get("username")]
            if reviewer_usernames:
                prompt_parts.append(f"👥 **Ревьювер:** {', '.join(reviewer_usernames)}")
                prompt_parts.append("")

        # Add time range
        if time_range.get("start") and time_range.get("end"):
            prompt_parts.append(f"⏰ **Период:** {time_range['start'][:10]} — {time_range['end'][:10]}")
            prompt_parts.append("")

        # Requirements
        prompt_parts.append("Требования к ответу:")
        prompt_parts.append("- Пиши ТОЛЬКО на русском")
        prompt_parts.append("- 2-4 предложения")
        prompt_parts.append("- Деловой стиль")
        prompt_parts.append("- Без \"Авторы:\", \"Author:\"")
        prompt_parts.append("- Без упоминания других Jira задач")

        return "\n".join(prompt_parts)
