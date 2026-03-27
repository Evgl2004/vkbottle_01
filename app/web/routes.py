"""Маршруты веб-сервера для обработки запросов от VK Mini App."""

import json
from typing import Any, Dict

from aiohttp import web
from loguru import logger

from app.services.mini_app import verify_phone_from_mini_app, validate_state_token
from app.utils.validation import normalize_phone


async def health_check(request: web.Request) -> web.Response:
    """Эндпоинт для проверки работоспособности сервера."""
    return web.json_response({"status": "ok"})


async def phone_verify(request: web.Request) -> web.Response:
    """Принимает запрос от Mini App с подтверждённым телефоном.

    Ожидаемый JSON:
    {
        "phone": "+79991234567",
        "vk_user_id": 123456789,
        "state_token": "uuid-optional",
        "signature": { ... }  # все параметры запуска Mini App (включая sign)
    }

    Подпись проверяется внутри `verify_phone_from_mini_app`.
    """
    try:
        data = await request.json()
    except json.JSONDecodeError:
        logger.warning("Невалидный JSON в запросе /api/v1/phone/verify")
        return web.json_response(
            {"success": False, "error": "Invalid JSON"},
            status=400,
        )

    phone = data.get("phone")
    vk_user_id = data.get("vk_user_id")
    state_token = data.get("state_token")
    signature_params = data.get("signature", {})

    if not phone or not vk_user_id:
        logger.warning("Отсутствуют обязательные поля phone или vk_user_id")
        return web.json_response(
            {"success": False, "error": "Missing required fields"},
            status=400,
        )

    # Если передан state_token, проверяем его и извлекаем user_id
    if state_token:
        token_user_id = await validate_state_token(state_token)
        if token_user_id is None:
            return web.json_response(
                {"success": False, "error": "Invalid or expired state token"},
                status=400,
            )
        if token_user_id != vk_user_id:
            logger.warning(
                "Несоответствие user_id в state_token: token_user_id={}, vk_user_id={}",
                token_user_id,
                vk_user_id,
            )
            return web.json_response(
                {"success": False, "error": "User mismatch"},
                status=400,
            )

    # Проверяем подпись и сохраняем телефон
    success, message = await verify_phone_from_mini_app(
        phone=phone,
        vk_user_id=vk_user_id,
        signature_params=signature_params,
    )

    if success:
        logger.info(
            "Телефон успешно подтверждён через Mini App (user_id={})",
            vk_user_id,
        )
        return web.json_response(
            {"success": True, "message": message},
            status=200,
        )
    else:
        logger.warning(
            "Ошибка подтверждения телефона через Mini App (user_id={}): {}",
            vk_user_id,
            message,
        )
        return web.json_response(
            {"success": False, "error": message},
            status=400,
        )


def setup_routes(app: web.Application) -> None:
    """Регистрирует все маршруты веб-сервера."""
    app.router.add_get("/health", health_check)
    app.router.add_post("/api/v1/phone/verify", phone_verify)