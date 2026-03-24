"""Jira status transition service.

Maps GitLab MR states to Jira status transitions.
"""

from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from app.shared.logging_config import get_logger

logger = get_logger("jira_transitions")


@dataclass
class StatusMapping:
    """Mapping from GitLab MR state to Jira transition."""
    gitlab_state: str
    jira_transition_name: str
    comment_template: Optional[str] = None


# Default status mappings
DEFAULT_STATUS_MAPPINGS: List[StatusMapping] = [
    # MR opened → Move to Review
    StatusMapping(
        gitlab_state="opened",
        jira_transition_name="Ревью",
        comment_template="Merge Request отправлен на ревью: {mr_url}"
    ),
    # MR approved → Move to Testing
    StatusMapping(
        gitlab_state="approved",
        jira_transition_name="Ожидает тестирования",
        comment_template="✅ Ревью пройдено. Задача готова к тестированию."
    ),
    # MR merged → Move to Done
    StatusMapping(
        gitlab_state="merged",
        jira_transition_name="Done",
        comment_template="✅ Merge Request принят в основную ветку. Задача завершена."
    ),
    # MR closed → Move back to To Do
    StatusMapping(
        gitlab_state="closed",
        jira_transition_name="Отменено",
        comment_template="❌ Merge Request закрыт. Задача возвращена в бэклог."
    ),
]


class JiraTransitionService:
    """Service for transitioning Jira issues based on GitLab MR state."""

    def __init__(self, jira_client, custom_mappings: Optional[List[StatusMapping]] = None):
        """
        Initialize transition service.
        
        Args:
            jira_client: JiraClient instance for API calls
            custom_mappings: Optional custom status mappings
        """
        self.jira_client = jira_client
        self.mappings = custom_mappings or DEFAULT_STATUS_MAPPINGS
        logger.info(f"Initialized JiraTransitionService with {len(self.mappings)} mappings")

    def get_transition_for_state(self, gitlab_state: str) -> Optional[StatusMapping]:
        """
        Get Jira transition for GitLab MR state.
        
        Args:
            gitlab_state: GitLab MR state (opened, approved, merged, closed)
            
        Returns:
            StatusMapping or None if no mapping found
        """
        for mapping in self.mappings:
            if mapping.gitlab_state.lower() == gitlab_state.lower():
                return mapping
        return None

    def transition_issue(
        self,
        issue_key: str,
        gitlab_state: str,
        mr_url: Optional[str] = None,
        mr_title: Optional[str] = None,
    ) -> bool:
        """
        Transition Jira issue based on GitLab MR state.
        
        Args:
            issue_key: Jira issue key (e.g., "MPTPSUPP-27204")
            gitlab_state: GitLab MR state
            mr_url: Optional MR URL for comment
            mr_title: Optional MR title for logging
            
        Returns:
            True if transition was successful, False otherwise
        """
        mapping = self.get_transition_for_state(gitlab_state)
        
        if not mapping:
            logger.info(f"No Jira transition mapping for GitLab state: {gitlab_state}")
            return False
        
        logger.info(f"Transitioning {issue_key} to '{mapping.jira_transition_name}' based on MR state: {gitlab_state}")
        
        # Get available transitions
        transitions = self.jira_client.get_transitions(issue_key)
        
        # Find matching transition by name
        transition_id = self._find_transition_by_name(transitions, mapping.jira_transition_name)
        
        if not transition_id:
            logger.warning(f"Transition '{mapping.jira_transition_name}' not found for issue {issue_key}")
            logger.debug(f"Available transitions: {[t.get('name') for t in transitions]}")
            return False
        
        # Execute transition
        try:
            self.jira_client.transition_issue(issue_key, transition_id)
            logger.info(f"Successfully transitioned {issue_key} to '{mapping.jira_transition_name}'")
            
            # Add comment if template provided
            if mapping.comment_template:
                comment = mapping.comment_template.format(
                    mr_url=mr_url or "N/A",
                    mr_title=mr_title or "N/A"
                )
                self.jira_client.add_comment(issue_key, comment)
                logger.info(f"Added comment to {issue_key}: {comment[:100]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to transition {issue_key}: {e}")
            return False

    def _find_transition_by_name(
        self,
        transitions: List[Dict[str, Any]],
        name: str
    ) -> Optional[str]:
        """
        Find transition ID by name.
        
        Args:
            transitions: List of available transitions from Jira API
            name: Transition name to find
            
        Returns:
            Transition ID or None if not found
        """
        name_lower = name.lower()
        
        for transition in transitions:
            transition_name = transition.get("name", "").lower()
            
            # Exact match
            if transition_name == name_lower:
                return transition.get("id")
            
            # Partial match (e.g., "Ревью" matches "На ревью")
            if name_lower in transition_name or transition_name in name_lower:
                return transition.get("id")
        
        return None
