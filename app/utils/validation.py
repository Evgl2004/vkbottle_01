"""Общие функции валидации пользовательского ввода.

Цель модуля:
1. Сконцентрировать все проверки в одном месте.
2. Сделать поведение единообразным между регистрацией и legacy-апгрейдом.
3. Вернуть удобный контракт `(успех, сообщение_об_ошибке)`.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Tuple

from vkbottle.bot import Message


PHONE_PATTERN = re.compile(r"^\+?\d{10,15}$")
NAME_PATTERN = re.compile(r"^[a-zA-Zа-яА-ЯёЁ\s-]+$")
EMAIL_PATTERN = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
BIRTH_DATE_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


async def confirm_text(
    message: Message,
    error_text: str = "✍️ Пожалуйста, отправьте текстовое сообщение.",
) -> bool:
    """Проверяет, что входящее сообщение содержит текст.

    Почему это важно:
    - часть шагов FSM принимает только текст (например, email, дата рождения);
    - вложения и стикеры не подходят для этих этапов.
    """

    text = (message.text or "").strip()
    if not text:
        await message.answer(error_text)
        return False
    return True


async def validate_phone(value: str) -> Tuple[bool, str]:
    """Проверяет и нормализует телефон.

    Формат:
    - допускаются только цифры и опциональный знак `+` в начале;
    - итоговая длина: 10..15 символов.
    """

    if not value:
        return False, "📱 Номер телефона не может быть пустым. Введите номер в формате +79991234567."

    prepared = value.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not PHONE_PATTERN.fullmatch(prepared):
        return False, "⚠️ Некорректный номер. Пример: +79991234567"

    return True, ""


async def normalize_phone(value: str) -> str:
    """Приводит телефон к единому виду.

    Правила:
    - удаляются пробелы и служебные символы;
    - если номер начинается с `8` и содержит 11 цифр, заменяем на `+7`.
    - если отсутствует `+`, добавляем его.
    """

    prepared = value.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if prepared.startswith("8") and len(prepared) == 11:
        prepared = "+7" + prepared[1:]
    elif not prepared.startswith("+"):
        prepared = "+" + prepared
    return prepared


async def validate_first_name(value: str) -> Tuple[bool, str]:
    """Проверяет корректность имени."""
    if not value:
        return False, "👤 Имя не может быть пустым. Введите имя."
    if not NAME_PATTERN.fullmatch(value):
        return False, "⚠️ Имя может содержать только буквы, пробелы и дефисы."
    return True, ""


async def validate_last_name(value: str) -> Tuple[bool, str]:
    """Проверяет корректность фамилии."""
    if not value:
        return False, "👥 Фамилия не может быть пустой. Введите фамилию."
    if not NAME_PATTERN.fullmatch(value):
        return False, "⚠️ Фамилия может содержать только буквы, пробелы и дефисы."
    return True, ""


async def clean_name(value: str) -> str:
    """Удаляет лишние пробелы в имени/фамилии."""
    return re.sub(r"\s+", " ", value).strip()


async def validate_birth_date(value: str) -> Tuple[bool, str]:
    """Проверяет дату рождения и возрастные ограничения.

    Формат ввода:
    - `ДД.ММ.ГГГГ`

    Ограничения:
    - дата не может быть в будущем;
    - возраст должен быть от 18 до 100 лет включительно.
    """

    if not BIRTH_DATE_PATTERN.fullmatch(value):
        return False, "⚠️ Неверный формат. Используйте ДД.ММ.ГГГГ."

    try:
        birth = datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError:
        return False, "⚠️ Дата некорректна. Проверьте день, месяц и год."

    today = date.today()
    if birth > today:
        return False, "⚠️ Дата рождения не может быть в будущем."

    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    if age < 18:
        return False, "🔞 Регистрация доступна только для пользователей старше 18 лет."
    if age > 100:
        return False, "⚠️ Проверьте дату рождения: указан слишком большой возраст."

    return True, ""


async def validate_email(value: str) -> Tuple[bool, str]:
    """Проверяет базовую корректность email."""
    if not value:
        return False, "📧 Email не может быть пустым. Введите email."
    if not EMAIL_PATTERN.match(value):
        return False, "⚠️ Некорректный email. Пример: name@example.com"
    return True, ""
