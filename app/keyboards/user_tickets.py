"""Клавиатуры пользовательского интерфейса раздела «Мои обращения»."""

from __future__ import annotations

from typing import List

from vkbottle import Callback, Keyboard, KeyboardButtonColor, Text

from app.database.models import Ticket
from app.keyboards.payloads import (
    CMD_BACK_TO_SUPPORT,
    CMD_MY_TICKETS,
    CMD_USER_REPLY,
    CMD_USER_TICKET,
    CMD_USER_TICKETS_PAGE,
)


def get_user_tickets_list_keyboard(
    tickets: List[Ticket],
    current_page: int,
    total_pages: int,
) -> str:
    """Формирует клавиатуру списка тикетов пользователя с пагинацией."""

    keyboard = Keyboard(inline=True)

    for ticket in tickets:
        status_emoji = {
            "open": "🆕",
            "in_progress": "🔄",
            "closed": "🔒",
        }.get(ticket.status, "❓")
        short_question = (ticket.message[:20] + "…") if len(ticket.message) > 20 else ticket.message
        label = f"{status_emoji} #{ticket.id} ({ticket.created_at.strftime('%d.%m')}): {short_question}"
        keyboard.add(
            Callback(label, payload={"cmd": CMD_USER_TICKET, "ticket_id": ticket.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        keyboard.row()

    if current_page > 1:
        keyboard.add(
            Callback(
                "⬅️ Предыдущая",
                payload={"cmd": CMD_USER_TICKETS_PAGE, "page": current_page - 1},
            ),
            color=KeyboardButtonColor.PRIMARY,
        )
    if current_page < total_pages:
        if current_page > 1:
            keyboard.row()
        keyboard.add(
            Callback(
                "Следующая ➡️",
                payload={"cmd": CMD_USER_TICKETS_PAGE, "page": current_page + 1},
            ),
            color=KeyboardButtonColor.PRIMARY,
        )

    keyboard.row()
    keyboard.add(Callback("🔙 В отдел заботы", payload={"cmd": CMD_BACK_TO_SUPPORT}))

    return keyboard.get_json()


def get_user_ticket_details_keyboard(ticket_id: int, status: str) -> str:
    """Формирует клавиатуру детального просмотра тикета пользователем."""

    keyboard = Keyboard(inline=True)
    if status != "closed":
        keyboard.add(
            Callback("✍️ Ответить", payload={"cmd": CMD_USER_REPLY, "ticket_id": ticket_id}),
            color=KeyboardButtonColor.PRIMARY,
        )
        keyboard.row()
    keyboard.add(
        Callback("📋 К списку обращений", payload={"cmd": CMD_MY_TICKETS}),
        color=KeyboardButtonColor.SECONDARY,
    )
    return keyboard.get_json()
