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
from typing import Any

# Переменную важно выставить до импорта vkbottle,
# чтобы избежать проблем с loguru enqueue в отдельных окружениях.
os.environ.setdefault("LOGURU_AUTOINIT", "1")

from loguru import logger
from vkbottle.bot import Bot

import asyncio

from app.config import settings
from app.handlers import setup_handlers
from app.services import prepare_runtime, shutdown_infrastructure
from app.services.state_dispenser import RedisStateDispenser
from app.web.server import run_web_server_in_background


def _log_filter(record: dict[str, Any]) -> bool:
    """Фильтрует шумные DEBUG-логи.

    Режимы:
    1. `LOG_SUPER_VERBOSE=true`:
       - пропускаем все логи без ограничений;
       - удобно для глубоких аварийных расследований.
    2. Обычный `DEBUG`:
       - оставляем отладку прикладного кода (`app.*`);
       - скрываем низкоуровневый поток `vkbottle.*`, который в тестовом режиме
         формирует большой объём малополезных записей.
    """

    if settings.log_super_verbose:
        return True

    if record["level"].name != "DEBUG":
        return True

    logger_name = str(record.get("name") or "")
    return not logger_name.startswith("vkbottle.")


def configure_logging() -> None:
    """Настраивает единый формат логирования процесса."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        filter=_log_filter,
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
        "Конфигурация запуска: env={}, log_level={}, log_super_verbose={}, group_id={}, admins_count={}",
        settings.env,
        settings.log_level,
        settings.log_super_verbose,
        settings.vk_group_id,
        len(settings.admin_user_ids),
    )

    state_dispenser = RedisStateDispenser.from_url(settings.redis_url)
    logger.debug("Создан RedisStateDispenser")
    bot = Bot(token=settings.vk_bot_token, state_dispenser=state_dispenser)
    setup_handlers(bot)
    logger.debug("Экземпляр Bot инициализирован")

    async def start_web_server_if_enabled():
        """Запускает веб-сервер для Mini App, если он включён в настройках."""
        if settings.web_enabled:
            logger.info("Веб-сервер Mini App включён, запускаем...")
            # Получаем текущий event loop
            loop = asyncio.get_running_loop()
            # Запускаем веб-сервер в фоне
            task = run_web_server_in_background(loop)
            # Сохраняем задачу, чтобы можно было её отменить на shutdown
            # (пока просто оставляем работать)
            await asyncio.sleep(0)  # yield control
        else:
            logger.info("Веб-сервер Mini App отключён в настройках")

    bot.loop_wrapper.on_startup.append(prepare_runtime())
    bot.loop_wrapper.on_startup.append(start_web_server_if_enabled)
    bot.loop_wrapper.on_shutdown.append(shutdown_infrastructure(state_dispenser))
    logger.debug("Startup/Shutdown корутины зарегистрированы в LoopWrapper")

    bot.run_forever()


if __name__ == "__main__":
    main()
