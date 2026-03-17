"""SQLAlchemy models for the application."""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()


class Event(Base):
    """
    Represents a normalized GitLab webhook event.
    
    Stored by the webhook receiver layer.
    """

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)  # push, merge_request, etc.
    payload_json = Column(JSON, nullable=False)  # Normalized event payload
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed = Column(Boolean, default=False, nullable=False, index=True)
    processing_error = Column(Text, nullable=True)  # Error message if processing failed
    retry_count = Column(Integer, default=0, nullable=False)

    # Relationships
    commits = relationship("Commit", back_populates="event", lazy="select")

    __table_args__ = (
        Index("idx_events_processed_created", "processed", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Event(id={self.id}, type={self.event_type}, processed={self.processed})>"


class Commit(Base):
    """
    Represents a Git commit associated with an event.
    """

    __tablename__ = "commits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commit_id = Column(String(64), nullable=False, index=True)  # Git commit hash
    message = Column(Text, nullable=True)  # Commit message
    author = Column(String(255), nullable=True)  # Author name/email
    timestamp = Column(DateTime, nullable=True)  # Commit timestamp
    branch = Column(String(255), nullable=True, index=True)  # Branch name
    repository = Column(String(255), nullable=True)  # Repository name
    jira_issue = Column(String(50), nullable=True, index=True)  # Extracted Jira issue key
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    processed = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    event = relationship("Event", back_populates="commits")

    __table_args__ = (
        Index("idx_commits_commit_id_branch", "commit_id", "branch", unique=True),
        Index("idx_commits_jira_processed", "jira_issue", "processed"),
    )

    def __repr__(self) -> str:
        return f"<Commit(id={self.commit_id[:8]}, jira={self.jira_issue})>"


class Branch(Base):
    """
    Represents a Git branch.
    """

    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    repository = Column(String(255), nullable=False)
    jira_issue = Column(String(50), nullable=True, index=True)  # Extracted from branch name
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_branches_name_repo", "name", "repository", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Branch(name={self.name})>"


class MergeRequest(Base):
    """
    Represents a GitLab Merge Request.
    """

    __tablename__ = "merge_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mr_id = Column(Integer, nullable=False, index=True)  # GitLab MR ID
    title = Column(String(500), nullable=True)
    source_branch = Column(String(255), nullable=True)
    target_branch = Column(String(255), nullable=True)
    state = Column(String(50), nullable=True)  # opened, merged, closed
    author = Column(String(255), nullable=True)
    jira_issue = Column(String(50), nullable=True, index=True)
    repository = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_mr_mr_id_repo", "mr_id", "repository", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MergeRequest(id={self.mr_id}, state={self.state})>"


class AISummary(Base):
    """
    Represents AI-ready summary input for a Jira issue.
    
    This table stores aggregated commit data prepared for AI summarization.
    The Jira integration layer will later read from this table.
    """

    __tablename__ = "ai_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jira_issue = Column(String(50), nullable=False, index=True)
    summary_input_json = Column(JSON, nullable=False)  # Structured input for AI
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed = Column(Boolean, default=False, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)  # When AI processing completed
    jira_comment_id = Column(Integer, nullable=True)  # ID of posted Jira comment

    # Batch metadata
    commit_count = Column(Integer, nullable=True)
    time_range_start = Column(DateTime, nullable=True)
    time_range_end = Column(DateTime, nullable=True)
    authors = Column(JSON, nullable=True)  # List of author names

    __table_args__ = (
        Index("idx_ai_summaries_issue_processed", "jira_issue", "processed"),
    )

    def __repr__(self) -> str:
        return f"<AISummary(jira={self.jira_issue}, processed={self.processed})>"
