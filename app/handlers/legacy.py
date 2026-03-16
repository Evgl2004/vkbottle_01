"""Хендлеры сценария обновления данных legacy-пользователей."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from loguru import logger
from vkbottle.bot import Bot, Message, MessageEvent
from vkbottle_types.events import GroupEventType

from app.database import db
from app.handlers.common import (
    EventMessageAdapter,
    edit_or_send_event_message,
    mark_callback_matched,
    mark_callback_skipped,
    start_callback_trace,
)
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
from app.services.vk_qr import send_card_qr
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
        logger.debug("Legacy: все поля собраны, переход в ревью (user_id={})", user_id)
        await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_REVIEW)
        await message.answer(await get_profile_review_text(user_id), keyboard=get_review_keyboard())
        return

    current = missing_fields[0]
    logger.debug(
        "Legacy: запрашиваем следующее поле (user_id={}, field='{}', remaining={})",
        user_id,
        current,
        missing_fields,
    )
    await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_FIELD, missing_fields=missing_fields)

    if current == "first_name":
        await message.answer("👤 Введите ваше имя.")
    elif current == "last_name":
        await message.answer("👥 Введите вашу фамилию.")
    elif current == "gender":
        await message.answer("⚥ Выберите ваш пол.", keyboard=get_gender_keyboard())
    elif current == "birth_date":
        await message.answer("🎂 Введите дату рождения в формате ДД.ММ.ГГГГ.")
    elif current == "email":
        await message.answer("📧 Введите email.")
    else:
        missing_fields.pop(0)
        await _ask_next_field(message, bot, missing_fields)


async def _run_iiko_sync(message: Message, bot: Bot) -> None:
    """Выполняет синхронизацию legacy-пользователя с iiko."""

    user_id = int(message.from_id)
    logger.debug("Legacy: старт iiko-синхронизации (user_id={})", user_id)
    user = await db.get_user(user_id)
    if not user:
        await bot.state_dispenser.delete(user_id)
        logger.error("Legacy: пользователь не найден перед iiko-синхронизацией (user_id={})", user_id)
        await message.answer("❌ Не удалось загрузить профиль. Введите /start.")
        return

    result = await sync_user_with_iiko(user)
    if not result.success:
        await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_IIKO_REGISTRATION)
        logger.error("Legacy: ошибка iiko-синхронизации (user_id={}): {}", user_id, result.message)
        await message.answer(
            f"❌ Ошибка синхронизации с iiko:\n{result.message}",
            keyboard=get_retry_iiko_keyboard(),
        )
        return

    await message.answer(
        "\n".join(
            [
                "✅ Данные успешно обновлены.",
                result.message,
                "🪪 Сейчас отправлю QR-коды ваших карт.",
            ]
        )
    )

    sent_qr_count = 0
    for idx, card_number in enumerate(result.card_numbers, start=1):
        if await send_card_qr(message, card_number, title=f"QR-код карты №{idx}"):
            sent_qr_count += 1

    logger.debug(
        "Legacy: отправка QR завершена (user_id={}, sent_qr_count={}, cards_count={})",
        user_id,
        sent_qr_count,
        len(result.card_numbers),
    )
    if result.card_numbers and sent_qr_count == 0:
        await message.answer("❌ Не удалось сформировать QR-код карты. Попробуйте позже.")

    await bot.state_dispenser.delete(user_id)
    logger.info("Legacy: iiko-синхронизация завершена успешно (user_id={})", user_id)
    updated = await db.get_user(user_id)
    await show_main_menu(message, user_name=(updated.first_name_input if updated else None) or "Гость")


async def start_legacy_upgrade(message: Message, bot: Bot, user) -> None:
    """Запускает legacy-сценарий по кнопке/команде `/start`."""

    logger.info(
        "Запуск legacy-апгрейда пользователя (user_id={}, is_registered={}, is_legacy={})",
        user.id,
        user.is_registered,
        user.is_legacy,
    )
    await message.answer(
        "🔄 Мы обновили бота и должны актуализировать ваши данные.\n"
        "Это займёт несколько шагов."
    )
    await message.answer(
        "📜 Пожалуйста, подтвердите согласие с правилами и обработкой персональных данных.",
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
        logger.info("Legacy: пользователь принял правила (user_id={})", user_id)
        await db.update_user(
            user_id,
            rules_accepted=True,
            rules_accepted_at=datetime.now(timezone.utc),
        )

        user = await db.get_user(user_id)
        missing = await _get_missing_fields(user)
        logger.debug("Legacy: вычислены недостающие поля (user_id={}, fields={})", user_id, missing)
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
            logger.warning(
                "Legacy: получен gender вне ожидаемой очереди полей (user_id={}, missing={})",
                user_id,
                missing,
            )
            await message.answer("⚠️ Ожидается ввод другого поля. Продолжаем актуализацию.")
            await _ask_next_field(message, bot, missing)
            return

        cmd = message.get_payload_json().get("cmd")
        gender = "male" if cmd == CMD_GENDER_MALE else "female"
        await db.update_user(user_id, gender=gender)
        logger.info("Legacy: сохранён пол (user_id={}, gender={})", user_id, gender)
        missing.pop(0)
        await _ask_next_field(message, bot, missing)

    @bot.on.private_message(state=LegacyState.WAITING_FOR_FIELD)
    async def legacy_field_text(message: Message) -> None:
        """Обрабатывает текстовый ввод недостающих полей legacy-анкеты."""

        if not await confirm_text(message, "✍️ Введите значение текстом."):
            return

        user_id = int(message.from_id)
        state_peer = message.state_peer
        missing = list(state_peer.payload.get("missing_fields", [])) if state_peer else []
        if not missing:
            logger.debug("Legacy: список missing пуст, переводим в ревью (user_id={})", user_id)
            await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_REVIEW)
            await message.answer(await get_profile_review_text(user_id), keyboard=get_review_keyboard())
            return

        current = missing[0]
        text = message.text.strip()
        logger.debug("Legacy: обработка текстового поля (user_id={}, field='{}')", user_id, current)

        if current == "first_name":
            valid, error = await validate_first_name(text)
            if not valid:
                logger.warning("Legacy: некорректное имя (user_id={}): {}", user_id, error)
                await message.answer(error)
                return
            await db.update_user(user_id, first_name_input=await clean_name(text))
            logger.info("Legacy: имя сохранено (user_id={})", user_id)
        elif current == "last_name":
            valid, error = await validate_last_name(text)
            if not valid:
                logger.warning("Legacy: некорректная фамилия (user_id={}): {}", user_id, error)
                await message.answer(error)
                return
            await db.update_user(user_id, last_name_input=await clean_name(text))
            logger.info("Legacy: фамилия сохранена (user_id={})", user_id)
        elif current == "birth_date":
            valid, error = await validate_birth_date(text)
            if not valid:
                logger.warning("Legacy: некорректная дата рождения (user_id={}): {}", user_id, error)
                await message.answer(error)
                return
            await db.update_user(user_id, birth_date=datetime.strptime(text, "%d.%m.%Y").date())
            logger.info("Legacy: дата рождения сохранена (user_id={})", user_id)
        elif current == "email":
            valid, error = await validate_email(text)
            if not valid:
                logger.warning("Legacy: некорректный email (user_id={}): {}", user_id, error)
                await message.answer(error)
                return
            await db.update_user(user_id, email=text)
            logger.info("Legacy: email сохранён (user_id={})", user_id)
        else:
            logger.warning("Legacy: неизвестное поле '{}' (user_id={})", current, user_id)
            await message.answer("⚠️ Неизвестное поле актуализации, пропускаем.")

        missing.pop(0)
        await _ask_next_field(message, bot, missing)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_REVIEW_OK},
        state=LegacyState.WAITING_FOR_REVIEW,
    )
    async def legacy_review_ok(message: Message) -> None:
        """Подтверждение анкеты legacy-пользователем."""
        user_id = int(message.from_id)
        logger.info("Legacy: анкета подтверждена (user_id={})", user_id)
        await bot.state_dispenser.set(
            user_id,
            LegacyState.WAITING_FOR_NOTIFICATIONS_CONSENT,
        )
        await message.answer(
            "📢 Выберите вариант согласия на уведомления:",
            keyboard=get_notifications_keyboard(),
        )

    @bot.on.private_message(
        payload_contains={"cmd": CMD_REVIEW_EDIT},
        state=LegacyState.WAITING_FOR_REVIEW,
    )
    async def legacy_review_edit(message: Message) -> None:
        """Открывает выбор поля для редактирования в legacy-потоке."""
        user_id = int(message.from_id)
        logger.info("Legacy: открыт выбор поля для редактирования (user_id={})", user_id)
        await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_EDIT_CHOICE)
        await message.answer("✏️ Выберите поле для редактирования:", keyboard=get_edit_choice_keyboard())

    @bot.on.private_message(state=LegacyState.WAITING_FOR_EDIT_CHOICE)
    async def legacy_edit_choice(message: Message) -> None:
        """Обрабатывает выбор поля для редактирования."""

        payload = message.get_payload_json()
        command = payload.get("cmd") if isinstance(payload, dict) else None
        user_id = int(message.from_id)
        logger.debug("Legacy: выбор поля редактирования (user_id={}, cmd={})", user_id, command)

        if command == CMD_EDIT_CANCEL:
            await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_REVIEW)
            await message.answer(await get_profile_review_text(user_id), keyboard=get_review_keyboard())
            return

        if command not in {
            CMD_EDIT_FIRST_NAME,
            CMD_EDIT_LAST_NAME,
            CMD_EDIT_GENDER,
            CMD_EDIT_BIRTH_DATE,
            CMD_EDIT_EMAIL,
        }:
            await message.answer("⚠️ Не удалось определить поле редактирования.")
            return

        await bot.state_dispenser.set(
            user_id,
            LegacyState.WAITING_FOR_EDIT_FIELD,
            edit_field=command,
        )
        logger.debug("Legacy: переход в WAITING_FOR_EDIT_FIELD (user_id={}, field={})", user_id, command)

        if command == CMD_EDIT_GENDER:
            await message.answer("⚥ Выберите новый пол.", keyboard=get_gender_keyboard())
        elif command == CMD_EDIT_FIRST_NAME:
            await message.answer("👤 Введите новое имя.")
        elif command == CMD_EDIT_LAST_NAME:
            await message.answer("👥 Введите новую фамилию.")
        elif command == CMD_EDIT_BIRTH_DATE:
            await message.answer("🎂 Введите новую дату рождения в формате ДД.ММ.ГГГГ.")
        elif command == CMD_EDIT_EMAIL:
            await message.answer("📧 Введите новый email.")

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
            logger.warning(
                "Legacy: получен gender при несоответствующем edit_field (user_id={}, edit_field={})",
                int(message.from_id),
                edit_field,
            )
            await message.answer("⚠️ Сейчас ожидается ввод другого поля.")
            return

        cmd = message.get_payload_json().get("cmd")
        user_id = int(message.from_id)
        gender = "male" if cmd == CMD_GENDER_MALE else "female"
        await db.update_user(user_id, gender=gender)
        logger.info("Legacy: обновлён пол в редактировании (user_id={}, gender={})", user_id, gender)
        await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_REVIEW)
        await message.answer(await get_profile_review_text(user_id), keyboard=get_review_keyboard())

    @bot.on.private_message(state=LegacyState.WAITING_FOR_EDIT_FIELD)
    async def legacy_edit_text(message: Message) -> None:
        """Редактирует текстовые поля legacy-анкеты."""

        if not await confirm_text(message, "✍️ Введите значение текстом."):
            return

        state_peer = message.state_peer
        edit_field = state_peer.payload.get("edit_field") if state_peer else None
        user_id = int(message.from_id)
        text = message.text.strip()
        logger.debug("Legacy: редактирование текстового поля (user_id={}, field={})", user_id, edit_field)

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
            logger.warning("Legacy: неизвестное поле редактирования (user_id={}, field={})", user_id, edit_field)
            await message.answer("⚠️ Не удалось определить редактируемое поле.")
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
        logger.info(
            "Legacy: выбор уведомлений (user_id={}, notifications_allowed={})",
            user_id,
            allowed,
        )

        await db.update_user(
            user_id,
            notifications_allowed=allowed,
            notifications_allowed_at=datetime.now(timezone.utc),
            is_legacy=False,
        )
        await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_IIKO_REGISTRATION)
        logger.debug("Legacy: переход в WAITING_FOR_IIKO_REGISTRATION (user_id={})", user_id)
        await _run_iiko_sync(message, bot)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_RETRY_IIKO},
        state=LegacyState.WAITING_FOR_IIKO_REGISTRATION,
    )
    async def legacy_retry_iiko(message: Message) -> None:
        """Повторный запуск iiko-синхронизации в legacy-потоке."""
        logger.info("Legacy: повторный запуск iiko-синхронизации (user_id={})", int(message.from_id))
        await _run_iiko_sync(message, bot)

    @bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent, blocking=False)
    async def legacy_callback_router(event: MessageEvent) -> None:
        """Обрабатывает callback-кнопки legacy-апгрейда.

        Команды пересекаются с регистрацией, поэтому обработка запускается
        только в релевантных `LegacyState`.
        """

        payload: dict[str, Any] = event.get_payload_json() or {}
        user_id = int(event.user_id)
        state_peer = await bot.state_dispenser.get(user_id)
        state_value = state_peer.state if state_peer else None
        command, _started_at = start_callback_trace(
            "legacy",
            event,
            payload,
            state=state_value,
        )
        if command not in {
            CMD_ACCEPT_RULES,
            CMD_GENDER_MALE,
            CMD_GENDER_FEMALE,
            CMD_REVIEW_OK,
            CMD_REVIEW_EDIT,
            CMD_EDIT_FIRST_NAME,
            CMD_EDIT_LAST_NAME,
            CMD_EDIT_GENDER,
            CMD_EDIT_BIRTH_DATE,
            CMD_EDIT_EMAIL,
            CMD_EDIT_CANCEL,
            CMD_NOTIFY_YES,
            CMD_NOTIFY_NO,
            CMD_RETRY_IIKO,
        }:
            mark_callback_skipped(
                "legacy",
                event,
                reason="unsupported_cmd",
                command=command,
                state=state_value,
            )
            return

        adapter = EventMessageAdapter(event)

        def in_state(state: LegacyState) -> bool:
            return state_value == str(state)

        if command == CMD_ACCEPT_RULES and in_state(LegacyState.WAITING_FOR_RULES_CONSENT):
            await event.send_empty_answer()
            mark_callback_matched("legacy", event, command=command, state=state_value)
            logger.info("Legacy callback: пользователь принял правила (user_id={})", user_id)
            await db.update_user(
                user_id,
                rules_accepted=True,
                rules_accepted_at=datetime.now(timezone.utc),
            )
            user = await db.get_user(user_id)
            missing = await _get_missing_fields(user)
            await _ask_next_field(adapter, bot, missing)
            return

        if command in {CMD_GENDER_MALE, CMD_GENDER_FEMALE} and in_state(LegacyState.WAITING_FOR_FIELD):
            missing = list(state_peer.payload.get("missing_fields", [])) if state_peer else []
            if not missing or missing[0] != "gender":
                mark_callback_skipped(
                    "legacy",
                    event,
                    reason="waiting_for_field_not_gender",
                    command=command,
                    state=state_value,
                )
                return

            await event.send_empty_answer()
            mark_callback_matched("legacy", event, command=command, state=state_value)
            gender = "male" if command == CMD_GENDER_MALE else "female"
            await db.update_user(user_id, gender=gender)
            logger.info("Legacy callback: сохранён пол (user_id={}, gender={})", user_id, gender)
            missing.pop(0)
            await _ask_next_field(adapter, bot, missing)
            return

        if command == CMD_REVIEW_OK and in_state(LegacyState.WAITING_FOR_REVIEW):
            await event.send_empty_answer()
            mark_callback_matched("legacy", event, command=command, state=state_value)
            logger.info("Legacy callback: анкета подтверждена (user_id={})", user_id)
            await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_NOTIFICATIONS_CONSENT)
            await edit_or_send_event_message(
                event,
                "📢 Выберите вариант согласия на уведомления:",
                keyboard=get_notifications_keyboard(),
            )
            return

        if command == CMD_REVIEW_EDIT and in_state(LegacyState.WAITING_FOR_REVIEW):
            await event.send_empty_answer()
            mark_callback_matched("legacy", event, command=command, state=state_value)
            logger.info("Legacy callback: открыт выбор поля редактирования (user_id={})", user_id)
            await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_EDIT_CHOICE)
            await edit_or_send_event_message(
                event,
                "✏️ Выберите поле для редактирования:",
                keyboard=get_edit_choice_keyboard(),
            )
            return

        if in_state(LegacyState.WAITING_FOR_EDIT_CHOICE) and command in {
            CMD_EDIT_FIRST_NAME,
            CMD_EDIT_LAST_NAME,
            CMD_EDIT_GENDER,
            CMD_EDIT_BIRTH_DATE,
            CMD_EDIT_EMAIL,
            CMD_EDIT_CANCEL,
        }:
            await event.send_empty_answer()
            mark_callback_matched("legacy", event, command=command, state=state_value)
            logger.debug("Legacy callback: выбор поля редактирования (user_id={}, cmd={})", user_id, command)
            if command == CMD_EDIT_CANCEL:
                await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_REVIEW)
                await edit_or_send_event_message(
                    event,
                    await get_profile_review_text(user_id),
                    keyboard=get_review_keyboard(),
                )
                return

            if command not in {
                CMD_EDIT_FIRST_NAME,
                CMD_EDIT_LAST_NAME,
                CMD_EDIT_GENDER,
                CMD_EDIT_BIRTH_DATE,
                CMD_EDIT_EMAIL,
            }:
                mark_callback_skipped(
                    "legacy",
                    event,
                    reason="unsupported_edit_cmd",
                    command=command,
                    state=state_value,
                )
                return

            await bot.state_dispenser.set(
                user_id,
                LegacyState.WAITING_FOR_EDIT_FIELD,
                edit_field=command,
            )
            if command == CMD_EDIT_GENDER:
                await edit_or_send_event_message(event, "⚥ Выберите новый пол.", keyboard=get_gender_keyboard())
                return
            if command == CMD_EDIT_FIRST_NAME:
                await edit_or_send_event_message(event, "👤 Введите новое имя.")
                return
            if command == CMD_EDIT_LAST_NAME:
                await edit_or_send_event_message(event, "👥 Введите новую фамилию.")
                return
            if command == CMD_EDIT_BIRTH_DATE:
                await edit_or_send_event_message(event, "🎂 Введите новую дату рождения в формате ДД.ММ.ГГГГ.")
                return
            if command == CMD_EDIT_EMAIL:
                await edit_or_send_event_message(event, "📧 Введите новый email.")
                return

        if command in {CMD_GENDER_MALE, CMD_GENDER_FEMALE} and in_state(LegacyState.WAITING_FOR_EDIT_FIELD):
            edit_field = state_peer.payload.get("edit_field") if state_peer else None
            if edit_field != CMD_EDIT_GENDER:
                mark_callback_skipped(
                    "legacy",
                    event,
                    reason="edit_field_mismatch",
                    command=command,
                    state=state_value,
                )
                return

            await event.send_empty_answer()
            mark_callback_matched("legacy", event, command=command, state=state_value)
            gender = "male" if command == CMD_GENDER_MALE else "female"
            await db.update_user(user_id, gender=gender)
            logger.info("Legacy callback: обновлён пол в редактировании (user_id={}, gender={})", user_id, gender)
            await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_REVIEW)
            await edit_or_send_event_message(
                event,
                await get_profile_review_text(user_id),
                keyboard=get_review_keyboard(),
            )
            return

        if command in {CMD_NOTIFY_YES, CMD_NOTIFY_NO} and in_state(LegacyState.WAITING_FOR_NOTIFICATIONS_CONSENT):
            await event.send_empty_answer()
            mark_callback_matched("legacy", event, command=command, state=state_value)
            allowed = command == CMD_NOTIFY_YES
            logger.info(
                "Legacy callback: выбор уведомлений (user_id={}, notifications_allowed={})",
                user_id,
                allowed,
            )
            await db.update_user(
                user_id,
                notifications_allowed=allowed,
                notifications_allowed_at=datetime.now(timezone.utc),
                is_legacy=False,
            )
            await bot.state_dispenser.set(user_id, LegacyState.WAITING_FOR_IIKO_REGISTRATION)
            await edit_or_send_event_message(event, "⏳ Выполняю синхронизацию профиля с iiko...")
            await _run_iiko_sync(adapter, bot)
            return

        if command == CMD_RETRY_IIKO and in_state(LegacyState.WAITING_FOR_IIKO_REGISTRATION):
            await event.send_empty_answer()
            mark_callback_matched("legacy", event, command=command, state=state_value)
            logger.info("Legacy callback: повторный запуск iiko-синхронизации (user_id={})", user_id)
            await _run_iiko_sync(adapter, bot)
            return

        mark_callback_skipped(
            "legacy",
            event,
            reason="state_mismatch_or_unhandled",
            command=command,
            state=state_value,
        )
