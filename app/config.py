"""Модуль централизованной конфигурации приложения.

Назначение модуля:
1. Считать параметры окружения из `.env` и переменных ОС.
2. Привести значения к строго типизированной форме.
3. Предоставить удобные вычисляемые свойства:
   - URL подключения к PostgreSQL;
   - URL подключения к Redis;
   - список администраторов.

Почему это важно:
- исключается разрозненная работа с `os.getenv` по всему проекту;
- все проверки и нормализация значений сосредоточены в одной точке;
- упрощается сопровождение и отладка.
"""

from __future__ import annotations

import json
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Типизированная конфигурация бота.

    Класс наследуется от `BaseSettings`, поэтому значения автоматически
    подтягиваются из:
    1. переменных окружения;
    2. файла `.env` (если он присутствует).

    Важно:
    - поля объявлены с alias, чтобы имена в Python были «питоничными»,
      а имена в `.env` оставались привычными для DevOps-конфигурации.
    - для всех чувствительных параметров (токены, пароли) предусмотрены
      явные поля, что облегчает валидацию при старте.
    """

    # ----------------------------
    # Настройки VK
    # ----------------------------
    vk_bot_token: str = Field(..., alias="VK_BOT_TOKEN")
    vk_group_id: int = Field(0, alias="VK_GROUP_ID")

    # ----------------------------
    # Роли и доступ
    # ----------------------------
    admin_user_ids_raw: str = Field("", alias="ADMIN_USER_IDS")

    # ----------------------------
    # PostgreSQL
    # ----------------------------
    postgres_host: str = Field("localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field("vkbot", alias="POSTGRES_DB")
    postgres_user: str = Field("vkbot", alias="POSTGRES_USER")
    postgres_password: str = Field("", alias="POSTGRES_PASSWORD")

    # ----------------------------
    # Redis
    # ----------------------------
    redis_host: str = Field("localhost", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_db: int = Field(0, alias="REDIS_DB")
    redis_password: str = Field("", alias="REDIS_PASSWORD")

    # ----------------------------
    # Служебные параметры процесса
    # ----------------------------
    env: str = Field("development", alias="ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_super_verbose: bool = Field(False, alias="LOG_SUPER_VERBOSE")

    # ----------------------------
    # iiko
    # ----------------------------
    iiko_api_key: str = Field("", alias="IIKO_API_KEY")
    iiko_org_id: str = Field("", alias="IIKO_ORG_ID")
    iiko_base_url: str = Field("https://api-ru.iiko.services/api/1", alias="IIKO_BASE_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def admin_user_ids(self) -> List[int]:
        """Возвращает список ID администраторов.

        Поддерживаются два формата входной строки:
        1. JSON-массив: `[123, 456]`
        2. CSV-строка: `123,456`
        """

        raw = (self.admin_user_ids_raw or "").strip()
        if not raw:
            return []

        # Пытаемся распарсить JSON-формат.
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [int(item) for item in parsed]
        except json.JSONDecodeError:
            # Если это не JSON, обработаем как CSV.
            pass

        return [int(item.strip()) for item in raw.split(",") if item.strip()]

    def is_admin(self, user_id: int) -> bool:
        """Проверяет, входит ли пользователь в список администраторов."""
        return user_id in self.admin_user_ids

    @property
    def database_url(self) -> str:
        """Формирует sync-URL для PostgreSQL.

        Этот URL используется как базовая строка, от которой затем
        строится async-вариант (`+asyncpg`).
        """

        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Возвращает async-URL для SQLAlchemy + asyncpg."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @property
    def redis_url(self) -> str:
        """Возвращает URL подключения к Redis с учетом пароля."""
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}@"
                f"{self.redis_host}:{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# Единый экземпляр настроек, импортируемый во всем проекте.
settings = Settings()
