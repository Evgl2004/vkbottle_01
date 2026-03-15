"""Сервис синхронизации пользователя с iiko после регистрации."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.database import db
from app.services import iiko_service


@dataclass(slots=True)
class SyncResult:
    """Результат синхронизации пользователя с iiko."""

    success: bool
    message: str
    card_numbers: List[str]


async def sync_user_with_iiko(user) -> SyncResult:
    """Выполняет полный сценарий синхронизации пользователя с iiko.

    Алгоритм:
    1. Проверка телефона.
    2. Поиск клиента в iiko.
    3. Создание или обновление клиента.
    4. Выпуск карты при отсутствии карт.
    5. Установка `is_registered=True` в БД.
    """

    phone = user.phone_number
    if not phone:
        return SyncResult(False, "Не найден номер телефона пользователя.", [])

    # 1. Пытаемся получить данные клиента.
    client_info = await iiko_service.get_customer_info(phone)

    # 2. Если клиента нет — создаём.
    if client_info is None:
        customer_id, msg = await iiko_service.register_customer(user)
        if not customer_id:
            return SyncResult(False, f"Не удалось зарегистрировать клиента в iiko: {msg}", [])
        client_info = {"customer_id": customer_id, "cards": []}
    else:
        customer_id = client_info.get("customer_id")
        if not customer_id:
            customer_id, msg = await iiko_service.register_customer(user)
            if not customer_id:
                return SyncResult(False, f"Не удалось обновить данные клиента в iiko: {msg}", [])
            client_info["customer_id"] = customer_id
        else:
            updated_id, msg = await iiko_service.register_customer(user, customer_id=customer_id)
            if not updated_id:
                return SyncResult(False, f"Не удалось обновить профиль в iiko: {msg}", [])
            client_info["customer_id"] = updated_id

    # 3. Проверяем карты.
    cards = client_info.get("cards", []) or []
    if not cards:
        ok, msg, card_number = await iiko_service.issue_card_for_customer(
            phone=phone,
            customer_id=client_info["customer_id"],
        )
        if not ok:
            return SyncResult(False, f"Не удалось выпустить карту: {msg}", [])

        # Перезапрашиваем карточки после выпуска.
        refreshed = await iiko_service.get_customer_info(phone)
        if refreshed and refreshed.get("cards"):
            cards = refreshed["cards"]
        elif card_number:
            cards = [{"number": card_number}]
        else:
            cards = []

    # 4. Завершаем регистрацию локально.
    await db.update_user(user.id, is_registered=True)
    card_numbers = [item.get("number", "") for item in cards if item.get("number")]

    return SyncResult(
        True,
        "Синхронизация с iiko выполнена успешно.",
        card_numbers,
    )
