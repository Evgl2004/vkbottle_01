"""Хендлеры пользовательского раздела обращений (тикеты)."""

from __future__ import annotations

from typing import Any, List

from loguru import logger
from vkbottle.bot import Bot, Message, MessageEvent
from vkbottle_types.events import GroupEventType

from app.database import db
from app.handlers.common import edit_or_send_event_message, extract_payload, get_moderator_ids
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
    logger.debug(
        "Рассылка уведомления модераторам (from_user_id={}, moderators_count={})",
        int(message.from_id),
        len(moderator_ids),
    )
    for moderator_id in moderator_ids:
        try:
            await message.ctx_api.messages.send(
                peer_ids=[moderator_id],
                message=text,
                random_id=0,
            )
        except Exception as error:
            logger.error("Не удалось уведомить модератора {}: {}", moderator_id, error)


async def _show_user_tickets_page_event(event: MessageEvent, page: int) -> None:
    """Отображает страницу пользовательских тикетов по callback-событию."""

    user_id = int(event.user_id)
    tickets, total_count = await ticket_service.get_tickets_page(
        page=page,
        per_page=5,
        user_id=user_id,
    )
    if not tickets:
        await edit_or_send_event_message(
            event,
            "📭 На этой странице обращений нет.",
            keyboard=get_back_to_support_keyboard(),
        )
        return

    total_pages = (total_count + 5 - 1) // 5
    await edit_or_send_event_message(
        event,
        f"📋 Ваши обращения (страница {page}/{total_pages}):",
        keyboard=get_user_tickets_list_keyboard(tickets, page, total_pages),
    )


async def _show_user_ticket_details_event(event: MessageEvent, ticket_id: int) -> None:
    """Показывает карточку тикета пользователю по callback-событию."""

    user_id = int(event.user_id)
    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket or ticket.user_id != user_id:
        await edit_or_send_event_message(event, "❌ Тикет не найден или доступ запрещён.")
        return

    history = await ticket_service.get_ticket_messages(ticket_id)
    await edit_or_send_event_message(
        event,
        format_ticket_details(ticket, history),
        keyboard=get_user_ticket_details_keyboard(ticket_id, ticket.status),
    )


