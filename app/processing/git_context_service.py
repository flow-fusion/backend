"""Git Context Service for enriching AI summaries with GitLab data."""

import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from functools import lru_cache
import httpx
from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models import Commit

logger = get_logger("git_context_service")


@dataclass
class DiffSummary:
    """Summarized diff information for a file."""

    filename: str
    additions: int
    deletions: int
    status: str  # added, modified, deleted, renamed

    def to_summary_line(self) -> str:
        """Create a compact summary line for AI."""
        parts = [f"{self.filename}:"]
        if self.additions > 0:
            parts.append(f"+{self.additions} lines added")
        if self.deletions > 0:
            parts.append(f"-{self.deletions} lines removed")
        return " ".join(parts)


@dataclass
class MergeRequestInfo:
    """Merge request information."""

    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    state: Optional[str] = None
    web_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "state": self.state,
            "web_url": self.web_url,
        }


@dataclass
class GitContext:
    """Complete Git context for a set of commits."""

    changed_files: List[str] = field(default_factory=list)
    diff_summary: List[DiffSummary] = field(default_factory=list)
    merge_request: Optional[MergeRequestInfo] = None
    repository_name: Optional[str] = None
    branch_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for AI summary input."""
        return {
            "changed_files": self.changed_files,
            "diff_summary": [ds.to_summary_line() for ds in self.diff_summary],
            "merge_request_title": self.merge_request.title if self.merge_request else "",
            "merge_request_description": self.merge_request.description if self.merge_request else "",
            "merge_request_author": self.merge_request.author if self.merge_request else "",
            "repository_name": self.repository_name,
            "branch_name": self.branch_name,
        }


class GitContextService:
    """
    Service for loading Git context from GitLab API.

    Responsibilities:
    - Load commit metadata from GitLab API
    - Load changed files for commits
    - Load merge requests associated with branches
    - Generate summarized diff descriptions
    - Cache API responses to reduce calls
    """

    def __init__(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
        gitlab_base_url: Optional[str] = None,
        gitlab_api_token: Optional[str] = None,
    ):
        settings = get_settings()
        
        self.base_url = gitlab_base_url or settings.GITLAB_BASE_URL
        self.api_token = gitlab_api_token or settings.GITLAB_API_TOKEN
        self.timeout = settings.GITLAB_API_TIMEOUT
        self.retry_count = settings.GITLAB_API_RETRY_COUNT

        self._client = http_client
        self._owns_client = http_client is None

        # Caches
        self._commit_cache: Dict[str, Dict[str, Any]] = {}
        self._diff_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._mr_cache: Dict[str, MergeRequestInfo] = {}

    async def __aenter__(self):
        """Async context manager entry."""
        if self._owns_client:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._get_headers(),
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._owns_client and self._client:
            await self._client.aclose()

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for GitLab API requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        elif hasattr(self, "_client") and self._client:
            # Check if token is in environment
            import os
            if token := os.getenv("GITLAB_API_TOKEN"):
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get_project_id(self, repository: str) -> Optional[str]:
        """
        Extract or resolve project ID from repository name.
        
        For URL-encoded project paths like "group/project", 
        GitLab API accepts them as project_id.
        """
        if not repository:
            return None
        
        # If it's already a numeric ID, return as-is
        if repository.isdigit():
            return repository
        
        # Otherwise, use as URL-encoded path
        return repository

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Make a GitLab API request with retry logic.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            JSON response or None on failure
        """
        if not self._client:
            logger.error("HTTP client not initialized")
            return None

        url = f"{self.base_url}/api/v4/{endpoint}"
        
        for attempt in range(self.retry_count):
            try:
                response = await self._client.request(method, url, params=params)
                response.raise_for_status()
                return response.json()
                
            except httpx.TimeoutException as e:
                logger.warning(f"GitLab API timeout (attempt {attempt + 1}/{self.retry_count}): {e}")
                if attempt == self.retry_count - 1:
                    return None
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.debug(f"GitLab API resource not found: {endpoint}")
                    return None
                logger.warning(f"GitLab API error (attempt {attempt + 1}/{self.retry_count}): {e}")
                if attempt == self.retry_count - 1:
                    return None
                    
            except Exception as e:
                logger.warning(f"GitLab API unexpected error (attempt {attempt + 1}/{self.retry_count}): {e}")
                if attempt == self.retry_count - 1:
                    return None

        return None

    async def get_commit_details(
        self,
        project_id: str,
        commit_sha: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get commit details from GitLab API.
        
        Args:
            project_id: GitLab project ID or path
            commit_sha: Commit SHA
            
        Returns:
            Commit details or None
        """
        # Check cache first
        cache_key = f"{project_id}:{commit_sha}"
        if cache_key in self._commit_cache:
            logger.debug(f"Commit {commit_sha[:8]} found in cache")
            return self._commit_cache[cache_key]

        endpoint = f"projects/{project_id}/repository/commits/{commit_sha}"
        result = await self._request("GET", endpoint)
        
        if result:
            self._commit_cache[cache_key] = result
            logger.debug(f"Cached commit details for {commit_sha[:8]}")
        
        return result

    async def get_commit_diff(
        self,
        project_id: str,
        commit_sha: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get commit diff from GitLab API.
        
        Args:
            project_id: GitLab project ID or path
            commit_sha: Commit SHA
            
        Returns:
            List of changed files with diffs or None
        """
        # Check cache first
        cache_key = f"{project_id}:{commit_sha}"
        if cache_key in self._diff_cache:
            logger.debug(f"Diff for {commit_sha[:8]} found in cache")
            return self._diff_cache[cache_key]

        endpoint = f"projects/{project_id}/repository/commits/{commit_sha}/diff"
        result = await self._request("GET", endpoint)
        
        if result:
            self._diff_cache[cache_key] = result
            logger.debug(f"Cached diff for {commit_sha[:8]}")
        
        return result

    async def get_merge_request_by_branch(
        self,
        project_id: str,
        branch: str,
    ) -> Optional[MergeRequestInfo]:
        """
        Get merge request for a branch from GitLab API.
        
        Args:
            project_id: GitLab project ID or path
            branch: Source branch name
            
        Returns:
            MergeRequestInfo or None
        """
        # Check cache first
        cache_key = f"{project_id}:{branch}"
        if cache_key in self._mr_cache:
            logger.debug(f"MR for branch {branch} found in cache")
            return self._mr_cache[cache_key]

        endpoint = f"projects/{project_id}/merge_requests"
        params = {"source_branch": branch, "state": "opened"}
        result = await self._request("GET", endpoint, params)
        
        if result and len(result) > 0:
            mr_data = result[0]  # Get first open MR
            mr_info = MergeRequestInfo(
                title=mr_data.get("title", ""),
                description=mr_data.get("description"),
                author=mr_data.get("author", {}).get("name") if mr_data.get("author") else None,
                state=mr_data.get("state"),
                web_url=mr_data.get("web_url"),
            )
            self._mr_cache[cache_key] = mr_info
            logger.debug(f"Cached MR for branch {branch}: {mr_info.title}")
            return mr_info
        
        return None

    def _summarize_diff(self, diff_data: List[Dict[str, Any]]) -> List[DiffSummary]:
        """
        Summarize diff data into compact format.
        
        Args:
            diff_data: Raw diff data from GitLab API
            
        Returns:
            List of DiffSummary objects
        """
        summaries = []
        
        for file_diff in diff_data:
            filename = file_diff.get("new_path") or file_diff.get("old_path") or "unknown"
            
            # Determine status
            if file_diff.get("new_file"):
                status = "added"
            elif file_diff.get("deleted_file"):
                status = "deleted"
            elif file_diff.get("renamed_file"):
                status = "renamed"
            else:
                status = "modified"
            
            # Count additions/deletions
            diff_text = file_diff.get("diff", "")
            additions = diff_text.count("\n+") if diff_text else 0
            deletions = diff_text.count("\n-") if diff_text else 0
            
            # Also use provided stats if available
            if "stats" in file_diff:
                additions = file_diff["stats"].get("additions", additions)
                deletions = file_diff["stats"].get("deletions", deletions)
            
            summary = DiffSummary(
                filename=filename,
                additions=additions,
                deletions=deletions,
                status=status,
            )
            summaries.append(summary)
        
        return summaries

    async def load_context(
        self,
        commits: List[Commit],
        project_id: Optional[str] = None,
    ) -> GitContext:
        """
        Load complete Git context for a list of commits.
        
        This is the main entry point for the service.
        
        Args:
            commits: List of Commit objects
            project_id: Optional GitLab project ID (auto-detected from commits if not provided)
            
        Returns:
            GitContext with all enriched data
        """
        if not commits:
            logger.debug("No commits provided for Git context")
            return GitContext()

        # Detect project ID from first commit
        if not project_id:
            first_commit = commits[0]
            if first_commit.repository:
                project_id = self._get_project_id(first_commit.repository)
        
        if not project_id:
            logger.warning("Cannot determine project ID, skipping Git context")
            return GitContext()

        logger.info(f"Loading Git context for project {project_id}, {len(commits)} commits")

        context = GitContext(
            repository_name=commits[0].repository if commits else None,
            branch_name=commits[0].branch if commits else None,
        )

        # Collect all changed files and diff summaries
        all_diff_summaries: List[DiffSummary] = []
        seen_files: set = set()

        for commit in commits:
            if not commit.commit_id:
                continue

            # Get commit diff
            diff_data = await self.get_commit_diff(project_id, commit.commit_id)
            
            if diff_data:
                summaries = self._summarize_diff(diff_data)
                for summary in summaries:
                    if summary.filename not in seen_files:
                        seen_files.add(summary.filename)
                        context.changed_files.append(summary.filename)
                    all_diff_summaries.append(summary)
        
        # Merge diff summaries for same files
        context.diff_summary = self._merge_diff_summaries(all_diff_summaries)

        # Load merge request info
        if commits[0].branch:
            mr_info = await self.get_merge_request_by_branch(project_id, commits[0].branch)
            if mr_info:
                context.merge_request = mr_info

        logger.info(
            f"Loaded Git context: {len(context.changed_files)} files, "
            f"{len(context.diff_summary)} diff summaries, "
            f"MR: {context.merge_request.title if context.merge_request else 'None'}"
        )

        return context

    def _merge_diff_summaries(
        self,
        summaries: List[DiffSummary],
    ) -> List[DiffSummary]:
        """
        Merge diff summaries for the same file.
        
        Args:
            summaries: List of DiffSummary objects
            
        Returns:
            Merged list with one entry per file
        """
        merged: Dict[str, DiffSummary] = {}
        
        for summary in summaries:
            if summary.filename in merged:
                # Aggregate additions and deletions
                existing = merged[summary.filename]
                existing.additions += summary.additions
                existing.deletions += summary.deletions
            else:
                merged[summary.filename] = DiffSummary(
                    filename=summary.filename,
                    additions=summary.additions,
                    deletions=summary.deletions,
                    status=summary.status,
                )
        
        # Sort by filename for consistent output
        return sorted(merged.values(), key=lambda s: s.filename)

    def clear_cache(self) -> None:
        """Clear all caches (useful for testing)."""
        self._commit_cache.clear()
        self._diff_cache.clear()
        self._mr_cache.clear()
        logger.debug("Git context caches cleared")


# Synchronous wrapper for non-async contexts
class GitContextServiceSync:
    """Synchronous wrapper for GitContextService."""

    def __init__(self):
        self._service: Optional[GitContextService] = None

    def load_context(
        self,
        commits: List[Commit],
        project_id: Optional[str] = None,
    ) -> GitContext:
        """Load Git context synchronously."""
        import asyncio
        
        async def _load():
            async with GitContextService() as service:
                return await service.load_context(commits, project_id)
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(_load())
