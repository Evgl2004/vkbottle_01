"""Сервис инфраструктурного старта приложения."""

from __future__ import annotations

from loguru import logger
from redis.asyncio import Redis

from app.config import settings
from app.database import db
from . import iiko_service
from .state_dispenser import RedisStateDispenser


async def prepare_infrastructure() -> RedisStateDispenser:
    """Готовит инфраструктуру к запуску бота.

    Выполняемые шаги:
    1. Проверка и создание таблиц в PostgreSQL.
    2. Обновление статистики запуска.
    3. Проверка доступности Redis.
    4. Инициализация iiko-клиента.
    5. Создание Redis-based state dispenser для `vkbottle`.
    """

    await db.create_tables()
    await db.update_bot_stats()

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()
    await redis_client.aclose()
    logger.info("Подключение к Redis подтверждено")

    await iiko_service.init_iiko_client()

    return RedisStateDispenser.from_url(settings.redis_url)


async def shutdown_infrastructure(state_dispenser: RedisStateDispenser) -> None:
    """Освобождает инфраструктурные ресурсы приложения."""
    await iiko_service.close_iiko_client()
    await state_dispenser.close()
