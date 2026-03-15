"""Форматирование карточек тикетов для сообщений VK."""

from __future__ import annotations

from typing import List, Optional

from app.database.models import Ticket, TicketMessage


def localize_status(status: str) -> str:
    """Локализует внутренний статус тикета на русский язык."""
    return {
        "open": "Открыт",
        "in_progress": "В работе",
        "closed": "Закрыт",
    }.get(status, status)


def format_ticket_details(ticket: Ticket, messages: Optional[List[TicketMessage]] = None) -> str:
    """Формирует подробный текст карточки тикета.

    В вывод включаются:
    1. базовые сведения о тикете;
    2. история переписки (если передана);
    3. дата закрытия (для статуса `closed`).
    """

    status_emoji = {
        "open": "🆕",
        "in_progress": "🔄",
        "closed": "🔒",
    }.get(ticket.status, "❓")

    user_repr = ticket.user_username or ticket.user_first_name or str(ticket.user_id)
    created_at = ticket.created_at.strftime("%d.%m.%Y %H:%M")

    text = (
        f"{status_emoji} Тикет #{ticket.id}\n"
        f"Пользователь: {user_repr}\n"
        f"Статус: {localize_status(ticket.status)}\n"
        f"Создан: {created_at}\n\n"
        f"Первичный вопрос:\n{ticket.message}"
    )

    if messages:
        text += "\n\nИстория переписки:"
        for message in messages:
            author = "Пользователь" if message.sender_type == "user" else "Модератор"
            created = message.created_at.strftime("%d.%m %H:%M")
            text += f"\n\n[{created}] {author}:\n{message.message}"

    if ticket.status == "closed" and ticket.closed_at:
        text += f"\n\nЗакрыт: {ticket.closed_at.strftime('%d.%m.%Y %H:%M')}"

    return text
