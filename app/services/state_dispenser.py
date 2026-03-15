"""Redis-реализация хранилища состояний `vkbottle`.

По умолчанию `vkbottle` использует in-memory dispenser, который
не подходит для production/перезапуска процесса.

Этот модуль предоставляет адаптер, который хранит состояния в Redis:
1. состояние пользователя сохраняется между рестартами бота;
2. можно масштабировать обработчики горизонтально;
3. есть TTL для автоматической очистки «забытых» сессий.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from redis.asyncio import Redis
from vkbottle import ABCStateDispenser, BaseStateGroup, StatePeer


class RedisStateDispenser(ABCStateDispenser):
    """Хранилище FSM-состояний на базе Redis."""

    def __init__(
        self,
        redis: Redis,
        key_prefix: str = "vkbot:state",
        ttl_seconds: Optional[int] = 60 * 60 * 24 * 7,
    ) -> None:
        """Создает экземпляр диспансера.

        Параметры:
        - `redis`: готовый асинхронный клиент Redis;
        - `key_prefix`: префикс ключей, чтобы отделить данные проекта;
        - `ttl_seconds`: TTL состояний (по умолчанию 7 дней).
        """

        self.redis = redis
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds

    @classmethod
    def from_url(
        cls,
        url: str,
        key_prefix: str = "vkbot:state",
        ttl_seconds: Optional[int] = 60 * 60 * 24 * 7,
    ) -> "RedisStateDispenser":
        """Фабричный метод создания по Redis URL."""
        redis = Redis.from_url(url, decode_responses=True)
        return cls(redis=redis, key_prefix=key_prefix, ttl_seconds=ttl_seconds)

    def _key(self, peer_id: int) -> str:
        """Формирует ключ Redis для конкретного пользователя."""
        return f"{self.key_prefix}:{peer_id}"

    async def get(self, peer_id: int) -> Optional[StatePeer]:
        """Возвращает состояние пользователя из Redis."""

        raw = await self.redis.get(self._key(peer_id))
        if not raw:
            return None

        data = json.loads(raw)
        return StatePeer(
            peer_id=peer_id,
            state=data.get("state"),
            payload=data.get("payload", {}),
        )

    async def set(self, peer_id: int, state: BaseStateGroup, **payload: Any):
        """Сохраняет состояние и payload пользователя в Redis."""

        packed = json.dumps(
            {
                "state": str(state),
                "payload": payload,
            },
            ensure_ascii=False,
        )
        key = self._key(peer_id)
        if self.ttl_seconds is None:
            await self.redis.set(key, packed)
        else:
            await self.redis.set(key, packed, ex=self.ttl_seconds)

    async def delete(self, peer_id: int):
        """Удаляет состояние пользователя."""
        await self.redis.delete(self._key(peer_id))

    async def close(self) -> None:
        """Закрывает Redis-клиент диспансера."""
        await self.redis.aclose()
