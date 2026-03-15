"""Пакет middleware-слоя VK-бота.

Задачи слоя:
1. Подключать сквозные middleware для всех входящих событий.
2. Содержать переиспользуемые middleware-компоненты (логирование, аудит и т.д.).
3. Давать единую точку регистрации middleware в приложении.
"""

from __future__ import annotations

from loguru import logger
from vkbottle.bot import Bot

from app.middlewares.logging import LoggingMiddleware


def setup_middlewares(bot: Bot) -> None:
    """Регистрирует middleware в транспортном слое `vkbottle`.

    На текущем этапе подключается:
    - `LoggingMiddleware` — сквозное debug-логирование входящих сообщений.

    Важно:
    - middleware регистрируется на `message_view`, поэтому покрывает
      весь набор `private_message`/`chat_message`-хендлеров.
    """

    bot.labeler.message_view.register_middleware(LoggingMiddleware)
    logger.info("Middleware-слой подключён: LoggingMiddleware")

