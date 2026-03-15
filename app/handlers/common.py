"""Общие вспомогательные функции для хендлеров VK-бота."""

from __future__ import annotations

from typing import Dict, Iterable, Set

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
    return payload if isinstance(payload, dict) else {}


async def is_moderator(user_id: int) -> bool:
    """Проверяет права модератора/администратора."""
    return settings.is_admin(user_id) or await db.is_user_moderator(user_id)


async def get_moderator_ids() -> Set[int]:
    """Возвращает итоговый набор ID модераторов.

    Источники:
    1. список администраторов из конфигурации;
    2. пользователи с флагом `is_moderator` в базе данных.
    """

    moderators = await db.get_moderators()
    result: Set[int] = set(settings.admin_user_ids)
    result.update(item.id for item in moderators)
    return result
