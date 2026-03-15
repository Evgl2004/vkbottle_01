"""Точка входа приложения VK-бота.

Файл отвечает за:
1. настройку логирования;
2. подготовку инфраструктуры (PostgreSQL, Redis, iiko);
3. создание экземпляра `Bot` и регистрацию хендлеров;
4. запуск long polling.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Важно установить переменную ДО импорта vkbottle:
# иначе внутри vkbottle может включиться логгер с enqueue=True,
# который в некоторых окружениях даёт PermissionError.
os.environ.setdefault("LOGURU_AUTOINIT", "1")

from loguru import logger
from vkbottle.bot import Bot

from app.config import settings
from app.handlers import setup_handlers
from app.services import prepare_infrastructure, shutdown_infrastructure


def configure_logging() -> None:
    """Настраивает формат и уровень логирования процесса."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
        colorize=False,
    )


def main() -> None:
    """Запускает приложение в режиме long polling."""

    configure_logging()
    logger.info("Запуск VK-бота")

    state_dispenser = asyncio.run(prepare_infrastructure())
    bot = Bot(token=settings.vk_bot_token, state_dispenser=state_dispenser)
    setup_handlers(bot)

    try:
        bot.run_forever()
    finally:
        asyncio.run(shutdown_infrastructure(state_dispenser))
        logger.info("Приложение остановлено корректно")


if __name__ == "__main__":
    main()
