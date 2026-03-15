"""Basic VK handlers."""

from __future__ import annotations

from vkbottle.bot import Bot, Message

from app.database import db


def register_start_handlers(bot: Bot) -> None:
    """Register initial text handlers."""

    @bot.on.message(text=["/start", "start", "Start", "menu", "Menu"])
    async def start_handler(message: Message) -> None:
        user_id = int(message.from_id)
        await db.add_or_update_user(user_id=user_id)
        user = await db.get_user(user_id)
        name = (user.first_name_input if user else None) or "friend"

        await message.answer(
            "\n".join(
                [
                    f"Hello, {name}.",
                    "VK bot baseline is initialized.",
                    "Core flows from Telegram reference are documented.",
                    "Next step: implement registration and ticket flows.",
                ]
            )
        )

    @bot.on.message(text=["/help", "help", "Help"])
    async def help_handler(message: Message) -> None:
        await message.answer(
            "\n".join(
                [
                    "Available commands:",
                    "- /start",
                    "- /help",
                    "",
                    "Current status: initialization completed.",
                ]
            )
        )
