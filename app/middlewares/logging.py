"""Middleware сквозного логирования входящих событий VK-бота.

Модуль реализует единый слой технической телеметрии для всех сообщений,
которые проходят через `message_view` в `vkbottle`.

Зачем нужен отдельный middleware:
1. Позволяет видеть полный путь входящего события до конкретного хендлера.
2. Упрощает отладку FSM-состояний (видно активное состояние пользователя).
3. Даёт замер времени обработки каждого апдейта.
4. Централизует формат логов и снижает дублирование в хендлерах.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from loguru import logger
from vkbottle.dispatch.middlewares.abc import BaseMiddleware
from vkbottle.tools.mini_types.bot import MessageMin


def _cut(value: Any, limit: int = 120) -> str:
    """Безопасно сокращает значения для логов.

    Параметры:
    - `value`: исходное значение (строка, число, словарь и т.д.);
    - `limit`: максимальная длина итоговой строки.

    Возвращает:
    - нормализованную однострочную строку, пригодную для логирования.
    """

    text = str(value).replace("\n", "\\n").replace("\r", "\\r")
    return text if len(text) <= limit else f"{text[:limit]}..."


class LoggingMiddleware(BaseMiddleware[MessageMin]):
    """Глобальный middleware логирования private message-событий.

    Контракт работы:
    1. `pre()` логирует входящее сообщение, payload и текущее FSM-состояние.
    2. `post()` логирует число сработавших хендлеров, их ответы и длительность.
    3. В случае внутренних ошибок middleware фиксирует их в `error`.

    Примечание:
    - Экземпляр middleware создаётся отдельно для каждого события,
      поэтому время обработки хранится в поле `self._started_at`.
    """

    def __init__(self, event: MessageMin, view=None) -> None:
        """Инициализирует middleware для конкретного события."""

        super().__init__(event, view=view)
        self._started_at = perf_counter()

    async def pre(self) -> None:
        """Логирует входящие данные до выполнения обработчиков."""

        state = self.event.state_peer.state if self.event.state_peer else None
        payload = self.event.get_payload_json()
        attachments_count = len(self.event.attachments or [])

        logger.debug(
            "📥 INCOMING: user_id={}, peer_id={}, cmid={}, text='{}', payload='{}', "
            "state='{}', attachments={}",
            self.event.from_id,
            self.event.peer_id,
            self.event.conversation_message_id,
            _cut(self.event.text or ""),
            _cut(payload if payload is not None else "-"),
            state or "-",
            attachments_count,
        )

    async def post(self) -> None:
        """Логирует итог обработки события после выполнения хендлеров."""

        elapsed_ms = round((perf_counter() - self._started_at) * 1000, 2)
        handler_names = [handler.handler.__name__ for handler in self.handlers]

        if self.error is not None:
            logger.exception(
                "❌ EVENT_ERROR: user_id={}, peer_id={}, handlers={}, elapsed_ms={}",
                self.event.from_id,
                self.event.peer_id,
                handler_names,
                elapsed_ms,
            )
            return

        logger.debug(
            "✅ OUTGOING: user_id={}, peer_id={}, handlers={}, responses_count={}, elapsed_ms={}",
            self.event.from_id,
            self.event.peer_id,
            handler_names,
            len(self.handle_responses),
            elapsed_ms,
        )
