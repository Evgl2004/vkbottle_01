"""Асинхронный слой доступа к PostgreSQL.

Модуль реализует единый объект `Database`, который:
1. управляет SQLAlchemy engine/session;
2. предоставляет прикладные методы для пользователей, статистики и тикетов;
3. скрывает SQL-детали от хендлеров.

Почему это важно:
- хендлеры остаются «тонкими» и не содержат SQL;
- бизнес-логика легче тестируется и переиспользуется;
- снижается риск дублирования запросов.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database.models import Base, BotStats, Ticket, TicketMessage, User


class Database:
    """Асинхронный репозиторий доменных данных."""

    def __init__(self) -> None:
        """Инициализирует engine и фабрику сессий SQLAlchemy."""

        self.engine = create_async_engine(
            settings.async_database_url,
            echo=False,
            pool_pre_ping=True,
        )
        self.session_maker = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def create_tables(self) -> None:
        """Создает таблицы по ORM-моделям.

        Важно:
        - Метод предназначен для dev/MVP-сценариев.
        - В production-режиме рекомендуется управлять схемой через миграции.
        """

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        logger.info("Таблицы базы данных успешно инициализированы")

    # -----------------------------------------------------------------
    # Пользователи
    # -----------------------------------------------------------------
    async def add_or_update_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Создает пользователя или обновляет базовый профиль.

        Используется на каждом входящем событии:
        - если запись уже есть, обновляются актуальные данные профиля;
        - если записи нет, пользователь создается.
        """

        logger.debug(
            "DB add_or_update_user: user_id={}, username={}, first_name='{}', last_name='{}'",
            user_id,
            username,
            first_name,
            last_name,
        )
        async with self.session_maker() as session:
            user = await session.get(User, user_id)
            if user:
                user.username = username
                user.first_name = first_name
                user.last_name = last_name
                user.is_active = True
                user.updated_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(user)
                logger.debug("DB add_or_update_user: обновлена существующая запись (user_id={})", user_id)
                return user

            user = User(
                id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info("DB add_or_update_user: создан новый пользователь (user_id={})", user_id)
            return user

    async def get_user(self, user_id: int) -> Optional[User]:
        """Возвращает пользователя по ID или `None`, если запись отсутствует."""
        async with self.session_maker() as session:
            user = await session.get(User, user_id)
            logger.debug("DB get_user: user_id={}, found={}", user_id, bool(user))
            return user

    async def update_user(self, user_id: int, **fields) -> Optional[User]:
        """Частично обновляет поля пользователя.

        Аргументы:
        - `user_id`: идентификатор пользователя;
        - `**fields`: произвольный набор полей модели `User`.

        Поведение:
        - обновляются только реально существующие поля модели;
        - при отсутствии пользователя возвращается `None`.
        """

        logger.debug("DB update_user: user_id={}, fields={}", user_id, list(fields.keys()))
        async with self.session_maker() as session:
            user = await session.get(User, user_id)
            if not user:
                logger.warning("DB update_user: пользователь не найден (user_id={})", user_id)
                return None

            for key, value in fields.items():
                if hasattr(user, key):
                    setattr(user, key, value)
                else:
                    logger.warning(
                        "Попытка обновления неизвестного поля `{}` у пользователя {}",
                        key,
                        user_id,
                    )

            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(user)
            logger.debug("DB update_user: обновление успешно (user_id={})", user_id)
            return user

    async def get_users_count(self) -> int:
        """Возвращает общее количество пользователей."""
        async with self.session_maker() as session:
            return int((await session.scalar(select(func.count(User.id)))) or 0)

    async def get_active_users_count(self) -> int:
        """Возвращает количество активных пользователей."""
        async with self.session_maker() as session:
            return int(
                (
                    await session.scalar(
                        select(func.count(User.id)).where(User.is_active.is_(True))
                    )
                )
                or 0
            )

    async def get_active_users(self) -> List[User]:
        """Возвращает список активных пользователей (для рассылок/уведомлений)."""
        async with self.session_maker() as session:
            result = await session.execute(select(User).where(User.is_active.is_(True)))
            return list(result.scalars().all())

    async def get_moderators(self) -> List[User]:
        """Возвращает список пользователей с флагом `is_moderator=True`."""
        async with self.session_maker() as session:
            result = await session.execute(select(User).where(User.is_moderator.is_(True)))
            moderators = list(result.scalars().all())
            logger.debug("DB get_moderators: count={}", len(moderators))
            return moderators

    async def is_user_moderator(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь модератором по данным БД."""
        async with self.session_maker() as session:
            user = await session.get(User, user_id)
            is_mod = bool(user and user.is_moderator)
            logger.debug("DB is_user_moderator: user_id={}, is_moderator={}", user_id, is_mod)
            return is_mod

    # -----------------------------------------------------------------
    # Статистика бота
    # -----------------------------------------------------------------
    async def get_bot_stats(self) -> Optional[BotStats]:
        """Возвращает последнюю запись агрегированной статистики."""
        async with self.session_maker() as session:
            rows = await session.execute(select(BotStats).order_by(BotStats.id.desc()).limit(1))
            return rows.scalar_one_or_none()

    async def update_bot_stats(self) -> BotStats:
        """Обновляет агрегированную статистику запуска/пользователей."""

        async with self.session_maker() as session:
            total_users = await self.get_users_count()
            active_users = await self.get_active_users_count()

            rows = await session.execute(select(BotStats).order_by(BotStats.id.desc()).limit(1))
            stats = rows.scalar_one_or_none()

            if stats:
                stats.total_users = total_users
                stats.active_users = active_users
                stats.last_restart = datetime.now(timezone.utc)
            else:
                stats = BotStats(
                    total_users=total_users,
                    active_users=active_users,
                    last_restart=datetime.now(timezone.utc),
                    status="active",
                )
                session.add(stats)

            await session.commit()
            await session.refresh(stats)
            logger.debug(
                "DB update_bot_stats: total_users={}, active_users={}, last_restart={}",
                stats.total_users,
                stats.active_users,
                stats.last_restart,
            )
            return stats

    # -----------------------------------------------------------------
    # Тикетная система
    # -----------------------------------------------------------------
    async def create_ticket(
        self,
        user_id: int,
        message: str,
        user_username: Optional[str] = None,
        user_first_name: Optional[str] = None,
    ) -> Ticket:
        """Создает новый тикет пользователя."""
        logger.debug("DB create_ticket: user_id={}, user_username={}", user_id, user_username)
        async with self.session_maker() as session:
            ticket = Ticket(
                user_id=user_id,
                message=message,
                user_username=user_username,
                user_first_name=user_first_name,
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            logger.info("DB create_ticket: создан тикет ticket_id={}, user_id={}", ticket.id, user_id)
            return ticket

    async def get_ticket(self, ticket_id: int) -> Optional[Ticket]:
        """Возвращает тикет по ID."""
        async with self.session_maker() as session:
            ticket = await session.get(Ticket, ticket_id)
            logger.debug("DB get_ticket: ticket_id={}, found={}", ticket_id, bool(ticket))
            return ticket

    async def update_ticket_status(self, ticket_id: int, status: str) -> bool:
        """Обновляет статус тикета и связанные временные поля.

        Логика:
        1. `open -> in_progress` устанавливает `first_response_at` (если ранее не было).
        2. любой переход в `closed` устанавливает `closed_at`.
        3. обновляется `updated_at`.
        """

        logger.debug("DB update_ticket_status: ticket_id={}, new_status={}", ticket_id, status)
        async with self.session_maker() as session:
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                logger.warning("DB update_ticket_status: тикет не найден (ticket_id={})", ticket_id)
                return False

            if status == "in_progress" and ticket.status == "open" and ticket.first_response_at is None:
                ticket.first_response_at = datetime.now(timezone.utc)

            if status == "closed" and ticket.status != "closed":
                ticket.closed_at = datetime.now(timezone.utc)

            ticket.status = status
            ticket.updated_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("DB update_ticket_status: статус обновлён (ticket_id={}, status={})", ticket_id, status)
            return True

    async def close_ticket(self, ticket_id: int) -> bool:
        """Сокращенный метод закрытия тикета."""
        return await self.update_ticket_status(ticket_id, "closed")

    async def add_ticket_message(
        self,
        ticket_id: int,
        sender_type: str,
        sender_id: int,
        message: str,
    ) -> TicketMessage:
        """Добавляет сообщение в историю диалога по тикету."""
        logger.debug(
            "DB add_ticket_message: ticket_id={}, sender_type={}, sender_id={}",
            ticket_id,
            sender_type,
            sender_id,
        )
        async with self.session_maker() as session:
            row = TicketMessage(
                ticket_id=ticket_id,
                sender_type=sender_type,
                sender_id=sender_id,
                message=message,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            logger.info(
                "DB add_ticket_message: сообщение сохранено (message_id={}, ticket_id={}, sender_type={})",
                row.id,
                ticket_id,
                sender_type,
            )
            return row

    async def get_ticket_messages(self, ticket_id: int) -> List[TicketMessage]:
        """Возвращает историю сообщений тикета в порядке возрастания времени."""
        async with self.session_maker() as session:
            result = await session.execute(
                select(TicketMessage)
                .where(TicketMessage.ticket_id == ticket_id)
                .order_by(TicketMessage.created_at.asc())
            )
            messages = list(result.scalars().all())
            logger.debug("DB get_ticket_messages: ticket_id={}, count={}", ticket_id, len(messages))
            return messages

    async def get_tickets_page(
        self,
        page: int = 1,
        per_page: int = 10,
        statuses: Optional[Sequence[str]] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[List[Ticket], int]:
        """Возвращает страницу тикетов и общее количество записей.

        Параметры:
        - `page`: номер страницы (начиная с 1);
        - `per_page`: размер страницы;
        - `statuses`: опциональный фильтр по статусам;
        - `user_id`: если передан, выборка ограничивается тикетами пользователя.
        """

        logger.debug(
            "DB get_tickets_page: page={}, per_page={}, statuses={}, user_id={}",
            page,
            per_page,
            statuses,
            user_id,
        )
        async with self.session_maker() as session:
            query = select(Ticket)

            if statuses:
                query = query.where(Ticket.status.in_(list(statuses)))

            if user_id is not None:
                query = query.where(Ticket.user_id == user_id)

            query = query.order_by(Ticket.created_at.desc())

            count_query = select(func.count()).select_from(query.subquery())
            total_count = int((await session.scalar(count_query)) or 0)

            query = query.offset((page - 1) * per_page).limit(per_page)
            rows = await session.execute(query)
            tickets = list(rows.scalars().all())
            logger.debug(
                "DB get_tickets_page: fetched={}, total_count={}, page={}, per_page={}",
                len(tickets),
                total_count,
                page,
                per_page,
            )
            return tickets, total_count

    async def get_user_tickets_count(self, user_id: int) -> int:
        """Возвращает количество тикетов конкретного пользователя."""
        async with self.session_maker() as session:
            value = await session.scalar(select(func.count(Ticket.id)).where(Ticket.user_id == user_id))
            count = int(value or 0)
            logger.debug("DB get_user_tickets_count: user_id={}, count={}", user_id, count)
            return count

    async def get_tickets_stats(self) -> Tuple[int, int, Optional[float]]:
        """Возвращает сводную статистику тикетов.

        Результат:
        1. количество `open`;
        2. количество `in_progress`;
        3. среднее время первого ответа (в минутах), если доступно.
        """

        logger.debug("DB get_tickets_stats")
        async with self.session_maker() as session:
            open_count = int(
                (await session.scalar(select(func.count(Ticket.id)).where(Ticket.status == "open"))) or 0
            )
            in_progress_count = int(
                (
                    await session.scalar(
                        select(func.count(Ticket.id)).where(Ticket.status == "in_progress")
                    )
                )
                or 0
            )

            avg_query = text(
                """
                SELECT AVG(EXTRACT(EPOCH FROM (first_response_at - created_at)) / 60)
                FROM tickets
                WHERE first_response_at IS NOT NULL
                """
            )
            row = (await session.execute(avg_query)).fetchone()
            avg_response = round(float(row[0]), 1) if row and row[0] is not None else None

            logger.debug(
                "DB get_tickets_stats: open_count={}, in_progress_count={}, avg_response={}",
                open_count,
                in_progress_count,
                avg_response,
            )
            return open_count, in_progress_count, avg_response


# Глобальный экземпляр репозитория, используемый по всему приложению.
db = Database()
