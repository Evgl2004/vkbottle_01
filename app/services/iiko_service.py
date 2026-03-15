"""Сервис-обертка над `AsyncIikoApi`.

Модуль обеспечивает:
1. инициализацию/закрытие клиента при старте и остановке приложения;
2. доменные функции для регистрации клиента и выпуска карты;
3. подробные диагностические логи для боевого трейсинга.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.config import settings
from app.services.iiko_async import AsyncIikoApi

_iiko_client: Optional[AsyncIikoApi] = None


def _mask_phone(phone: str) -> str:
    """Маскирует телефон для безопасного вывода в логах."""

    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


async def init_iiko_client() -> None:
    """Создаёт глобальный экземпляр iiko-клиента."""

    global _iiko_client
    if not settings.iiko_api_key or not settings.iiko_org_id:
        logger.warning(
            "iiko не настроен: отсутствуют IIKO_API_KEY или IIKO_ORG_ID. "
            "Синхронизация пользователей с iiko будет недоступна."
        )
        _iiko_client = None
        return

    _iiko_client = AsyncIikoApi(
        api_key=settings.iiko_api_key,
        organization_id=settings.iiko_org_id,
        base_url=settings.iiko_base_url,
    )
    logger.info("iiko-клиент инициализирован")


async def close_iiko_client() -> None:
    """Корректно закрывает iiko-клиент при завершении процесса."""

    global _iiko_client
    if _iiko_client:
        await _iiko_client.close()
    _iiko_client = None


def _client() -> AsyncIikoApi:
    """Возвращает активный iiko-клиент или выбрасывает понятную ошибку."""

    if _iiko_client is None:
        raise RuntimeError("Клиент iiko не инициализирован. Проверьте настройки IIKO_*.")
    return _iiko_client


async def get_customer_info(phone: str) -> Optional[Dict[str, Any]]:
    """Возвращает информацию о клиенте iiko по телефону."""

    try:
        logger.debug("Запрос клиента iiko по телефону {}", _mask_phone(phone))
        info = await _client().get_customer_info(phone)
        logger.debug(
            "Ответ iiko customer_info: found={} phone={}",
            bool(info),
            _mask_phone(phone),
        )
        return info
    except Exception as error:
        logger.error("Ошибка get_customer_info (phone={}): {}", _mask_phone(phone), error)
        return None


async def register_customer(user, customer_id: Optional[str] = None) -> Tuple[Optional[str], str]:
    """Создаёт или обновляет клиента iiko на основе анкеты пользователя."""

    try:
        sex_map = {"male": 1, "female": 2}
        sex = sex_map.get(user.gender) if user.gender else None
        birth_date_str = user.birth_date.strftime("%Y-%m-%d 00:00:00.000") if user.birth_date else None
        consent_status = 1 if user.rules_accepted else 0

        logger.debug(
            "register_customer: phone={}, customer_id={}, has_email={}, has_birth_date={}",
            _mask_phone(user.phone_number or ""),
            customer_id or "<new>",
            bool(user.email),
            bool(birth_date_str),
        )

        result = await _client().register_customer(
            phone=user.phone_number or "",
            name=user.first_name_input or "",
            surname=user.last_name_input or "",
            birth_date=birth_date_str,
            sex=sex,
            email=user.email or "",
            consent_status=consent_status,
            should_receive_promo=user.notifications_allowed,
            should_receive_loyalty=user.notifications_allowed,
            customer_id=customer_id,
        )

        logger.debug(
            "register_customer result: ok={}, customer_id={}",
            bool(result[0]),
            result[0] or "<none>",
        )
        return result
    except Exception as error:
        msg = f"Ошибка register_customer: {error}"
        logger.error(msg)
        return None, msg


async def add_card(customer_id: str, card_number: str) -> Tuple[bool, str]:
    """Добавляет карту клиенту iiko."""

    try:
        logger.debug(
            "add_card: customer_id={}, card_number={}",
            customer_id,
            card_number,
        )
        result = await _client().add_card(customer_id, card_number)
        logger.debug("add_card result: ok={}, message={}", result[0], result[1])
        return result
    except Exception as error:
        msg = f"Ошибка add_card: {error}"
        logger.error(msg)
        return False, msg


async def get_loyalty_programs() -> List[Dict[str, Any]]:
    """Возвращает список программ лояльности."""

    try:
        programs = await _client().get_loyalty_programs()
        logger.debug("Получены программы лояльности: count={}", len(programs))
        return programs
    except Exception as error:
        logger.error("Ошибка get_loyalty_programs: {}", error)
        return []


async def add_customer_to_program(customer_id: str, program_id: Optional[str] = None) -> Tuple[bool, str]:
    """Подключает клиента к программе лояльности."""

    try:
        logger.debug(
            "add_customer_to_program: customer_id={}, program_id={}",
            customer_id,
            program_id or "<auto>",
        )
        result = await _client().add_customer_to_program(customer_id, program_id)
        logger.debug(
            "add_customer_to_program result: ok={}, message={}",
            result[0],
            result[1],
        )
        return result
    except Exception as error:
        msg = f"Ошибка add_customer_to_program: {error}"
        logger.error(msg)
        return False, msg


async def issue_card_for_customer(phone: str, customer_id: str) -> Tuple[bool, str, Optional[str]]:
    """Выполняет полный сценарий выпуска карты и подключения программы.

    Возвращает:
    - `успех`;
    - `сообщение`;
    - `номер_карты` (если создана).
    """

    digits = "".join(char for char in phone if char.isdigit())
    card_number = f"{digits}_{datetime.now().strftime('%Y%m%d')}"

    logger.debug(
        "issue_card_for_customer start: customer_id={}, phone={}, card_number={}",
        customer_id,
        _mask_phone(phone),
        card_number,
    )

    ok, message = await add_card(customer_id, card_number)
    if not ok:
        logger.error(
            "issue_card_for_customer: add_card failed (customer_id={}): {}",
            customer_id,
            message,
        )
        return False, message, None

    prog_ok, prog_message = await add_customer_to_program(customer_id)
    if not prog_ok:
        logger.warning(
            "Карта выпущена, но программа лояльности не подключена (customer_id={}): {}",
            customer_id,
            prog_message,
        )
        return (
            True,
            f"Карта выпущена, но программа лояльности не подключена: {prog_message}",
            card_number,
        )

    logger.info(
        "Карта успешно выпущена и подключена к программе лояльности (customer_id={}, card_number={})",
        customer_id,
        card_number,
    )
    return True, "Карта успешно выпущена и подключена к программе лояльности.", card_number
