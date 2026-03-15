"""Application configuration."""

from __future__ import annotations

import json
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment."""

    vk_bot_token: str = Field(..., alias="VK_BOT_TOKEN")
    vk_group_id: int = Field(0, alias="VK_GROUP_ID")

    admin_user_ids_raw: str = Field("", alias="ADMIN_USER_IDS")

    postgres_host: str = Field("localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field("vkbot", alias="POSTGRES_DB")
    postgres_user: str = Field("vkbot", alias="POSTGRES_USER")
    postgres_password: str = Field("", alias="POSTGRES_PASSWORD")

    redis_host: str = Field("localhost", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_db: int = Field(0, alias="REDIS_DB")
    redis_password: str = Field("", alias="REDIS_PASSWORD")

    env: str = Field("development", alias="ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def admin_user_ids(self) -> List[int]:
        """Parse admin ids from JSON array or comma-separated string."""

        if not self.admin_user_ids_raw:
            return []

        raw = self.admin_user_ids_raw.strip()
        if not raw:
            return []

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [int(value) for value in parsed]
        except json.JSONDecodeError:
            pass

        return [int(item.strip()) for item in raw.split(",") if item.strip()]

    def is_admin(self, user_id: int) -> bool:
        """Check whether user id is in admin list."""
        return user_id in self.admin_user_ids

    @property
    def database_url(self) -> str:
        """Sync SQLAlchemy URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Async SQLAlchemy URL for asyncpg driver."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @property
    def redis_url(self) -> str:
        """Redis connection URL."""
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}@"
                f"{self.redis_host}:{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
