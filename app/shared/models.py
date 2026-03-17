"""SQLAlchemy ORM models.

These models are SHARED between Webhook and Processing layers.
They represent the database schema.
"""

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
    func,
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
from typing import Optional

Base = declarative_base()


class Repository(Base):
    """Represents a Git repository."""
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    branches = relationship("Branch", back_populates="repository", lazy="select")

    def __repr__(self) -> str:
        return f"<Repository(name={self.name})>"


class Branch(Base):
    """Represents a Git branch."""
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    jira_issue = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    repository = relationship("Repository", back_populates="branches")
    commits = relationship("Commit", back_populates="branch", cascade="all, delete-orphan", lazy="select")
    events = relationship("Event", back_populates="branch_rel", foreign_keys="Event.branch_id", lazy="select")
    merge_requests = relationship("MergeRequest", back_populates="branch", cascade="all, delete-orphan", lazy="select")

    __table_args__ = (
        Index("idx_branches_name_repo", "name", "repository_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Branch(name={self.name}, repo_id={self.repository_id})>"


class Commit(Base):
    """Represents a Git commit associated with a branch."""
    __tablename__ = "commits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commit_hash = Column(String(64), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    author = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    branch = relationship("Branch", back_populates="commits")

    __table_args__ = (
        Index("idx_commits_hash_branch", "commit_hash", "branch_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Commit(id={self.id}, hash={self.commit_hash[:8]})>"


class MergeRequest(Base):
    """Represents a GitLab Merge Request."""
    __tablename__ = "merge_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    mr_id = Column(Integer, nullable=False, index=True)
    title = Column(String(500), nullable=True)
    status = Column(String(50), nullable=True)
    merged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    branch = relationship("Branch", back_populates="merge_requests")

    __table_args__ = (
        Index("idx_mr_branch_mr_id", "branch_id", "mr_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MergeRequest(id={self.mr_id}, status={self.status})>"


class Event(Base):
    """Represents a normalized GitLab webhook event."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    repository = Column(String(255), nullable=False, index=True)
    branch = Column(String(255), nullable=True, index=True)
    jira_issue = Column(String(50), nullable=True, index=True)
    author = Column(String(255), nullable=True)
    payload_json = Column(Text, nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed = Column(Boolean, default=False, nullable=False, index=True)
    processing_error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    branch_rel = relationship("Branch", back_populates="events", foreign_keys=[branch_id], lazy="select")

    __table_args__ = (
        Index("idx_events_processed_created", "processed", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Event(id={self.id}, type={self.event_type}, processed={self.processed})>"


class AISummary(Base):
    """Represents AI-ready summary input for a Jira issue."""
    __tablename__ = "ai_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jira_issue = Column(String(50), nullable=False, index=True)
    summary_input_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed = Column(Boolean, default=False, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    jira_comment_id = Column(Integer, nullable=True)

    commit_count = Column(Integer, nullable=True)
    time_range_start = Column(DateTime, nullable=True)
    time_range_end = Column(DateTime, nullable=True)
    authors = Column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_ai_summaries_issue_processed", "jira_issue", "processed"),
    )

    def __repr__(self) -> str:
        return f"<AISummary(jira={self.jira_issue}, processed={self.processed})>"
