"""Регистрация всех наборов хендлеров бота."""

from __future__ import annotations

from vkbottle.bot import Bot

from app.handlers.legacy import register_legacy_handlers
from app.handlers.menu import register_menu_handlers
from app.handlers.moderation import register_moderation_handlers
from app.handlers.registration import register_registration_handlers
from app.handlers.start import register_start_handlers
from app.handlers.user_tickets import register_user_ticket_handlers


def setup_handlers(bot: Bot) -> None:
    """Подключает все обработчики в правильном порядке.

    Порядок имеет значение:
    1. стартовые команды;
    2. пользовательские flow (регистрация/legacy/меню);
    3. тикеты;
    4. модерация.
    """

    register_start_handlers(bot)
    register_registration_handlers(bot)
    register_legacy_handlers(bot)
    register_menu_handlers(bot)
    register_user_ticket_handlers(bot)
    register_moderation_handlers(bot)
