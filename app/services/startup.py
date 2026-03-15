"""Сервис инфраструктурного старта приложения.

Модуль инкапсулирует подготовку внешних зависимостей (PostgreSQL, Redis, iiko)
и предоставляет две стратегии запуска:
1. `prepare_runtime()` — когда инфраструктура поднимается в уже активном loop.
2. `prepare_infrastructure()` — совместимый режим, который дополнительно
   возвращает готовый `RedisStateDispenser`.
"""

from __future__ import annotations

from loguru import logger
from redis.asyncio import Redis

from app.config import settings
from app.database import db
from . import iiko_service
from .state_dispenser import RedisStateDispenser


async def prepare_runtime() -> None:
    """Подготавливает внешнюю инфраструктуру в текущем event loop.

    Выполняемые шаги:
    1. Создание таблиц PostgreSQL (для MVP/dev режима).
    2. Обновление агрегированной статистики запуска.
    3. Проверка доступности Redis (ping).
    4. Инициализация iiko-клиента.

    Важно:
    - Функция не создаёт `RedisStateDispenser`, чтобы избежать лишних соединений.
    - Предназначена для сценария, когда dispenser создаётся отдельно и
      передаётся в `Bot` заранее.
    """

    logger.info("Подготовка инфраструктуры: старт")

    await db.create_tables()
    await db.update_bot_stats()
    logger.debug("База данных и статистика инициализированы")

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()
    await redis_client.aclose()
    logger.info("Подключение к Redis подтверждено")

    await iiko_service.init_iiko_client()
    logger.info("Подготовка инфраструктуры: завершена")


async def prepare_infrastructure() -> RedisStateDispenser:
    """Совместимый API подготовки инфраструктуры.

    Используется в сценариях, где нужно одной функцией:
    1. подготовить сервисы;
    2. получить экземпляр `RedisStateDispenser`.

    Возвращает:
    - готовый `RedisStateDispenser`, подключённый к Redis.
    """

    await prepare_runtime()
    return RedisStateDispenser.from_url(settings.redis_url)


async def shutdown_infrastructure(state_dispenser: RedisStateDispenser) -> None:
    """Освобождает инфраструктурные ресурсы приложения.

    Порядок остановки:
    1. Корректно закрыть iiko-клиент (aiohttp-сессию).
    2. Закрыть Redis-соединение state dispenser.
    """

    logger.info("Остановка инфраструктуры: старт")
    await iiko_service.close_iiko_client()
    await state_dispenser.close()
    logger.info("Остановка инфраструктуры: завершена")
