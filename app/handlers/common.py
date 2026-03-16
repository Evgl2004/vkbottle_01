"""Общие вспомогательные функции для хендлеров VK-бота."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Set

from loguru import logger
from vkbottle.bot import Message, MessageEvent

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


async def edit_or_send_event_message(
    event: MessageEvent,
    text: str,
    *,
    keyboard: str | None = None,
) -> None:
    """Пытается отредактировать сообщение callback-события, иначе отправляет новое.

    Используется в `message_event`-обработчиках для UX в стиле Telegram:
    - сперва пробуем `messages.edit` по `conversation_message_id`;
    - если редактирование невозможно, выполняем fallback на `messages.send`.
    """

    try:
        if event.conversation_message_id is not None:
            await event.edit_message(message=text, keyboard=keyboard)
            return
    except Exception as error:
        logger.debug(
            "edit_or_send_event_message: edit failed, fallback to send (peer_id={}, cmid={}, error={})",
            event.peer_id,
            event.conversation_message_id,
            error,
        )

    await event.send_message(message=text, keyboard=keyboard)


class EventMessageAdapter:
    """Адаптирует `MessageEvent` к интерфейсу `Message` для общих сервисов.

    Зачем нужен адаптер:
    1. В кодовой базе есть сервисы и хендлеры, которые принимают объект `Message`
       и вызывают у него `answer(...)`, читают `from_id`, `peer_id`, `ctx_api`.
    2. В callback-сценариях (`message_event`) мы хотим переиспользовать эти же
       функции без дублирования бизнес-логики.
    3. Адаптер предоставляет минимально необходимый контракт, делегируя отправку
       сообщений в `event.send_message(...)`.
    """

    def __init__(self, event: MessageEvent) -> None:
        """Инициализирует адаптер из исходного callback-события."""

        self._event = event
        self.from_id = int(event.user_id)
        self.peer_id = int(event.peer_id)
        self.ctx_api = event.ctx_api

    async def answer(self, message: str | None = None, **kwargs: Any) -> None:
        """Совместимый аналог `Message.answer(...)` для callback-контекста."""

        await self._event.send_message(message=message, **kwargs)
