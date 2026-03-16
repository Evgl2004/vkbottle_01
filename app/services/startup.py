"""Сервис инфраструктурного старта приложения.

Модуль инкапсулирует подготовку внешних зависимостей (PostgreSQL, Redis, iiko)
и предоставляет две стратегии запуска:
1. `prepare_runtime()` — когда инфраструктура поднимается в уже активном loop.
2. `prepare_infrastructure()` — совместимый режим, который дополнительно
   возвращает готовый `RedisStateDispenser`.
"""

from __future__ import annotations

from typing import Any

import aiohttp
from loguru import logger
from redis.asyncio import Redis

from app.config import settings
from app.database import db
from . import iiko_service
from .state_dispenser import RedisStateDispenser


async def _verify_vk_longpoll_configuration() -> None:
    """Проверяет настройки VK Long Poll и наличие событий для callback-кнопок.

    Цель проверки:
    1. Вывести диагностику в логах сразу при старте бота.
    2. Рано обнаружить типовые причины «кнопки нажимаются, но ничего не происходит»:
       - выключен Long Poll;
       - не включено событие `message_event` для callback-кнопок;
       - не включено `message_new` для fallback-сценариев.

    Важно:
    - Проверка диагностическая, не блокирует запуск приложения.
    - При ошибке сети/VK API пишется warning с рекомендацией проверить настройки вручную.
    """

    if settings.vk_group_id <= 0:
        logger.warning(
            "VK preflight пропущен: VK_GROUP_ID не задан или <= 0 (vk_group_id={})",
            settings.vk_group_id,
        )
        return

    if not settings.vk_bot_token:
        logger.warning("VK preflight пропущен: VK_BOT_TOKEN пуст")
        return

    params = {
        "group_id": settings.vk_group_id,
        "access_token": settings.vk_bot_token,
        "v": "5.199",
    }
    url = "https://api.vk.com/method/groups.getLongPollSettings"
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                payload: dict[str, Any] = await response.json(content_type=None)
    except Exception as error:
        logger.warning(
            "VK preflight: не удалось запросить Long Poll настройки (group_id={}, error={})",
            settings.vk_group_id,
            error,
        )
        return

    if "error" in payload:
        error = payload.get("error") or {}
        logger.warning(
            "VK preflight: VK API вернул ошибку (group_id={}, code={}, message={})",
            settings.vk_group_id,
            error.get("error_code"),
            error.get("error_msg"),
        )
        return

    response_data = payload.get("response") or {}
    events = response_data.get("events") or {}
    is_enabled = bool(response_data.get("is_enabled"))
    message_new_enabled = bool(events.get("message_new"))
    message_event_enabled = bool(events.get("message_event"))
    message_reply_enabled = bool(events.get("message_reply"))
    message_edit_enabled = bool(events.get("message_edit"))

    logger.debug(
        "VK preflight: Long Poll settings (enabled={}, message_new={}, message_event={}, message_reply={}, message_edit={})",
        is_enabled,
        message_new_enabled,
        message_event_enabled,
        message_reply_enabled,
        message_edit_enabled,
    )

    missing_events: list[str] = []
    if not message_new_enabled:
        missing_events.append("message_new")
    if not message_event_enabled:
        missing_events.append("message_event")

    if not is_enabled:
        logger.warning(
            "VK preflight: Long Poll выключен для группы (group_id={}). Включите Long Poll в настройках сообщества VK.",
            settings.vk_group_id,
        )
        return

    if missing_events:
        logger.warning(
            "VK preflight: не включены обязательные события Long Poll {} (group_id={}). "
            "Кнопки callback могут не работать, пока события не будут активированы.",
            missing_events,
            settings.vk_group_id,
        )
        return

    logger.info(
        "VK preflight: Long Poll настроен корректно (group_id={}, message_event=1, message_new=1)",
        settings.vk_group_id,
    )


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
    await _verify_vk_longpoll_configuration()
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
