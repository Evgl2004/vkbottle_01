"""Сервис проверки подписи VK для запросов от Mini App.

Согласно документации VK, параметры запроса от Mini App подписываются
секретным ключом приложения. Алгоритм:
1. Все параметры, кроме `sign`, сортируются по алфавиту.
2. Формируется строка вида `key1=value1key2=value2...`.
3. К строке применяется HMAC-SHA-256 с секретным ключом.
4. Полученный хеш сравнивается с параметром `sign` (в hex).

Подробнее: https://dev.vk.com/mini-apps/development/launch-params#Проверка-подлинности-параметров-запуска
"""

import hashlib
import hmac
from typing import Any, Dict
from urllib.parse import unquote

from loguru import logger

from app.config import settings


def verify_vk_signature(params: Dict[str, Any], secret_key: str) -> bool:
    """Проверяет подпись VK для параметров запуска Mini App.

    Args:
        params: Словарь параметров, включая `sign`.
        secret_key: Секретный ключ мини-приложения.

    Returns:
        True, если подпись корректна, иначе False.
    """
    if "sign" not in params:
        logger.warning("Отсутствует параметр sign в запросе от Mini App")
        return False

    sign = params.pop("sign")
    # Декодируем URL-encoded значения (VK передаёт параметры в URL)
    decoded_params = {k: unquote(v) if isinstance(v, str) else v for k, v in params.items()}

    # Сортируем ключи по алфавиту
    sorted_keys = sorted(decoded_params.keys())
    # Формируем строку для подписи
    string_to_sign = "".join(f"{key}={decoded_params[key]}" for key in sorted_keys)

    # Вычисляем HMAC-SHA-256
    expected_sign = hmac.new(
        secret_key.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Сравниваем с переданной подписью (без учёта регистра)
    is_valid = hmac.compare_digest(expected_sign.lower(), sign.lower())
    if not is_valid:
        logger.warning(
            "Невалидная подпись VK: expected={}, received={}",
            expected_sign,
            sign,
        )
    return is_valid


def verify_mini_app_request(params: Dict[str, Any]) -> bool:
    """Проверяет подпись запроса от Mini App с использованием настроек приложения.

    Использует секретный ключ из конфигурации (`settings.vk_mini_app_secret`).
    Если ключ не задан, возвращает False (в production это недопустимо).

    Returns:
        True, если подпись корректна и ключ задан.
    """
    secret = settings.vk_mini_app_secret
    if not secret:
        logger.error("Секретный ключ Mini App не задан в конфигурации")
        return False

    return verify_vk_signature(params, secret)