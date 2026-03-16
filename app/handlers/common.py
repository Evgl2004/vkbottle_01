"""Общие вспомогательные функции для хендлеров VK-бота."""

from __future__ import annotations

from collections import defaultdict
from time import perf_counter
from typing import Any, Dict, Set

from loguru import logger
from vkbottle.bot import Message, MessageEvent

from app.config import settings
from app.database import db

_CALLBACK_STATS_LOG_STEP = 25
_callback_router_stats: dict[str, dict[str, int]] = defaultdict(
    lambda: {
        "received": 0,
        "matched": 0,
        "handled": 0,
        "skipped": 0,
        "errors": 0,
    }
)


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


def _extract_event_trace_id(event: MessageEvent) -> str:
    """Возвращает наиболее полезный trace-id callback-события."""

    # Для message_event в object обычно есть короткий event_id клика кнопки.
    object_event_id = None
    event_object = getattr(event, "object", None)
    if event_object is not None:
        object_event_id = getattr(event_object, "event_id", None)

    top_level_event_id = getattr(event, "event_id", None)
    return str(object_event_id or top_level_event_id or "-")


def _log_callback_stats_if_needed(router: str) -> None:
    """Периодически пишет агрегированную статистику callback-роутера."""

    stats = _callback_router_stats[router]
    if stats["received"] % _CALLBACK_STATS_LOG_STEP != 0:
        return

    logger.info(
        "CALLBACK_STATS router={} received={} matched={} handled={} skipped={} errors={}",
        router,
        stats["received"],
        stats["matched"],
        stats["handled"],
        stats["skipped"],
        stats["errors"],
    )


def start_callback_trace(
    router: str,
    event: MessageEvent,
    payload: Dict[str, Any],
    *,
    state: str | None = None,
) -> tuple[str | None, float]:
    """Логирует вход callback-события и возвращает (`cmd`, `started_at`)."""

    started_at = perf_counter()
    command = payload.get("cmd")
    trace_id = _extract_event_trace_id(event)

    _callback_router_stats[router]["received"] += 1
    logger.debug(
        "CALLBACK_TRACE IN router={} trace_id={} user_id={} peer_id={} cmid={} cmd={} state={} payload={}",
        router,
        trace_id,
        int(event.user_id),
        int(event.peer_id),
        event.conversation_message_id,
        command,
        state or "-",
        payload,
    )
    _log_callback_stats_if_needed(router)
    return (str(command) if command is not None else None), started_at


def mark_callback_matched(
    router: str,
    event: MessageEvent,
    *,
    command: str | None,
    state: str | None = None,
) -> None:
    """Логирует, что событие принято в обработку конкретным роутером."""

    trace_id = _extract_event_trace_id(event)
    _callback_router_stats[router]["matched"] += 1
    logger.debug(
        "CALLBACK_TRACE MATCHED router={} trace_id={} cmd={} state={}",
        router,
        trace_id,
        command or "-",
        state or "-",
    )


def mark_callback_skipped(
    router: str,
    event: MessageEvent,
    *,
    reason: str,
    command: str | None,
    state: str | None = None,
) -> None:
    """Логирует причину, по которой роутер пропустил callback-событие."""

    trace_id = _extract_event_trace_id(event)
    _callback_router_stats[router]["skipped"] += 1
    logger.debug(
        "CALLBACK_TRACE SKIP router={} trace_id={} reason={} cmd={} state={}",
        router,
        trace_id,
        reason,
        command or "-",
        state or "-",
    )
    _log_callback_stats_if_needed(router)


def finish_callback_trace(
    router: str,
    event: MessageEvent,
    *,
    started_at: float,
    action: str,
    command: str | None,
    state: str | None = None,
) -> None:
    """Логирует успешное завершение callback-обработки и её длительность."""

    trace_id = _extract_event_trace_id(event)
    elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
    _callback_router_stats[router]["handled"] += 1
    logger.debug(
        "CALLBACK_TRACE DONE router={} trace_id={} action={} cmd={} state={} elapsed_ms={}",
        router,
        trace_id,
        action,
        command or "-",
        state or "-",
        elapsed_ms,
    )
    _log_callback_stats_if_needed(router)


def fail_callback_trace(
    router: str,
    event: MessageEvent,
    *,
    started_at: float,
    command: str | None,
    state: str | None = None,
) -> None:
    """Логирует аварийное завершение callback-обработки."""

    trace_id = _extract_event_trace_id(event)
    elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
    _callback_router_stats[router]["errors"] += 1
    logger.exception(
        "CALLBACK_TRACE ERROR router={} trace_id={} cmd={} state={} elapsed_ms={}",
        router,
        trace_id,
        command or "-",
        state or "-",
        elapsed_ms,
    )
    _log_callback_stats_if_needed(router)


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
