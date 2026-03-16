"""Хендлеры модераторской части тикетной системы."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from loguru import logger
from vkbottle.bot import Bot, Message, MessageEvent
from vkbottle_types.events import GroupEventType

from app.database import db
from app.handlers.common import edit_or_send_event_message, extract_payload, is_moderator
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
    logger.debug(
        "Показ дашборда модератора (moderator_id={}, open_count={}, in_progress_count={}, avg_response={})",
        int(message.from_id),
        open_count,
        in_progress_count,
        avg_text,
    )
    await message.answer(
        "\n".join(
            [
                "🛠 Панель модератора:",
                f"• Новые тикеты: {open_count}",
                f"• Тикеты в работе: {in_progress_count}",
                f"• Среднее время ответа: {avg_text}",
            ]
        ),
        keyboard=get_moderation_main_keyboard(),
    )


async def _show_moderation_dashboard_event(event: MessageEvent) -> None:
    """Отправляет/перерисовывает дашборд модератора по callback-событию."""

    open_count, in_progress_count, avg_response = await ticket_service.get_tickets_stats()
    avg_text = f"{avg_response} мин" if avg_response is not None else "нет данных"
    await edit_or_send_event_message(
        event,
        "\n".join(
            [
                "🛠 Панель модератора:",
                f"• Новые тикеты: {open_count}",
                f"• Тикеты в работе: {in_progress_count}",
                f"• Среднее время ответа: {avg_text}",
            ]
        ),
        keyboard=get_moderation_main_keyboard(),
    )


async def _show_moderation_tickets_page_event(
    event: MessageEvent,
    *,
    filter_key: str,
    page: int,
) -> None:
    """Показывает страницу списка тикетов модератора по callback-событию."""

    statuses = FILTER_STATUS_MAP.get(filter_key, None)
    tickets, total_count = await ticket_service.get_tickets_page(
        page=page,
        per_page=10,
        statuses=statuses,
    )
    if not tickets:
        await edit_or_send_event_message(
            event,
            f"📭 {FILTER_TITLES.get(filter_key, 'Тикеты')} отсутствуют.",
            keyboard=get_moderation_main_keyboard(),
        )
        return

    total_pages = (total_count + 10 - 1) // 10
    await edit_or_send_event_message(
        event,
        f"{FILTER_TITLES.get(filter_key, 'Тикеты')} (страница {page}/{total_pages}):",
        keyboard=get_moderation_tickets_keyboard(tickets, page, total_pages, filter_key),
    )


async def _show_moderation_ticket_details_event(
    event: MessageEvent,
    *,
    ticket_id: int,
    filter_key: str,
) -> None:
    """Показывает карточку тикета модератору по callback-событию."""

    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket:
        await edit_or_send_event_message(event, "❌ Тикет не найден.")
        return

    history = await ticket_service.get_ticket_messages(ticket_id)
    await edit_or_send_event_message(
        event,
        format_ticket_details(ticket, history),
        keyboard=get_moderation_ticket_details_keyboard(ticket_id, ticket.status, filter_key),
    )


def register_moderation_handlers(bot: Bot) -> None:
    """Регистрирует обработчики модераторских сценариев."""

    @bot.on.private_message(text=["/mod", "модератор", "moderator"])
    @bot.on.private_message(payload_contains={"cmd": CMD_MOD_MAIN})
    async def moderation_main(message: Message) -> None:
        """Открывает главное модераторское меню."""

        user_id = int(message.from_id)
        logger.debug("Запрос открытия панели модератора (user_id={})", user_id)
        if not await is_moderator(user_id):
            logger.warning("Отказ в доступе к панели модератора (user_id={})", user_id)
            await message.answer("⛔ У вас нет прав модератора.")
            return

        await bot.state_dispenser.delete(user_id)
        logger.info("Открыта панель модератора (user_id={})", user_id)
        await _send_moderation_dashboard(message)

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_TICKETS, "filter": str})
    async def moderation_list(message: Message) -> None:
        """Показывает первую страницу тикетов по выбранному фильтру."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("⛔ У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        filter_key = payload.get("filter", "all")
        statuses = FILTER_STATUS_MAP.get(filter_key, None)
        logger.debug(
            "Модератор запросил список тикетов (user_id={}, filter={}, statuses={})",
            user_id,
            filter_key,
            statuses,
        )

        tickets, total_count = await ticket_service.get_tickets_page(
            page=1,
            per_page=10,
            statuses=statuses,
        )
        if not tickets:
            await message.answer(
                f"📭 {FILTER_TITLES.get(filter_key, 'Тикеты')} отсутствуют.",
                keyboard=get_moderation_main_keyboard(),
            )
            return

        total_pages = (total_count + 10 - 1) // 10
        logger.debug(
            "Сформирован список тикетов модератора (user_id={}, filter={}, total_count={}, total_pages={})",
            user_id,
            filter_key,
            total_count,
            total_pages,
        )
        await message.answer(
            f"{FILTER_TITLES.get(filter_key, 'Тикеты')} (страница 1/{total_pages}):",
            keyboard=get_moderation_tickets_keyboard(tickets, 1, total_pages, filter_key),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_TICKETS_PAGE, "page": int, "filter": str})
    async def moderation_page(message: Message) -> None:
        """Переключает страницу списка тикетов модератора."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("⛔ У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        page = max(int(payload.get("page", 1)), 1)
        filter_key = payload.get("filter", "all")
        statuses = FILTER_STATUS_MAP.get(filter_key, None)
        logger.debug(
            "Запрошена страница тикетов модератора (user_id={}, filter={}, page={})",
            user_id,
            filter_key,
            page,
        )

        tickets, total_count = await ticket_service.get_tickets_page(
            page=page,
            per_page=10,
            statuses=statuses,
        )
        if not tickets:
            await message.answer(
                "📭 На этой странице тикеты отсутствуют.",
                keyboard=get_moderation_main_keyboard(),
            )
            return

        total_pages = (total_count + 10 - 1) // 10
        logger.debug(
            "Сформирована страница тикетов модератора (user_id={}, page={}, total_pages={}, total_count={})",
            user_id,
            page,
            total_pages,
            total_count,
        )
        await message.answer(
            f"{FILTER_TITLES.get(filter_key, 'Тикеты')} (страница {page}/{total_pages}):",
            keyboard=get_moderation_tickets_keyboard(tickets, page, total_pages, filter_key),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_TICKET, "ticket_id": int, "filter": str})
    async def moderation_ticket_details(message: Message) -> None:
        """Показывает карточку конкретного тикета модератору."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("⛔ У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))
        filter_key = payload.get("filter", "all")
        logger.debug(
            "Запрошены детали тикета модератором (user_id={}, ticket_id={}, filter={})",
            user_id,
            ticket_id,
            filter_key,
        )

        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket:
            await message.answer("❌ Тикет не найден.")
            return

        history = await ticket_service.get_ticket_messages(ticket_id)
        logger.debug(
            "Отправка деталей тикета модератору (user_id={}, ticket_id={}, history_count={})",
            user_id,
            ticket_id,
            len(history),
        )
        await message.answer(
            format_ticket_details(ticket, history),
            keyboard=get_moderation_ticket_details_keyboard(ticket_id, ticket.status, filter_key),
        )

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_REPLY, "ticket_id": int})
    async def moderation_reply_start(message: Message) -> None:
        """Переводит модератора в режим ввода ответа по тикету."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("⛔ У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))
        logger.info("Модератор начал ввод ответа (moderator_id={}, ticket_id={})", user_id, ticket_id)
        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket:
            await message.answer("❌ Тикет не найден.")
            return
        if ticket.status == "closed":
            await message.answer("🔒 Тикет уже закрыт. Ответ невозможен.")
            return

        await bot.state_dispenser.set(
            user_id,
            TicketState.WAITING_FOR_MODERATOR_REPLY,
            ticket_id=ticket_id,
        )
        logger.debug("Переход в WAITING_FOR_MODERATOR_REPLY (moderator_id={}, ticket_id={})", user_id, ticket_id)
        await message.answer(f"✍️ Введите ответ пользователю по тикету #{ticket_id}.")

    @bot.on.private_message(state=TicketState.WAITING_FOR_MODERATOR_REPLY)
    async def moderation_reply_send(message: Message) -> None:
        """Сохраняет ответ модератора, меняет статус и уведомляет пользователя."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await bot.state_dispenser.delete(user_id)
            await message.answer("⛔ У вас нет прав модератора.")
            return
        if not await confirm_text(message, "✍️ Пожалуйста, отправьте ответ текстом."):
            return

        state_peer = message.state_peer
        if state_peer is None:
            await bot.state_dispenser.delete(user_id)
            await message.answer("⚠️ Состояние ответа потеряно. Откройте тикет заново.")
            return

        ticket_id = int(state_peer.payload.get("ticket_id", 0))
        logger.info("Получен ответ модератора (moderator_id={}, ticket_id={})", user_id, ticket_id)
        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket:
            await bot.state_dispenser.delete(user_id)
            await message.answer("❌ Тикет не найден.")
            return

        reply_text = message.text.strip()
        await ticket_service.add_message_to_ticket(
            ticket_id=ticket_id,
            sender_type="moderator",
            sender_id=user_id,
            message=reply_text,
        )
        await ticket_service.update_ticket_status(ticket_id, "in_progress")
        logger.debug("Ответ модератора сохранён, статус обновлён (ticket_id={})", ticket_id)

        # Уведомляем пользователя.
        try:
            await message.ctx_api.messages.send(
                peer_ids=[ticket.user_id],
                message="\n".join(
                    [
                        f"💬 Ответ модератора по тикету #{ticket_id}:",
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
        logger.debug("Состояние WAITING_FOR_MODERATOR_REPLY очищено (moderator_id={})", user_id)

    @bot.on.private_message(payload_map={"cmd": CMD_MOD_CLOSE, "ticket_id": int})
    async def moderation_close_ticket(message: Message) -> None:
        """Закрывает тикет и показывает обновлённую карточку."""

        user_id = int(message.from_id)
        if not await is_moderator(user_id):
            await message.answer("⛔ У вас нет прав модератора.")
            return

        payload = extract_payload(message)
        ticket_id = int(payload.get("ticket_id"))
        logger.info("Запрошено закрытие тикета модератором (moderator_id={}, ticket_id={})", user_id, ticket_id)

        ok = await ticket_service.close_ticket(ticket_id)
        if not ok:
            logger.warning("Не удалось закрыть тикет: не найден (ticket_id={})", ticket_id)
            await message.answer("❌ Не удалось закрыть тикет: запись не найдена.")
            return

        logger.info("Тикет закрыт модератором (moderator_id={}, ticket_id={})", user_id, ticket_id)
        ticket = await ticket_service.get_ticket(ticket_id)
        history = await ticket_service.get_ticket_messages(ticket_id)
        await message.answer(
            format_ticket_details(ticket, history) if ticket else "Тикет закрыт.",
            keyboard=get_moderation_ticket_details_keyboard(ticket_id, "closed", "all"),
        )

    @bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent)
    async def moderation_callback_router(event: MessageEvent) -> None:
        """Обрабатывает callback-кнопки модераторского интерфейса."""

        payload: dict[str, Any] = event.get_payload_json() or {}
        command = payload.get("cmd")
        if command not in {
            CMD_MOD_MAIN,
            CMD_MOD_TICKETS,
            CMD_MOD_TICKETS_PAGE,
            CMD_MOD_TICKET,
            CMD_MOD_REPLY,
            CMD_MOD_CLOSE,
        }:
            return

        await event.send_empty_answer()
        user_id = int(event.user_id)
        if not await is_moderator(user_id):
            await edit_or_send_event_message(event, "⛔ У вас нет прав модератора.")
            return

        logger.debug(
            "moderation callback (user_id={}, peer_id={}, cmd={}, payload={})",
            user_id,
            int(event.peer_id),
            command,
            payload,
        )

        if command == CMD_MOD_MAIN:
            await bot.state_dispenser.delete(user_id)
            await _show_moderation_dashboard_event(event)
            return

        if command == CMD_MOD_TICKETS:
            filter_key = str(payload.get("filter", "all"))
            await _show_moderation_tickets_page_event(event, filter_key=filter_key, page=1)
            return

        if command == CMD_MOD_TICKETS_PAGE:
            filter_key = str(payload.get("filter", "all"))
            try:
                page = max(int(payload.get("page", 1)), 1)
            except (TypeError, ValueError):
                page = 1
            await _show_moderation_tickets_page_event(event, filter_key=filter_key, page=page)
            return

        if command == CMD_MOD_TICKET:
            filter_key = str(payload.get("filter", "all"))
            try:
                ticket_id = int(payload.get("ticket_id"))
            except (TypeError, ValueError):
                await edit_or_send_event_message(event, "⚠️ Не удалось определить тикет.")
                return
            await _show_moderation_ticket_details_event(event, ticket_id=ticket_id, filter_key=filter_key)
            return

        if command == CMD_MOD_REPLY:
            try:
                ticket_id = int(payload.get("ticket_id"))
            except (TypeError, ValueError):
                await edit_or_send_event_message(event, "⚠️ Не удалось определить тикет.")
                return

            ticket = await ticket_service.get_ticket(ticket_id)
            if not ticket:
                await edit_or_send_event_message(event, "❌ Тикет не найден.")
                return
            if ticket.status == "closed":
                await edit_or_send_event_message(event, "🔒 Тикет уже закрыт. Ответ невозможен.")
                return

            await bot.state_dispenser.set(
                user_id,
                TicketState.WAITING_FOR_MODERATOR_REPLY,
                ticket_id=ticket_id,
            )
            await edit_or_send_event_message(event, f"✍️ Введите ответ пользователю по тикету #{ticket_id}.")
            return

        if command == CMD_MOD_CLOSE:
            try:
                ticket_id = int(payload.get("ticket_id"))
            except (TypeError, ValueError):
                await edit_or_send_event_message(event, "⚠️ Не удалось определить тикет.")
                return

            ok = await ticket_service.close_ticket(ticket_id)
            if not ok:
                await edit_or_send_event_message(event, "❌ Не удалось закрыть тикет: запись не найдена.")
                return

            await _show_moderation_ticket_details_event(event, ticket_id=ticket_id, filter_key="all")
