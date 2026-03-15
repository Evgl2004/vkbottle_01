"""Пакет работы с базой данных.

Экспортирует:
1. глобальный объект `db` для выполнения операций;
2. ORM-модели, используемые сервисным и транспортным слоями.
"""

from app.database.database import db
from app.database.models import Base, BotStats, MigrationHistory, Ticket, TicketMessage, User

__all__ = ["db", "Base", "User", "BotStats", "MigrationHistory", "Ticket", "TicketMessage"]
