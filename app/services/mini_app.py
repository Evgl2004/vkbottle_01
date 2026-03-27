"""Сервис для работы с VK Mini App: генерация ссылок, проверка телефона, управление состоянием."""

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from loguru import logger

from app.config import settings
from app.database import db
from app.services.vk_signature import verify_mini_app_request


def generate_mini_app_link(user_id: int, state_token: Optional[str] = None) -> str:
    """Генерирует ссылку для открытия Mini App с параметрами запуска.

    Параметры запуска включают:
    - `vk_user_id` – идентификатор пользователя VK (обязательный)
    - `state_token` – одноразовый токен для связывания сессии (опционально)
    - `sign` – подпись параметров (добавляется на стороне Mini App, не здесь)

    Args:
        user_id: ID пользователя VK.
        state_token: Токен состояния, если уже сгенерирован.

    Returns:
        Ссылка вида `https://vk.com/app{app_id}?vk_user_id={user_id}&state_token={token}`
    """
    app_id = settings.vk_mini_app_id
    if not app_id:
        logger.error("ID Mini App не задан в конфигурации")
        return ""

    base_url = settings.vk_mini_app_url.rstrip("/")
    if base_url == "https://vk.com/app":
        # Стандартный шаблон
        link = f"{base_url}{app_id}"
    else:
        link = base_url

    params = {"vk_user_id": user_id}
    if state_token:
        params["state_token"] = state_token

    # Параметры будут подписаны на стороне Mini App, здесь мы просто формируем query string.
    from urllib.parse import urlencode

    query = urlencode(params)
    return f"{link}?{query}"


async def create_state_token(user_id: int, ttl_seconds: int = 300) -> str:
    """Создаёт одноразовый токен состояния и сохраняет его в Redis.

    Токен используется для связывания запроса от Mini App с пользователем и его FSM-состоянием.
    После использования токен должен быть удалён.

    Args:
        user_id: ID пользователя VK.
        ttl_seconds: Время жизни токена в секундах (по умолчанию 5 минут).

    Returns:
        Сгенерированный токен (UUID строкой).
    """
    from app.services.state_dispenser import get_redis_client

    token = str(uuid.uuid4())
    redis_key = f"mini_app:state_token:{token}"
    redis_client = await get_redis_client()

    # Сохраняем user_id и timestamp
    import json

    data = {
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.setex(redis_key, ttl_seconds, json.dumps(data))
    logger.debug("Создан state_token для Mini App (user_id={}, token={})", user_id, token)
    return token


async def validate_state_token(token: str) -> Optional[int]:
    """Проверяет токен состояния и возвращает привязанный user_id.

    Если токен валиден, он удаляется из Redis (одноразовое использование).

    Args:
        token: Токен состояния.

    Returns:
        ID пользователя VK или None, если токен недействителен.
    """
    from app.services.state_dispenser import get_redis_client

    redis_key = f"mini_app:state_token:{token}"
    redis_client = await get_redis_client()

    data_json = await redis_client.get(redis_key)
    if not data_json:
        logger.warning("Попытка использовать несуществующий или истёкший state_token: {}", token)
        return None

    import json

    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        logger.error("Некорректный JSON в state_token: {}", data_json)
        # Удаляем битый ключ
        await redis_client.delete(redis_key)
        return None

    user_id = data.get("user_id")
    if not user_id:
        logger.error("Некорректные данные в state_token: {}", data)
        # Удаляем ключ с некорректными данными
        await redis_client.delete(redis_key)
        return None

    # Удаляем токен после использования
    await redis_client.delete(redis_key)
    logger.debug("State_token использован и удалён (user_id={}, token={})", user_id, token)
    return user_id


async def notify_bot_phone_verified(user_id: int, ttl_seconds: int = 60) -> None:
    """Устанавливает флаг в Redis, что телефон подтверждён, для уведомления бота."""
    from app.services.state_dispenser import get_redis_client
    redis_client = await get_redis_client()
    key = f"phone_verified:{user_id}"
    await redis_client.setex(key, ttl_seconds, "1")
    logger.debug("Установлен флаг подтверждения телефона (user_id={})", user_id)


async def verify_phone_from_mini_app(
    phone: str,
    vk_user_id: int,
    signature_params: dict,
) -> Tuple[bool, str]:
    """Проверяет телефон, полученный от Mini App, и сохраняет его в профиль пользователя.

    Выполняет:
    1. Проверку подписи запроса.
    2. Валидацию формата телефона.
    3. Проверку, что телефон ещё не подтверждён.
    4. Сохранение телефона в БД с отметкой о подтверждении.
    5. Уведомление бота о подтверждении.

    Args:
        phone: Номер телефона, полученный от VK.
        vk_user_id: ID пользователя VK (должен совпадать с подписанным).
        signature_params: Все параметры запроса (включая sign) для проверки подписи.

    Returns:
        Кортеж (успех, сообщение об ошибке или успехе).
    """
    # 1. Проверка подписи
    if not verify_mini_app_request(signature_params):
        return False, "Невалидная подпись запроса"

    # 2. Проверка, что vk_user_id совпадает с подписанным
    if str(signature_params.get("vk_user_id")) != str(vk_user_id):
        return False, "Несоответствие идентификатора пользователя"

    # 3. Валидация телефона (базовая)
    from app.utils.validation import validate_phone, normalize_phone

    valid, error = await validate_phone(phone)
    if not valid:
        return False, error

    normalized = await normalize_phone(phone)

    # 4. Проверка, что телефон ещё не подтверждён у этого пользователя
    user = await db.get_user(vk_user_id)
    if user and user.phone_verified_at is not None:
        logger.info(
            "Пользователь уже подтвердил телефон ранее (user_id={}, phone={})",
            vk_user_id,
            user.phone_number,
        )
        # Возвращаем успех, но не обновляем данные
        return True, "Телефон уже был подтверждён ранее"

    # 5. Сохранение в БД
    try:
        await db.update_user(
            vk_user_id,
            phone_number=normalized,
            phone_verified_at=datetime.now(timezone.utc),
            phone_verification_method="vk_mini_app",
        )
        logger.info(
            "Телефон подтверждён через Mini App (user_id={}, phone={})",
            vk_user_id,
            normalized,
        )
        # 6. Уведомление бота
        await notify_bot_phone_verified(vk_user_id)
        return True, "Телефон успешно подтверждён"
    except Exception as e:
        logger.exception("Ошибка сохранения телефона из Mini App: {}", e)
        return False, "Внутренняя ошибка сервера"