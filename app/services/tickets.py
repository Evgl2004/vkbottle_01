"""Сервисный слой работы с тикетами.

Сервис инкапсулирует правила обращения к БД для тикетной системы,
чтобы хендлеры не зависели от SQL-деталей.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from loguru import logger

from app.database import db
from app.database.models import Ticket, TicketMessage


class TicketService:
    """Сервис тикетной системы."""

    async def create_ticket(
        self,
        user_id: int,
        message: str,
        user_username: Optional[str] = None,
        user_first_name: Optional[str] = None,
    ) -> Ticket:
        """Создает новое обращение пользователя."""
        logger.debug("TicketService.create_ticket(user_id={})", user_id)
        return await db.create_ticket(
            user_id=user_id,
            message=message,
            user_username=user_username,
            user_first_name=user_first_name,
        )

    async def get_ticket(self, ticket_id: int) -> Optional[Ticket]:
        """Возвращает тикет по ID."""
        logger.debug("TicketService.get_ticket(ticket_id={})", ticket_id)
        return await db.get_ticket(ticket_id)

    async def add_message_to_ticket(
        self,
        ticket_id: int,
        sender_type: str,
        sender_id: int,
        message: str,
    ) -> TicketMessage:
        """Добавляет сообщение в переписку тикета."""
        logger.debug(
            "TicketService.add_message_to_ticket(ticket_id={}, sender_type={}, sender_id={})",
            ticket_id,
            sender_type,
            sender_id,
        )
        return await db.add_ticket_message(
            ticket_id=ticket_id,
            sender_type=sender_type,
            sender_id=sender_id,
            message=message,
        )

    async def get_ticket_messages(self, ticket_id: int) -> List[TicketMessage]:
        """Возвращает историю переписки тикета."""
        logger.debug("TicketService.get_ticket_messages(ticket_id={})", ticket_id)
        return await db.get_ticket_messages(ticket_id)

    async def update_ticket_status(self, ticket_id: int, status: str) -> bool:
        """Обновляет статус тикета."""
        logger.debug("TicketService.update_ticket_status(ticket_id={}, status={})", ticket_id, status)
        return await db.update_ticket_status(ticket_id, status)

    async def close_ticket(self, ticket_id: int) -> bool:
        """Закрывает тикет."""
        logger.debug("TicketService.close_ticket(ticket_id={})", ticket_id)
        return await db.close_ticket(ticket_id)

    async def get_tickets_page(
        self,
        page: int = 1,
        per_page: int = 10,
        statuses: Optional[Sequence[str]] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[List[Ticket], int]:
        """Возвращает страницу тикетов и общее число записей."""
        logger.debug(
            "TicketService.get_tickets_page(page={}, per_page={}, statuses={}, user_id={})",
            page,
            per_page,
            statuses,
            user_id,
        )
        return await db.get_tickets_page(
            page=page,
            per_page=per_page,
            statuses=statuses,
            user_id=user_id,
        )

    async def get_user_tickets_count(self, user_id: int) -> int:
        """Возвращает количество тикетов пользователя."""
        logger.debug("TicketService.get_user_tickets_count(user_id={})", user_id)
        return await db.get_user_tickets_count(user_id)

    async def get_tickets_stats(self):
        """Возвращает агрегированную статистику по тикетам."""
        logger.debug("TicketService.get_tickets_stats()")
        return await db.get_tickets_stats()


ticket_service = TicketService()
