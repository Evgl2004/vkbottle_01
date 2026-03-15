"""Клавиатуры модератора тикетной системы."""

from __future__ import annotations

from typing import List

from vkbottle import Keyboard, KeyboardButtonColor, Text

from app.database.models import Ticket
from app.keyboards.payloads import (
    CMD_MOD_CLOSE,
    CMD_MOD_MAIN,
    CMD_MOD_REPLY,
    CMD_MOD_TICKET,
    CMD_MOD_TICKETS,
    CMD_MOD_TICKETS_PAGE,
)


def get_moderation_main_keyboard() -> str:
    """Главная клавиатура модератора с фильтрами очереди."""

    keyboard = Keyboard(inline=False)
    keyboard.add(
        Text("Все тикеты", payload={"cmd": CMD_MOD_TICKETS, "filter": "all"}),
        color=KeyboardButtonColor.PRIMARY,
    )
    keyboard.row()
    keyboard.add(
        Text("Новые тикеты", payload={"cmd": CMD_MOD_TICKETS, "filter": "open"}),
        color=KeyboardButtonColor.PRIMARY,
    )
    keyboard.row()
    keyboard.add(
        Text("Тикеты в работе", payload={"cmd": CMD_MOD_TICKETS, "filter": "in_progress"}),
        color=KeyboardButtonColor.PRIMARY,
    )
    return keyboard.get_json()


def get_moderation_tickets_keyboard(
    tickets: List[Ticket],
    current_page: int,
    total_pages: int,
    filter_key: str,
) -> str:
    """Формирует клавиатуру списка тикетов для модератора."""

    keyboard = Keyboard(inline=False)

    for ticket in tickets:
        status_emoji = {
            "open": "🆕",
            "in_progress": "🔄",
            "closed": "🔒",
        }.get(ticket.status, "❓")
        user_repr = ticket.user_username or ticket.user_first_name or str(ticket.user_id)
        label = f"{status_emoji} #{ticket.id} от {user_repr}"
        keyboard.add(
            Text(label, payload={"cmd": CMD_MOD_TICKET, "ticket_id": ticket.id, "filter": filter_key}),
            color=KeyboardButtonColor.SECONDARY,
        )
        keyboard.row()

    if current_page > 1:
        keyboard.add(
            Text(
                "Предыдущая страница",
                payload={
                    "cmd": CMD_MOD_TICKETS_PAGE,
                    "page": current_page - 1,
                    "filter": filter_key,
                },
            ),
            color=KeyboardButtonColor.PRIMARY,
        )
    if current_page < total_pages:
        if current_page > 1:
            keyboard.row()
        keyboard.add(
            Text(
                "Следующая страница",
                payload={
                    "cmd": CMD_MOD_TICKETS_PAGE,
                    "page": current_page + 1,
                    "filter": filter_key,
                },
            ),
            color=KeyboardButtonColor.PRIMARY,
        )

    keyboard.row()
    keyboard.add(Text("В меню модератора", payload={"cmd": CMD_MOD_MAIN}))
    return keyboard.get_json()


def get_moderation_ticket_details_keyboard(ticket_id: int, status: str, filter_key: str) -> str:
    """Формирует клавиатуру действий по конкретному тикету."""

    keyboard = Keyboard(inline=False)

    if status != "closed":
        keyboard.add(
            Text("Ответить", payload={"cmd": CMD_MOD_REPLY, "ticket_id": ticket_id}),
            color=KeyboardButtonColor.PRIMARY,
        )
        keyboard.row()
        keyboard.add(
            Text("Закрыть тикет", payload={"cmd": CMD_MOD_CLOSE, "ticket_id": ticket_id}),
            color=KeyboardButtonColor.NEGATIVE,
        )
        keyboard.row()

    keyboard.add(
        Text("Назад к списку", payload={"cmd": CMD_MOD_TICKETS, "filter": filter_key}),
        color=KeyboardButtonColor.SECONDARY,
    )
    return keyboard.get_json()
