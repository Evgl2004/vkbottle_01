"""Точка входа приложения VK-бота.

Модуль отвечает за запуск процесса в корректном асинхронном режиме.
Ключевая задача: гарантировать, что инфраструктура (PostgreSQL, Redis, iiko)
инициализируется и используется в том же event loop, где работают хендлеры
vkbottle. Это исключает ошибки межцикловой работы asyncio.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Переменную важно выставить до импорта vkbottle,
# чтобы избежать проблем с loguru enqueue в отдельных окружениях.
os.environ.setdefault("LOGURU_AUTOINIT", "1")

from loguru import logger
from vkbottle.bot import Bot

from app.config import settings
from app.handlers import setup_handlers
from app.services import prepare_infrastructure, shutdown_infrastructure


def configure_logging() -> None:
    """Настраивает единый формат логирования процесса."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
        colorize=False,
    )


async def run_bot() -> None:
    """Запускает бота в едином event loop.

    Почему это важно:
    1. SQLAlchemy async/asyncpg, Redis-клиент и aiohttp-сессии iiko должны жить
       в одном цикле событий.
    2. Если подготовка инфраструктуры выполняется через отдельный `asyncio.run`,
       а polling стартует в другом loop, возможны ошибки вида:
       - `Future attached to a different loop`
       - `Event loop is closed`

    Сценарий выполнения:
    1. Подготовить инфраструктуру.
    2. Создать экземпляр `Bot` и зарегистрировать хендлеры.
    3. Запустить polling.
    4. При остановке гарантированно закрыть инфраструктурные ресурсы.
    """

    state_dispenser = await prepare_infrastructure()
    bot = Bot(token=settings.vk_bot_token, state_dispenser=state_dispenser)
    setup_handlers(bot)

    try:
        await bot.run_polling()
    finally:
        await shutdown_infrastructure(state_dispenser)
        logger.info("Приложение остановлено корректно")


def main() -> None:
    """Синхронная точка входа процесса.

    Функция только настраивает логирование и запускает единый async-контур.
    """

    configure_logging()
    logger.info("Запуск VK-бота")

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (KeyboardInterrupt)")


if __name__ == "__main__":
    main()
