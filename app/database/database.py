"""Async database gateway."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database.models import Base, BotStats, Ticket, TicketMessage, User


class Database:
    """Thin async repository for core entities."""

    def __init__(self) -> None:
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
        """Create schema for local/dev startup."""
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        logger.info("database schema ready")

    async def add_or_update_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Create user row or refresh messenger profile fields."""
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
            return user

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by id."""
        async with self.session_maker() as session:
            return await session.get(User, user_id)

    async def update_user(self, user_id: int, **fields) -> Optional[User]:
        """Patch user fields."""
        async with self.session_maker() as session:
            user = await session.get(User, user_id)
            if not user:
                return None

            for key, value in fields.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(user)
            return user

    async def get_users_count(self) -> int:
        """Count all users."""
        async with self.session_maker() as session:
            return int((await session.scalar(select(func.count(User.id)))) or 0)

    async def get_active_users_count(self) -> int:
        """Count active users."""
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
        """Get active users list."""
        async with self.session_maker() as session:
            rows = await session.execute(select(User).where(User.is_active.is_(True)))
            return list(rows.scalars().all())

    async def get_moderators(self) -> List[User]:
        """Get users with moderator flag."""
        async with self.session_maker() as session:
            rows = await session.execute(select(User).where(User.is_moderator.is_(True)))
            return list(rows.scalars().all())

    async def is_user_moderator(self, user_id: int) -> bool:
        """Check moderator role."""
        async with self.session_maker() as session:
            user = await session.get(User, user_id)
            return bool(user and user.is_moderator)

    async def get_bot_stats(self) -> Optional[BotStats]:
        """Get latest bot stats row."""
        async with self.session_maker() as session:
            rows = await session.execute(select(BotStats).order_by(BotStats.id.desc()).limit(1))
            return rows.scalar_one_or_none()

    async def update_bot_stats(self) -> BotStats:
        """Refresh aggregate stats for dashboard."""
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
                )
                session.add(stats)

            await session.commit()
            await session.refresh(stats)
            return stats

    async def create_ticket(
        self,
        user_id: int,
        message: str,
        user_username: Optional[str] = None,
        user_first_name: Optional[str] = None,
    ) -> Ticket:
        """Create support ticket."""
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
            return ticket

    async def add_ticket_message(
        self,
        ticket_id: int,
        sender_type: str,
        sender_id: int,
        message: str,
    ) -> TicketMessage:
        """Append message to ticket thread."""
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
            return row


db = Database()
