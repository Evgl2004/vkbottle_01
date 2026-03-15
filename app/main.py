"""Application entrypoint."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger
from vkbottle.bot import Bot

from app.config import settings
from app.handlers import setup_handlers
from app.services import bootstrap


def configure_logging() -> None:
    """Configure process logger."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
        colorize=False,
    )


def main() -> None:
    """Start application."""
    configure_logging()
    logger.info("starting VK bot")

    asyncio.run(bootstrap())

    bot = Bot(token=settings.vk_bot_token)
    setup_handlers(bot)
    bot.run_forever()


if __name__ == "__main__":
    main()
