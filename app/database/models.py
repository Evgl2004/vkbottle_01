"""SQLAlchemy-модели домена VK-бота.

В модуле описываются:
1. пользовательская таблица с регистрационными и юридическими полями;
2. таблицы тикетной системы;
3. агрегированная статистика бота;
4. журнал применения миграций.

Подход:
- схема близка к референсному Telegram-проекту для сохранения
  бизнес-совместимости и упрощения переноса логики.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Базовый класс всех ORM-моделей проекта."""


class User(Base):
    """Модель пользователя бота.

    В таблице объединены:
    1. технические поля профиля из VK;
    2. поля анкеты регистрации;
    3. флаги прав и активности;
    4. юридически значимые согласия.
    """

    __tablename__ = "users"

    # Идентификаторы и базовый профиль.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Роли и флаги активности.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_moderator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Согласие на правила/ПДн.
    rules_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rules_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Согласие на уведомления.
    notifications_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notifications_allowed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Флаги жизненного цикла.
    is_legacy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Поля анкеты лояльности.
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    phone_verification_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    first_name_input: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name_input: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Системные метки.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} registered={self.is_registered}>"


class BotStats(Base):
    """Модель агрегированной статистики бота.

    В текущей версии хранит:
    - общее количество пользователей;
    - число активных пользователей;
    - момент последнего старта/обновления.
    """

    __tablename__ = "bot_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    total_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_restart: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<BotStats total={self.total_users} active={self.active_users} status={self.status}>"


class MigrationHistory(Base):
    """Журнал применения миграций схемы.

    Таблица не заменяет полноценный Alembic, но позволяет
    фиксировать историю обновлений структуры БД в рамках проекта.
    """

    __tablename__ = "migration_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<MigrationHistory version={self.version} name={self.name!r}>"


class Ticket(Base):
    """Модель обращения пользователя в отдел заботы/поддержки."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    first_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Ticket id={self.id} user_id={self.user_id} status={self.status}>"


class TicketMessage(Base):
    """Модель сообщения в переписке по тикету."""

    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sender_type: Mapped[str] = mapped_column(String(10), nullable=False)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<TicketMessage id={self.id} ticket_id={self.ticket_id} sender_type={self.sender_type}>"
