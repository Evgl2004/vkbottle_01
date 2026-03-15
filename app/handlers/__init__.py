"""Handlers registry."""

from vkbottle.bot import Bot

from app.handlers.start import register_start_handlers


def setup_handlers(bot: Bot) -> None:
    """Register all bot handlers."""
    register_start_handlers(bot)
