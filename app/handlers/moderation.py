"""Хендлеры модераторской части тикетной системы."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from loguru import logger
from vkbottle.bot import Bot, Message

from app.database import db
from app.handlers.common import extract_payload, is_moderator
from app.keyboards.moderation import (
    get_moderation_main_keyboard,
    get_moderation_ticket_details_keyboard,
    get_moderation_tickets_keyboard,
)
from app.keyboards.payloads import (
    CMD_MOD_CLOSE,
    CMD_MOD_MAIN,
    CMD_MOD_REPLY,
    CMD_MOD_TICKET,
    CMD_MOD_TICKETS,
    CMD_MOD_TICKETS_PAGE,
)
from app.keyboards.user_tickets import get_user_ticket_details_keyboard
from app.services.tickets import ticket_service
from app.states.tickets import TicketState
from app.utils.ticket_formatter import format_ticket_details
from app.utils.validation import confirm_text


FILTER_STATUS_MAP: Dict[str, Optional[Sequence[str]]] = {
    "all": None,
    "open": ["open"],
    "in_progress": ["in_progress"],
}

FILTER_TITLES = {
    "all": "Все тикеты",
    "open": "Новые тикеты",
    "in_progress": "Тикеты в работе",
}


async def _send_moderation_dashboard(message: Message) -> None:
    """Отправляет модератору сводку и клавиатуру управления."""

    open_count, in_progress_count, avg_response = await ticket_service.get_tickets_stats()
    avg_text = f"{avg_response} мин" if avg_response is not None else "нет данных"
    await message.answer(
        "\n".join(
            [
                "Панель модератора:",
                f"- Новые тикеты: {open_count}",
                f"- Тикеты в работе: {in_progress_count}",
                f"- Среднее время ответа: {avg_text}",
            ]
        ),
        keyboard=get_moderation_main_keyboard(),
    )


def register_moderation_handlers(bot: Bot) -> None:
    """Регистрирует обработчики модераторских сценариев."""

    @bot.on.private_message(text=["/mod", "модератор", "moderator"])
    @bot.on.private_message(payload_contains={"cmd": CMD_MOD_MAIN})
    async def moderation_main(message: Message) -> None:
        """Открывает главное модераторское меню."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("У вас нет прав модератора.")
            return

        await bot.state_dispenser.delete(user_id)
        await _send_moderation_dashboard(message)

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_TICKETS, "filter": str})
    async def moderation_list(message: Message) -> None:
        """Показывает первую страницу тикетов по выбранному фильтру."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        filter_key = payload.get("filter", "all")
        statuses = FILTER_STATUS_MAP.get(filter_key, None)

        tickets, total_count = await ticket_service.get_tickets_page(
            page=1,
            per_page=10,
            statuses=statuses,
        )
        if not tickets:
            await message.answer(
                f"{FILTER_TITLES.get(filter_key, 'Тикеты')} отсутствуют.",
                keyboard=get_moderation_main_keyboard(),
            )
            return

        total_pages = (total_count + 10 - 1) // 10
        await message.answer(
            f"{FILTER_TITLES.get(filter_key, 'Тикеты')} (страница 1/{total_pages}):",
            keyboard=get_moderation_tickets_keyboard(tickets, 1, total_pages, filter_key),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_TICKETS_PAGE, "page": int, "filter": str})
    async def moderation_page(message: Message) -> None:
        """Переключает страницу списка тикетов модератора."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        page = max(int(payload.get("page", 1)), 1)
        filter_key = payload.get("filter", "all")
        statuses = FILTER_STATUS_MAP.get(filter_key, None)

        tickets, total_count = await ticket_service.get_tickets_page(
            page=page,
            per_page=10,
            statuses=statuses,
        )
        if not tickets:
            await message.answer(
                "На этой странице тикеты отсутствуют.",
                keyboard=get_moderation_main_keyboard(),
            )
            return

        total_pages = (total_count + 10 - 1) // 10
        await message.answer(
            f"{FILTER_TITLES.get(filter_key, 'Тикеты')} (страница {page}/{total_pages}):",
            keyboard=get_moderation_tickets_keyboard(tickets, page, total_pages, filter_key),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_TICKET, "ticket_id": int, "filter": str})
    async def moderation_ticket_details(message: Message) -> None:
        """Показывает карточку конкретного тикета модератору."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))
        filter_key = payload.get("filter", "all")

        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket:
            await message.answer("Тикет не найден.")
            return

        history = await ticket_service.get_ticket_messages(ticket_id)
        await message.answer(
            format_ticket_details(ticket, history),
            keyboard=get_moderation_ticket_details_keyboard(ticket_id, ticket.status, filter_key),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_REPLY, "ticket_id": int})
    async def moderation_reply_start(message: Message) -> None:
        """Переводит модератора в режим ввода ответа по тикету."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))
        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket:
            await message.answer("Тикет не найден.")
            return
        if ticket.status == "closed":
            await message.answer("Тикет уже закрыт. Ответ невозможен.")
            return

        await bot.state_dispenser.set(
            user_id,
            TicketState.WAITING_FOR_MODERATOR_REPLY,
            ticket_id=ticket_id,
        )
        await message.answer(f"Введите ответ пользователю по тикету #{ticket_id}.")

    @bot.on.private_message(state=TicketState.WAITING_FOR_MODERATOR_REPLY)
    async def moderation_reply_send(message: Message) -> None:
        """Сохраняет ответ модератора, меняет статус и уведомляет пользователя."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await bot.state_dispenser.delete(user_id)
            await message.answer("У вас нет прав модератора.")
            return
        if not await confirm_text(message, "Пожалуйста, отправьте ответ текстом."):
            return

        state_peer = message.state_peer
        if state_peer is None:
            await bot.state_dispenser.delete(user_id)
            await message.answer("Состояние ответа потеряно. Откройте тикет заново.")
            return

        ticket_id = int(state_peer.payload.get("ticket_id", 0))
        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket:
            await bot.state_dispenser.delete(user_id)
            await message.answer("Тикет не найден.")
            return

        reply_text = message.text.strip()
        await ticket_service.add_message_to_ticket(
            ticket_id=ticket_id,
            sender_type="moderator",
            sender_id=user_id,
            message=reply_text,
        )
        await ticket_service.update_ticket_status(ticket_id, "in_progress")

        # Уведомляем пользователя.
        try:
            await message.ctx_api.messages.send(
                peer_ids=[ticket.user_id],
                message="\n".join(
                    [
                        f"Ответ модератора по тикету #{ticket_id}:",
                        reply_text,
                    ]
                ),
                keyboard=get_user_ticket_details_keyboard(ticket_id, "in_progress"),
                random_id=0,
            )
        except Exception as error:
            logger.error("Не удалось отправить ответ пользователю {}: {}", ticket.user_id, error)

        updated_ticket = await ticket_service.get_ticket(ticket_id)
        history = await ticket_service.get_ticket_messages(ticket_id)
        await message.answer(
            format_ticket_details(updated_ticket, history) if updated_ticket else "Ответ сохранён.",
            keyboard=get_moderation_ticket_details_keyboard(
                ticket_id,
                updated_ticket.status if updated_ticket else "in_progress",
                "all",
            ),
        )
        await bot.state_dispenser.delete(user_id)

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_CLOSE, "ticket_id": int})
    async def moderation_close_ticket(message: Message) -> None:
        """Закрывает тикет и показывает обновлённую карточку."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))

        ok = await ticket_service.close_ticket(ticket_id)
        if not ok:
            await message.answer("Не удалось закрыть тикет: запись не найдена.")
            return

        ticket = await ticket_service.get_ticket(ticket_id)
        history = await ticket_service.get_ticket_messages(ticket_id)
        await message.answer(
            format_ticket_details(ticket, history) if ticket else "Тикет закрыт.",
            keyboard=get_moderation_ticket_details_keyboard(ticket_id, "closed", "all"),
        )
