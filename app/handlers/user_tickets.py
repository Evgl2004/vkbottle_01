"""Хендлеры пользовательского раздела обращений (тикеты)."""

from __future__ import annotations

from typing import List

from loguru import logger
from vkbottle.bot import Bot, Message

from app.database import db
from app.handlers.common import extract_payload, get_moderator_ids
from app.keyboards.menu import get_back_to_main_keyboard, get_back_to_support_keyboard
from app.keyboards.payloads import (
    CMD_MY_TICKETS,
    CMD_USER_REPLY,
    CMD_USER_TICKET,
    CMD_USER_TICKETS_PAGE,
)
from app.keyboards.user_tickets import (
    get_user_ticket_details_keyboard,
    get_user_tickets_list_keyboard,
)
from app.services.tickets import ticket_service
from app.states.tickets import TicketState
from app.utils.ticket_formatter import format_ticket_details
from app.utils.validation import confirm_text


async def _notify_moderators(message: Message, text: str) -> None:
    """Рассылает служебное уведомление всем модераторам."""

    moderator_ids = await get_moderator_ids()
    for moderator_id in moderator_ids:
        try:
            await message.ctx_api.messages.send(
                peer_ids=[moderator_id],
                message=text,
                random_id=0,
            )
        except Exception as error:
            logger.error("Не удалось уведомить модератора {}: {}", moderator_id, error)


def register_user_ticket_handlers(bot: Bot) -> None:
    """Регистрирует обработчики пользовательских тикетов."""

    @bot.on.private_message(state=TicketState.WAITING_FOR_QUESTION)
    async def create_ticket_from_question(message: Message) -> None:
        """Создает новый тикет на основе сообщения пользователя."""

        if not await confirm_text(message, "Пожалуйста, отправьте вопрос текстом."):
            return

        user_id = int(message.from_id)
        user = await db.get_user(user_id)
        if not user:
            await bot.state_dispenser.delete(user_id)
            await message.answer("Пользователь не найден. Введите /start для повторной инициализации.")
            return

        ticket = await ticket_service.create_ticket(
            user_id=user_id,
            message=message.text.strip(),
            user_username=user.username,
            user_first_name=user.first_name_input or user.first_name,
        )

        await message.answer(
            "\n".join(
                [
                    "Ваше обращение принято.",
                    f"Номер тикета: #{ticket.id}",
                    "Модератор ответит в ближайшее время.",
                ]
            ),
            keyboard=get_back_to_main_keyboard(),
        )

        await _notify_moderators(
            message,
            "\n".join(
                [
                    "Новое обращение пользователя.",
                    f"Тикет: #{ticket.id}",
                    f"Пользователь: {user.username or user.first_name_input or user_id}",
                    f"Текст: {message.text.strip()}",
                ]
            ),
        )

        await bot.state_dispenser.delete(user_id)

    @bot.on.private_message(payload_contains={"cmd": CMD_MY_TICKETS})
    async def user_tickets_list(message: Message) -> None:
        """Показывает первую страницу списка обращений пользователя."""

        user_id = int(message.from_id)
        tickets, total_count = await ticket_service.get_tickets_page(
            page=1,
            per_page=5,
            user_id=user_id,
        )
        if not tickets:
            await message.answer(
                "У вас пока нет обращений. Создать обращение можно через раздел «Отдел заботы».",
                keyboard=get_back_to_support_keyboard(),
            )
            return

        total_pages = (total_count + 5 - 1) // 5
        await message.answer(
            f"Ваши обращения (страница 1/{total_pages}):",
            keyboard=get_user_tickets_list_keyboard(tickets, 1, total_pages),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_USER_TICKETS_PAGE, "page": int})
    async def user_tickets_page(message: Message) -> None:
        """Переключает страницу списка пользовательских обращений."""

        payload = extract_payload(message)
        page = int(payload.get("page", 1))
        page = max(page, 1)

        tickets, total_count = await ticket_service.get_tickets_page(
            page=page,
            per_page=5,
            user_id=int(message.from_id),
        )
        if not tickets:
            await message.answer(
                "На этой странице обращений нет.",
                keyboard=get_back_to_support_keyboard(),
            )
            return

        total_pages = (total_count + 5 - 1) // 5
        await message.answer(
            f"Ваши обращения (страница {page}/{total_pages}):",
            keyboard=get_user_tickets_list_keyboard(tickets, page, total_pages),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_USER_TICKET, "ticket_id": int})
    async def user_ticket_details(message: Message) -> None:
        """Показывает карточку конкретного тикета пользователю."""

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))

        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket or ticket.user_id != int(message.from_id):
            await message.answer("Тикет не найден или доступ запрещён.")
            return

        history = await ticket_service.get_ticket_messages(ticket_id)
        await message.answer(
            format_ticket_details(ticket, history),
            keyboard=get_user_ticket_details_keyboard(ticket_id, ticket.status),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_USER_REPLY, "ticket_id": int})
    async def user_reply_start(message: Message) -> None:
        """Переводит пользователя в состояние отправки ответа по тикету."""

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))

        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket or ticket.user_id != int(message.from_id):
            await message.answer("Тикет не найден или доступ запрещён.")
            return
        if ticket.status == "closed":
            await message.answer("Тикет уже закрыт. Отправка нового ответа невозможна.")
            return

        await bot.state_dispenser.set(
            int(message.from_id),
            TicketState.WAITING_FOR_USER_REPLY,
            ticket_id=ticket_id,
        )
        await message.answer(
            f"Введите ответ для тикета #{ticket_id}.",
            keyboard=get_user_ticket_details_keyboard(ticket_id, ticket.status),
        )

    @bot.on.private_message(state=TicketState.WAITING_FOR_USER_REPLY)
    async def user_reply_send(message: Message) -> None:
        """Сохраняет ответ пользователя и уведомляет модераторов."""

        if not await confirm_text(message, "Пожалуйста, отправьте ответ текстом."):
            return

        state_peer = message.state_peer
        if state_peer is None:
            await bot.state_dispenser.delete(int(message.from_id))
            await message.answer("Состояние ответа потеряно. Откройте тикет заново.")
            return

        ticket_id = int(state_peer.payload.get("ticket_id", 0))
        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket or ticket.user_id != int(message.from_id):
            await bot.state_dispenser.delete(int(message.from_id))
            await message.answer("Тикет не найден или доступ запрещён.")
            return

        text = message.text.strip()
        await ticket_service.add_message_to_ticket(
            ticket_id=ticket_id,
            sender_type="user",
            sender_id=int(message.from_id),
            message=text,
        )

        if ticket.status == "open":
            await ticket_service.update_ticket_status(ticket_id, "in_progress")

        await _notify_moderators(
            message,
            "\n".join(
                [
                    "Новое сообщение от пользователя в тикете.",
                    f"Тикет: #{ticket_id}",
                    f"Текст: {text}",
                ]
            ),
        )

        updated_ticket = await ticket_service.get_ticket(ticket_id)
        history = await ticket_service.get_ticket_messages(ticket_id)
        await message.answer(
            format_ticket_details(updated_ticket, history) if updated_ticket else "Тикет обновлён.",
            keyboard=get_user_ticket_details_keyboard(
                ticket_id,
                updated_ticket.status if updated_ticket else "in_progress",
            ),
        )
        await bot.state_dispenser.delete(int(message.from_id))
