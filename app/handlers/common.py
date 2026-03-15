"""Общие вспомогательные функции для хендлеров VK-бота."""

from __future__ import annotations

from typing import Dict, Iterable, Set

from loguru import logger
from vkbottle.bot import Message

from app.config import settings
from app.database import db


def extract_payload(message: Message) -> Dict:
    """Безопасно извлекает payload сообщения.

    Возвращает:
    - словарь payload, если кнопка действительно передала JSON;
    - пустой словарь, если payload отсутствует или не является словарём.
    """

    payload = message.get_payload_json()
    if isinstance(payload, dict):
        logger.debug(
            "Payload извлечён (user_id={}, keys={})",
            int(message.from_id),
            list(payload.keys()),
        )
        return payload

    logger.debug("Payload отсутствует или не является dict (user_id={})", int(message.from_id))
    return {}


async def is_moderator(user_id: int) -> bool:
    """Проверяет права модератора/администратора."""
    is_admin = settings.is_admin(user_id)
    is_db_mod = await db.is_user_moderator(user_id)
    result = is_admin or is_db_mod
    logger.debug(
        "Проверка модератора (user_id={}, is_admin={}, is_db_moderator={}, result={})",
        user_id,
        is_admin,
        is_db_mod,
        result,
    )
    return result


async def get_moderator_ids() -> Set[int]:
    """Возвращает итоговый набор ID модераторов.

    Источники:
    1. список администраторов из конфигурации;
    2. пользователи с флагом `is_moderator` в базе данных.
    """

    moderators = await db.get_moderators()
    result: Set[int] = set(settings.admin_user_ids)
    result.update(item.id for item in moderators)
    logger.debug(
        "Собран список модераторов (from_admins={}, from_db={}, total={})",
        len(settings.admin_user_ids),
        len(moderators),
        len(result),
    )
    return result
