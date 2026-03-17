"""Application configuration."""

from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""

    # Application
    APP_NAME: str = "AI Concurs Backend"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_concurs"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # Event Queue
    EVENT_QUEUE_NAME: str = "event_queue"
    EVENT_RETRY_QUEUE_NAME: str = "event_retry_queue"
    EVENT_DEAD_LETTER_QUEUE_NAME: str = "event_dead_letter_queue"

    # Processing
    COMMIT_BATCH_WINDOW_MINUTES: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY_SECONDS: int = 60

    # GitLab API
    GITLAB_BASE_URL: str = "https://gitlab.com"
    GITLAB_API_TOKEN: Optional[str] = None
    GITLAB_API_TIMEOUT: int = 30
    GITLAB_API_RETRY_COUNT: int = 3

    # GitLab Webhook
    GITLAB_WEBHOOK_SECRET: str = ""  # Required! Set via environment variable

    # Jira Integration
    JIRA_URL: str = ""
    JIRA_EMAIL: str = ""
    JIRA_TOKEN: str = ""
    JIRA_AUTO_POST: bool = True  # Auto-post AI summaries to Jira

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
