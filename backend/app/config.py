"""Settings from environment variables (SPEC 1.3). Safe defaults for local tests."""

from functools import lru_cache

from pydantic_settings import BaseSettings

DEV_TEAM_PASSWORD = "dev-password"  # noqa: S105 - development default, refused in production
TIMEZONE = "Europe/Amsterdam"


class Settings(BaseSettings):
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = "postgresql+psycopg://scrum:scrum@localhost:5432/scrum"

    # Shared team login for the web pages (HTTP Basic auth).
    TEAM_USER: str = "team"
    TEAM_PASSWORD: str = DEV_TEAM_PASSWORD

    # Teams Workflows webhook. Empty = dry run (posts are recorded, not sent).
    TEAMS_WEBHOOK_URL: str = ""

    # Local model (OpenAI-compatible llama-server on the PC).
    LLM_BASE_URL: str = "http://localhost:8080/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "coder"
    LLM_TIMEOUT_S: int = 900

    # Optional: wake the sleeping PC through the homelab waker.
    WAKER_URL: str = ""
    WAKER_TOKEN: str = ""

    SUMMARY_CHUNK_CHARS: int = 40_000
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
    SUMMARY_RETENTION_DAYS: int = 180
    DEADLINE_RETENTION_DAYS: int = 60
    POST_LOG_RETENTION_DAYS: int = 180


class ConfigError(RuntimeError):
    """Raised when the configuration is unsafe for production."""


def check_production(s: Settings) -> None:
    """SPEC 1.4: refuse to start in production with development secrets."""
    if s.APP_ENV != "production":
        return
    if s.TEAM_PASSWORD == DEV_TEAM_PASSWORD or len(s.TEAM_PASSWORD) < 12:
        raise ConfigError("TEAM_PASSWORD must be set to a real password (12+ chars) in production")
    if s.TEAMS_WEBHOOK_URL and not s.TEAMS_WEBHOOK_URL.startswith("https://"):
        raise ConfigError("TEAMS_WEBHOOK_URL must be an https:// URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
