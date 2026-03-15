"""Хендлеры сценария обновления данных legacy-пользователей."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from vkbottle.bot import Bot, Message

from app.database import db
from app.handlers.menu import show_main_menu
from app.keyboards.registration import (
    get_edit_choice_keyboard,
    get_gender_keyboard,
    get_notifications_keyboard,
    get_retry_iiko_keyboard,
    get_review_keyboard,
    get_rules_keyboard,
)
from app.keyboards.payloads import (
    CMD_ACCEPT_RULES,
    CMD_EDIT_BIRTH_DATE,
    CMD_EDIT_CANCEL,
    CMD_EDIT_EMAIL,
    CMD_EDIT_FIRST_NAME,
    CMD_EDIT_GENDER,
    CMD_EDIT_LAST_NAME,
    CMD_GENDER_FEMALE,
    CMD_GENDER_MALE,
    CMD_NOTIFY_NO,
    CMD_NOTIFY_YES,
    CMD_RETRY_IIKO,
    CMD_REVIEW_EDIT,
    CMD_REVIEW_OK,
)
from app.services.user_sync import sync_user_with_iiko
from app.states.legacy import LegacyState
from app.utils.profile import get_profile_review_text
from app.utils.validation import (
    clean_name,
    confirm_text,
    validate_birth_date,
    validate_email,
    validate_first_name,
    validate_last_name,
)


async def _get_missing_fields(user) -> List[str]:
    """Вычисляет список обязательных полей, требующих актуализации."""

    missing: List[str] = []
    if not user.first_name_input:
        missing.append("first_name")
    if not user.last_name_input:
        missing.append("last_name")
    if user.gender not in ("male", "female"):
        missing.append("gender")
    if not user.birth_date:
        missing.append("birth_date")
    if not user.email:
        missing.append("email")
    return missing


async def _ask_next_field(message: Message, bot: Bot, missing_fields: List[str]) -> None:
    """Запрашивает следующий недостающий атрибут анкеты legacy-пользователя."""

    user_id = int(message.from_id)
    if not missing_fields:
        await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_REVIEW)
        await message.answer(await get_profile_review_text(user_id), keyboard=get_review_keyboard())
        return

    current = missing_fields[0]
    await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_FIELD, missing_fields=missing_fields)

    if current == "first_name":
        await message.answer("Введите ваше имя.")
    elif current == "last_name":
        await message.answer("Введите вашу фамилию.")
    elif current == "gender":
        await message.answer("Выберите ваш пол.", keyboard=get_gender_keyboard())
    elif current == "birth_date":
        await message.answer("Введите дату рождения в формате ДД.ММ.ГГГГ.")
    elif current == "email":
        await message.answer("Введите email.")
    else:
        missing_fields.pop(0)
        await _ask_next_field(message, bot, missing_fields)


async def _run_iiko_sync(message: Message, bot: Bot) -> None:
    """Выполняет синхронизацию legacy-пользователя с iiko."""

    user_id = int(message.from_id)
    user = await db.get_user(user_id)
    if not user:
        await bot.state_dispenser.delete(user_id)
        await message.answer("Не удалось загрузить профиль. Введите /start.")
        return

    result = await sync_user_with_iiko(user)
    if not result.success:
        await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_IIKO_REGISTRATION)
        await message.answer(
            f"Ошибка синхронизации с iiko:\n{result.message}",
            keyboard=get_retry_iiko_keyboard(),
        )
        return

    await bot.state_dispenser.delete(user_id)
    updated = await db.get_user(user_id)
    await message.answer("Данные успешно обновлены.")
    await show_main_menu(message, user_name=(updated.first_name_input if updated else None) or "Гость")


async def start_legacy_upgrade(message: Message, bot: Bot, user) -> None:
    """Запускает legacy-сценарий по кнопке/команде `/start`."""

    await message.answer(
        "Мы обновили бота и должны актуализировать ваши данные.\n"
        "Это займёт несколько шагов."
    )
    await message.answer(
        "Пожалуйста, подтвердите согласие с правилами и обработкой персональных данных.",
        keyboard=get_rules_keyboard(),
    )
    await bot.state_dispenser.set(int(message.from_id), LegacyState.WAITING_FOR_RULES_CONSENT)


def register_legacy_handlers(bot: Bot) -> None:
    """Регистрирует обработчики legacy-потока."""

    @bot.on.private_message(
        payload_contains={"cmd": CMD_ACCEPT_RULES},
        state=LegacyState.WAITING_FOR_RULES_CONSENT,
    )
    async def legacy_accept_rules(message: Message) -> None:
        """Сохраняет согласие и запускает добор недостающих полей."""

        user_id = int(message.from_id)
        await db.update_user(
            user_id,
            rules_accepted=True,
            rules_accepted_at=datetime.now(timezone.utc),
        )

        user = await db.get_user(user_id)
        missing = await _get_missing_fields(user)
        await _ask_next_field(message, bot, missing)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_GENDER_MALE},
        state=LegacyState.WAITING_FOR_FIELD,
    )
    @bot.on.private_message(
        payload_contains={"cmd": CMD_GENDER_FEMALE},
        state=LegacyState.WAITING_FOR_FIELD,
    )
    async def legacy_field_gender(message: Message) -> None:
        """Обрабатывает выбор пола в шаге добора недостающих полей."""

        user_id = int(message.from_id)
        state_peer = message.state_peer
        missing = list(state_peer.payload.get("missing_fields", [])) if state_peer else []
        if not missing or missing[0] != "gender":
            await message.answer("Ожидается ввод другого поля. Продолжаем актуализацию.")
            await _ask_next_field(message, bot, missing)
            return

        cmd = message.get_payload_json().get("cmd")
        await db.update_user(user_id, gender="male" if cmd == CMD_GENDER_MALE else "female")
        missing.pop(0)
        await _ask_next_field(message, bot, missing)

    @bot.on.private_message(state=LegacyState.WAITING_FOR_FIELD)
    async def legacy_field_text(message: Message) -> None:
        """Обрабатывает текстовый ввод недостающих полей legacy-анкеты."""

        if not await confirm_text(message, "Введите значение текстом."):
            return

        user_id = int(message.from_id)
        state_peer = message.state_peer
        missing = list(state_peer.payload.get("missing_fields", [])) if state_peer else []
        if not missing:
            await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_REVIEW)
            await message.answer(await get_profile_review_text(user_id), keyboard=get_review_keyboard())
            return

        current = missing[0]
        text = message.text.strip()

        if current == "first_name":
            valid, error = await validate_first_name(text)
            if not valid:
                await message.answer(error)
                return
            await db.update_user(user_id, first_name_input=await clean_name(text))
        elif current == "last_name":
            valid, error = await validate_last_name(text)
            if not valid:
                await message.answer(error)
                return
            await db.update_user(user_id, last_name_input=await clean_name(text))
        elif current == "birth_date":
            valid, error = await validate_birth_date(text)
            if not valid:
                await message.answer(error)
                return
            await db.update_user(user_id, birth_date=datetime.strptime(text, "%d.%m.%Y").date())
        elif current == "email":
            valid, error = await validate_email(text)
            if not valid:
                await message.answer(error)
                return
            await db.update_user(user_id, email=text)
        else:
            await message.answer("Неизвестное поле актуализации, пропускаем.")

        missing.pop(0)
        await _ask_next_field(message, bot, missing)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_REVIEW_OK},
        state=LegacyState.WAITING_FOR_REVIEW,
    )
    async def legacy_review_ok(message: Message) -> None:
        """Подтверждение анкеты legacy-пользователем."""
        await bot.state_dispenser.set(
            int(message.from_id),
            LegacyState.WAITING_FOR_NOTIFICATIONS_CONSENT,
        )
        await message.answer(
            "Выберите вариант согласия на уведомления:",
            keyboard=get_notifications_keyboard(),
        )

    @bot.on.private_message(
        payload_contains={"cmd": CMD_REVIEW_EDIT},
        state=LegacyState.WAITING_FOR_REVIEW,
    )
    async def legacy_review_edit(message: Message) -> None:
        """Открывает выбор поля для редактирования в legacy-потоке."""
        await bot.state_dispenser.set(int(message.from_id), LegacyState.WAITING_FOR_EDIT_CHOICE)
        await message.answer("Выберите поле для редактирования:", keyboard=get_edit_choice_keyboard())

    @bot.on.private_message(state=LegacyState.WAITING_FOR_EDIT_CHOICE)
    async def legacy_edit_choice(message: Message) -> None:
        """Обрабатывает выбор поля для редактирования."""

        payload = message.get_payload_json()
        command = payload.get("cmd") if isinstance(payload, dict) else None

        if command == CMD_EDIT_CANCEL:
            await bot.state_dispenser.set(int(message.from_id), LegacyState.WAITING_FOR_REVIEW)
            await message.answer(await get_profile_review_text(int(message.from_id)), keyboard=get_review_keyboard())
            return

        if command not in {
            CMD_EDIT_FIRST_NAME,
            CMD_EDIT_LAST_NAME,
            CMD_EDIT_GENDER,
            CMD_EDIT_BIRTH_DATE,
            CMD_EDIT_EMAIL,
        }:
            await message.answer("Не удалось определить поле редактирования.")
            return

        await bot.state_dispenser.set(
            int(message.from_id),
            LegacyState.WAITING_FOR_EDIT_FIELD,
            edit_field=command,
        )

        if command == CMD_EDIT_GENDER:
            await message.answer("Выберите новый пол.", keyboard=get_gender_keyboard())
        elif command == CMD_EDIT_FIRST_NAME:
            await message.answer("Введите новое имя.")
        elif command == CMD_EDIT_LAST_NAME:
            await message.answer("Введите новую фамилию.")
        elif command == CMD_EDIT_BIRTH_DATE:
            await message.answer("Введите новую дату рождения в формате ДД.ММ.ГГГГ.")
        elif command == CMD_EDIT_EMAIL:
            await message.answer("Введите новый email.")

    @bot.on.private_message(
        payload_contains={"cmd": CMD_GENDER_MALE},
        state=LegacyState.WAITING_FOR_EDIT_FIELD,
    )
    @bot.on.private_message(
        payload_contains={"cmd": CMD_GENDER_FEMALE},
        state=LegacyState.WAITING_FOR_EDIT_FIELD,
    )
    async def legacy_edit_gender(message: Message) -> None:
        """Редактирует поле пола в legacy-потоке."""

        state_peer = message.state_peer
        edit_field = state_peer.payload.get("edit_field") if state_peer else None
        if edit_field != CMD_EDIT_GENDER:
            await message.answer("Сейчас ожидается ввод другого поля.")
            return

        cmd = message.get_payload_json().get("cmd")
        await db.update_user(int(message.from_id), gender="male" if cmd == CMD_GENDER_MALE else "female")
        await bot.state_dispenser.set(int(message.from_id), LegacyState.WAITING_FOR_REVIEW)
        await message.answer(await get_profile_review_text(int(message.from_id)), keyboard=get_review_keyboard())

    @bot.on.private_message(state=LegacyState.WAITING_FOR_EDIT_FIELD)
    async def legacy_edit_text(message: Message) -> None:
        """Редактирует текстовые поля legacy-анкеты."""

        if not await confirm_text(message, "Введите значение текстом."):
            return

        state_peer = message.state_peer
        edit_field = state_peer.payload.get("edit_field") if state_peer else None
        user_id = int(message.from_id)
        text = message.text.strip()

        if edit_field == CMD_EDIT_FIRST_NAME:
            valid, error = await validate_first_name(text)
            if not valid:
                await message.answer(error)
                return
            await db.update_user(user_id, first_name_input=await clean_name(text))
        elif edit_field == CMD_EDIT_LAST_NAME:
            valid, error = await validate_last_name(text)
            if not valid:
                await message.answer(error)
                return
            await db.update_user(user_id, last_name_input=await clean_name(text))
        elif edit_field == CMD_EDIT_BIRTH_DATE:
            valid, error = await validate_birth_date(text)
            if not valid:
                await message.answer(error)
                return
            await db.update_user(user_id, birth_date=datetime.strptime(text, "%d.%m.%Y").date())
        elif edit_field == CMD_EDIT_EMAIL:
            valid, error = await validate_email(text)
            if not valid:
                await message.answer(error)
                return
            await db.update_user(user_id, email=text)
        else:
            await message.answer("Не удалось определить редактируемое поле.")
            return

        await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_REVIEW)
        await message.answer(await get_profile_review_text(user_id), keyboard=get_review_keyboard())

    @bot.on.private_message(
        payload_contains={"cmd": CMD_NOTIFY_YES},
        state=LegacyState.WAITING_FOR_NOTIFICATIONS_CONSENT,
    )
    @bot.on.private_message(
        payload_contains={"cmd": CMD_NOTIFY_NO},
        state=LegacyState.WAITING_FOR_NOTIFICATIONS_CONSENT,
    )
    async def legacy_notifications(message: Message) -> None:
        """Сохраняет выбор уведомлений и завершает legacy-апгрейд."""

        user_id = int(message.from_id)
        cmd = message.get_payload_json().get("cmd")
        allowed = cmd == CMD_NOTIFY_YES

        await db.update_user(
            user_id,
            notifications_allowed=allowed,
            notifications_allowed_at=datetime.now(timezone.utc),
            is_legacy=False,
        )
        await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_IIKO_REGISTRATION)
        await _run_iiko_sync(message, bot)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_RETRY_IIKO},
        state=LegacyState.WAITING_FOR_IIKO_REGISTRATION,
    )
    async def legacy_retry_iiko(message: Message) -> None:
        """Повторный запуск iiko-синхронизации в legacy-потоке."""
        await _run_iiko_sync(message, bot)
