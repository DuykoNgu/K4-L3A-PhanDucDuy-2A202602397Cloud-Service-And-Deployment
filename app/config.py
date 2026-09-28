"""Cấu hình của service đọc từ environment và .env cục bộ."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = Field(default=8000, ge=1, le=65535)
    agent_api_key: str = Field(min_length=1)
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_per_minute: int = Field(default=10, ge=1)
    monthly_budget_usd: float = Field(default=10.0, ge=0, allow_inf_nan=False)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
