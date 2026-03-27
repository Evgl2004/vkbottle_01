"""Запуск aiohttp веб-сервера для обработки запросов от Mini App."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from aiohttp import web
from loguru import logger

from app.config import settings
from app.web.routes import setup_routes


@asynccontextmanager
async def lifespan(app: web.Application) -> AsyncIterator[None]:
    """Контекстный менеджер жизненного цикла веб-приложения."""
    logger.info("Веб-сервер Mini App запускается на порту {}", settings.web_port)
    yield
    logger.info("Веб-сервер Mini App останавливается")


def create_app() -> web.Application:
    """Создаёт и настраивает экземпляр aiohttp Application."""
    app = web.Application()
    app.cleanup_ctx.append(lifespan)
    setup_routes(app)
    return app


async def start_web_server() -> None:
    """Запускает веб-сервер в фоновом режиме."""
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.web_host, port=settings.web_port)
    await site.start()
    logger.info(
        "Веб-сервер Mini App запущен на http://{}:{}",
        settings.web_host,
        settings.web_port,
    )
    # Бесконечно ждём, пока сервер не будет остановлен извне
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("Получен сигнал остановки веб-сервера")
    finally:
        await runner.cleanup()


def run_web_server_in_background(loop: asyncio.AbstractEventLoop) -> asyncio.Task:
    """Запускает веб-сервер как фоновую задачу в указанном event loop."""
    return loop.create_task(start_web_server())