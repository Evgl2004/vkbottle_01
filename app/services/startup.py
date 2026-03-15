"""Startup bootstrap checks."""

from __future__ import annotations

from loguru import logger
from redis.asyncio import Redis

from app.config import settings
from app.database import db


async def _check_redis() -> None:
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
        logger.info("redis connection ok")
    finally:
        await client.aclose()


async def bootstrap() -> None:
    """Prepare infrastructure before polling loop starts."""
    await db.create_tables()
    await db.update_bot_stats()
    await _check_redis()
