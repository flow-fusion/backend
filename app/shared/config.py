"""Application configuration."""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Application
    APP_NAME: str = "FlowFusion"
    DEBUG: bool = False
    VERSION: str = "1.0.0"

    # Database (REQUIRED for production, optional for testing)
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

    # GitLab Webhook (REQUIRED for production)
    GITLAB_WEBHOOK_SECRET: str = ""

    # Jira Integration (OPTIONAL)
    JIRA_URL: str = ""
    JIRA_EMAIL: str = ""
    JIRA_TOKEN: str = ""
    JIRA_AUTO_POST: bool = True
    JIRA_USE_BEARER_AUTH: bool = False  # Use Bearer token auth instead of Basic

    # AI Configuration (OPTIONAL)
    AI_PROVIDER: str = "openrouter"  # openai, openrouter, anthropic, ollama, google
    AI_API_KEY: str = ""
    AI_MODEL: str = ""
    AI_AUTO_GENERATE: bool = False  # Auto-generate AI summaries
    OLLAMA_BASE_URL: str = "http://localhost:11434"  # For local Ollama

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    def validate_required(self) -> None:
        """Validate required settings are configured for production."""
        import warnings
        if not self.GITLAB_WEBHOOK_SECRET:
            warnings.warn("GITLAB_WEBHOOK_SECRET is not configured - webhook validation disabled")
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL is required")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
