"""Точка входа приложения VK-бота.

Важная особенность запуска:
- Для текущей версии `vkbottle` безопаснее запускать polling через
  `bot.run_forever()` (управление event loop внутри LoopWrapper).
- Чтобы избежать ошибок разных event loop для БД/Redis/iiko, подготовка
  инфраструктуры переносится в startup-задачи этого же LoopWrapper.
"""

from __future__ import annotations

import os
import sys

# Переменную важно выставить до импорта vkbottle,
# чтобы избежать проблем с loguru enqueue в отдельных окружениях.
os.environ.setdefault("LOGURU_AUTOINIT", "1")

from loguru import logger
from vkbottle.bot import Bot

from app.config import settings
from app.handlers import setup_handlers
from app.services import prepare_runtime, shutdown_infrastructure
from app.services.state_dispenser import RedisStateDispenser


def configure_logging() -> None:
    """Настраивает единый формат логирования процесса."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
        colorize=False,
    )


def main() -> None:
    """Синхронная точка входа процесса.

    Алгоритм:
    1. Настроить логирование.
    2. Создать Redis state dispenser и передать его в `Bot`.
    3. Зарегистрировать хендлеры.
    4. Добавить startup/shutdown-корутины в `LoopWrapper`.
    5. Запустить `bot.run_forever()`.

    Почему именно так:
    - startup/shutdown выполняются в том же loop, где работает polling и хендлеры;
    - это устраняет межцикловые ошибки asyncio/asyncpg при обращениях к БД.
    """

    configure_logging()
    logger.info("Запуск VK-бота")
    logger.info(
        "Конфигурация запуска: env={}, log_level={}, group_id={}, admins_count={}",
        settings.env,
        settings.log_level,
        settings.vk_group_id,
        len(settings.admin_user_ids),
    )

    state_dispenser = RedisStateDispenser.from_url(settings.redis_url)
    logger.debug("Создан RedisStateDispenser")
    bot = Bot(token=settings.vk_bot_token, state_dispenser=state_dispenser)
    setup_handlers(bot)
    logger.debug("Экземпляр Bot инициализирован")

    bot.loop_wrapper.on_startup.append(prepare_runtime())
    bot.loop_wrapper.on_shutdown.append(shutdown_infrastructure(state_dispenser))
    logger.debug("Startup/Shutdown корутины зарегистрированы в LoopWrapper")

    bot.run_forever()


if __name__ == "__main__":
    main()
