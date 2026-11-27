from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "maxbottenants"
    app_secret_key: str = "change-me-in-production"
    log_level: str = "INFO"
    default_timezone: str = "Europe/Moscow"

    database_url: str = Field(
        default="postgresql+psycopg://maxbot:maxbot@localhost:5432/maxbottenants"
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://maxbot:maxbot@localhost:5432/maxbottenants"
    )
    redis_url: str = "redis://localhost:6379/0"

    max_api_base_url: str = "https://platform-api2.max.ru"
    max_bot_token: str = ""
    max_webhook_secret: str = ""
    max_webhook_enabled: bool = False
    worker_batch_size: int = 100
    worker_stale_processing_seconds: int = 300
    outbox_max_attempts: int = 5

    def validate_runtime(self) -> list[str]:
        warnings: list[str] = []
        if self.max_webhook_enabled and not self.max_webhook_secret:
            warnings.append("MAX_WEBHOOK_ENABLED=true but MAX_WEBHOOK_SECRET is empty")
        if self.app_env != "development":
            if self.app_secret_key == "change-me-in-production":
                warnings.append("APP_SECRET_KEY uses default dev value")
            if self.admin_api_token == "change-me":
                warnings.append("ADMIN_API_TOKEN uses default dev value")
        return warnings

    admin_api_token: str = "change-me"
    sync_interval_minutes: int = 15
    worker_poll_interval_seconds: int = 2


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