def register_user_ticket_handlers(bot: Bot) -> None:
    """Регистрирует обработчики пользовательских тикетов."""

    @bot.on.private_message(state=TicketState.WAITING_FOR_QUESTION)
    async def create_ticket_from_question(message: Message) -> None:
        """Создает новый тикет на основе сообщения пользователя."""

        if not await confirm_text(message, "✍️ Пожалуйста, отправьте вопрос текстом."):
            return

        user_id = int(message.from_id)
        logger.info("Создание тикета из вопроса пользователя (user_id={})", user_id)
        user = await db.get_user(user_id)
        if not user:
            await bot.state_dispenser.delete(user_id)
            logger.error("Невозможно создать тикет: пользователь не найден (user_id={})", user_id)
            await message.answer("❌ Пользователь не найден. Введите /start для повторной инициализации.")
            return

        ticket = await ticket_service.create_ticket(
            user_id=user_id,
            message=message.text.strip(),
            user_username=user.username,
            user_first_name=user.first_name_input or user.first_name,
        )
        logger.info("Создан тикет (ticket_id={}, user_id={})", ticket.id, user_id)

        await message.answer(
            "\n".join(
                [
                    "✅ Ваше обращение принято.",
                    f"🎫 Номер тикета: #{ticket.id}",
                    "🕐 Модератор ответит в ближайшее время.",
                ]
            ),
            keyboard=get_back_to_main_keyboard(),
        )

        await _notify_moderators(
            message,
            "\n".join(
                [
                    "📬 Новое обращение пользователя.",
                    f"🎫 Тикет: #{ticket.id}",
                    f"👤 Пользователь: {user.username or user.first_name_input or user_id}",
                    f"❓ Текст: {message.text.strip()}",
                ]
            ),
        )

        await bot.state_dispenser.delete(user_id)
        logger.debug("Состояние TicketState очищено после создания тикета (user_id={})", user_id)

    @bot.on.private_message(payload_contains={"cmd": CMD_MY_TICKETS})
    async def user_tickets_list(message: Message) -> None:
        """Показывает первую страницу списка обращений пользователя."""

        user_id = int(message.from_id)
        logger.debug("Запрошен список тикетов пользователя (user_id={})", user_id)
        tickets, total_count = await ticket_service.get_tickets_page(
            page=1,
            per_page=5,
            user_id=user_id,
        )
        if not tickets:
            await message.answer(
                "📭 У вас пока нет обращений. Создать обращение можно через раздел «Отдел заботы».",
                keyboard=get_back_to_support_keyboard(),
            )
            return

        total_pages = (total_count + 5 - 1) // 5
        logger.debug(
            "Сформирована первая страница тикетов пользователя (user_id={}, total_count={}, total_pages={})",
            user_id,
            total_count,
            total_pages,
        )
        await message.answer(
            f"📋 Ваши обращения (страница 1/{total_pages}):",
            keyboard=get_user_tickets_list_keyboard(tickets, 1, total_pages),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_USER_TICKETS_PAGE, "page": int})
    async def user_tickets_page(message: Message) -> None:
        """Переключает страницу списка пользовательских обращений."""

        payload = extract_payload(message)
        page = int(payload.get("page", 1))
        page = max(page, 1)
        logger.debug("Запрошена страница тикетов пользователя (user_id={}, page={})", int(message.from_id), page)

        tickets, total_count = await ticket_service.get_tickets_page(
            page=page,
            per_page=5,
            user_id=int(message.from_id),
        )
        if not tickets:
            await message.answer(
                "📭 На этой странице обращений нет.",
                keyboard=get_back_to_support_keyboard(),
            )
            return

        total_pages = (total_count + 5 - 1) // 5
        logger.debug(
            "Сформирована страница тикетов пользователя (user_id={}, page={}, total_pages={}, total_count={})",
            int(message.from_id),
            page,
            total_pages,
            total_count,
        )
        await message.answer(
            f"📋 Ваши обращения (страница {page}/{total_pages}):",
            keyboard=get_user_tickets_list_keyboard(tickets, page, total_pages),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_USER_TICKET, "ticket_id": int})
    async def user_ticket_details(message: Message) -> None:
        """Показывает карточку конкретного тикета пользователю."""

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))
        logger.debug("Запрошены детали тикета пользователем (user_id={}, ticket_id={})", int(message.from_id), ticket_id)

        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket or ticket.user_id != int(message.from_id):
            await message.answer("❌ Тикет не найден или доступ запрещён.")
            return

        history = await ticket_service.get_ticket_messages(ticket_id)
        logger.debug(
            "Отправка деталей тикета пользователю (user_id={}, ticket_id={}, history_count={})",
            int(message.from_id),
            ticket_id,
            len(history),
        )
        await message.answer(
            format_ticket_details(ticket, history),
            keyboard=get_user_ticket_details_keyboard(ticket_id, ticket.status),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_USER_REPLY, "ticket_id": int})
    async def user_reply_start(message: Message) -> None:
        """Переводит пользователя в состояние отправки ответа по тикету."""

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))
        logger.info("Пользователь начал ввод ответа по тикету (user_id={}, ticket_id={})", int(message.from_id), ticket_id)

        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket or ticket.user_id != int(message.from_id):
            await message.answer("❌ Тикет не найден или доступ запрещён.")
            return
        if ticket.status == "closed":
            await message.answer("🔒 Тикет уже закрыт. Отправка нового ответа невозможна.")
            return

        await bot.state_dispenser.set(
            int(message.from_id),
            TicketState.WAITING_FOR_USER_REPLY,
            ticket_id=ticket_id,
        )
        logger.debug("Переход в WAITING_FOR_USER_REPLY (user_id={}, ticket_id={})", int(message.from_id), ticket_id)
        await message.answer(
            f"✍️ Введите ответ для тикета #{ticket_id}.",
            keyboard=get_user_ticket_details_keyboard(ticket_id, ticket.status),
        )

    @bot.on.private_message(state=TicketState.WAITING_FOR_USER_REPLY)
    async def user_reply_send(message: Message) -> None:
        """Сохраняет ответ пользователя и уведомляет модераторов."""

        if not await confirm_text(message, "✍️ Пожалуйста, отправьте ответ текстом."):
            return

        state_peer = message.state_peer
        if state_peer is None:
            await bot.state_dispenser.delete(int(message.from_id))
            await message.answer("⚠️ Состояние ответа потеряно. Откройте тикет заново.")
            return

        ticket_id = int(state_peer.payload.get("ticket_id", 0))
        logger.info("Получен ответ пользователя по тикету (user_id={}, ticket_id={})", int(message.from_id), ticket_id)
        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket or ticket.user_id != int(message.from_id):
            await bot.state_dispenser.delete(int(message.from_id))
            await message.answer("❌ Тикет не найден или доступ запрещён.")
            return

        text = message.text.strip()
        await ticket_service.add_message_to_ticket(
            ticket_id=ticket_id,
            sender_type="user",
            sender_id=int(message.from_id),
            message=text,
        )
        logger.debug("Сообщение пользователя добавлено в тикет (ticket_id={})", ticket_id)

        if ticket.status == "open":
            await ticket_service.update_ticket_status(ticket_id, "in_progress")
            logger.debug("Статус тикета переведен в in_progress (ticket_id={})", ticket_id)

        await _notify_moderators(
            message,
            "\n".join(
                [
                    "💬 Новое сообщение от пользователя в тикете.",
                    f"🎫 Тикет: #{ticket_id}",
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
        logger.debug("Состояние WAITING_FOR_USER_REPLY очищено (user_id={})", int(message.from_id))

    @bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent, blocking=False)
    async def user_tickets_callback_router(event: MessageEvent) -> None:
        """Обрабатывает callback-кнопки пользовательского раздела тикетов."""

        payload: dict[str, Any] = event.get_payload_json() or {}
        command = payload.get("cmd")
        if command not in {CMD_MY_TICKETS, CMD_USER_TICKETS_PAGE, CMD_USER_TICKET, CMD_USER_REPLY}:
            return

        await event.send_empty_answer()
        user_id = int(event.user_id)
        logger.debug(
            "user_tickets callback (user_id={}, peer_id={}, cmd={}, payload={})",
            user_id,
            int(event.peer_id),
            command,
            payload,
        )

        if command == CMD_MY_TICKETS:
            await _show_user_tickets_page_event(event, page=1)
            return

        if command == CMD_USER_TICKETS_PAGE:
            try:
                page = max(int(payload.get("page", 1)), 1)
            except (TypeError, ValueError):
                page = 1
            await _show_user_tickets_page_event(event, page=page)
            return

        if command == CMD_USER_TICKET:
            try:
                ticket_id = int(payload.get("ticket_id"))
            except (TypeError, ValueError):
                await edit_or_send_event_message(event, "⚠️ Не удалось определить тикет.")
                return
            await _show_user_ticket_details_event(event, ticket_id=ticket_id)
            return

        if command == CMD_USER_REPLY:
            try:
                ticket_id = int(payload.get("ticket_id"))
            except (TypeError, ValueError):
                await edit_or_send_event_message(event, "⚠️ Не удалось определить тикет.")
                return

            ticket = await ticket_service.get_ticket(ticket_id)
            if not ticket or ticket.user_id != user_id:
                await edit_or_send_event_message(event, "❌ Тикет не найден или доступ запрещён.")
                return
            if ticket.status == "closed":
                await edit_or_send_event_message(event, "🔒 Тикет уже закрыт. Отправка нового ответа невозможна.")
                return

            await bot.state_dispenser.set(
                user_id,
                TicketState.WAITING_FOR_USER_REPLY,
                ticket_id=ticket_id,
            )
            await edit_or_send_event_message(
                event,
                f"✍️ Введите ответ для тикета #{ticket_id}.",
                keyboard=get_user_ticket_details_keyboard(ticket_id, ticket.status),
            )
