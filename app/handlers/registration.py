"""Хендлеры сценария регистрации нового пользователя."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
from app.states.registration import RegistrationState
from app.utils.profile import get_profile_review_text
from app.utils.validation import (
    clean_name,
    confirm_text,
    normalize_phone,
    validate_birth_date,
    validate_email,
    validate_first_name,
    validate_last_name,
    validate_phone,
)


def _mask_phone(phone: str) -> str:
    """Маскирует номер телефона для безопасного логирования.

    Пример:
    - `+79991234567` -> `+7*******567`
    """

    if len(phone) < 4:
        return "***"
    return f"{phone[:2]}*******{phone[-3:]}"


def _mask_email(email: str) -> str:
    """Маскирует email для безопасного логирования."""

    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


async def _show_review(message: Message) -> None:
    """Показывает пользователю экран проверки введённой анкеты."""
    logger.debug("Показ экрана ревью анкеты (user_id={})", int(message.from_id))
    text = await get_profile_review_text(int(message.from_id))
    await message.answer(text, keyboard=get_review_keyboard())


async def _run_iiko_sync(message: Message, bot: Bot) -> None:
    """Запускает синхронизацию пользователя с iiko и завершает регистрацию."""

    user_id = int(message.from_id)
    logger.debug("Старт синхронизации с iiko в регистрации (user_id={})", user_id)

    user = await db.get_user(user_id)
    if not user:
        await bot.state_dispenser.delete(user_id)
        await message.answer("❌ Не удалось загрузить профиль пользователя. Введите /start.")
        return

    result = await sync_user_with_iiko(user)
    if not result.success:
        logger.error(
            "Синхронизация с iiko завершилась ошибкой (user_id={}): {}",
            user_id,
            result.message,
        )
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_IIKO_REGISTRATION)
        logger.debug("Переход в WAITING_FOR_IIKO_REGISTRATION после ошибки (user_id={})", user_id)
        await message.answer(
            f"❌ Ошибка синхронизации с iiko:\n{result.message}",
            keyboard=get_retry_iiko_keyboard(),
        )
        return

    logger.debug(
        "Синхронизация с iiko успешна (user_id={}, cards_count={})",
        user_id,
        len(result.card_numbers),
    )

    await message.answer(
        "\n".join(
            [
                "✅ Регистрация успешно завершена.",
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
        "Завершена отправка QR после регистрации (user_id={}, sent_qr_count={}, cards_count={})",
        user_id,
        sent_qr_count,
        len(result.card_numbers),
    )
    if result.card_numbers and sent_qr_count == 0:
        await message.answer(
            "❌ Не удалось сформировать QR-код карты. Попробуйте открыть раздел «Виртуальная карта» чуть позже."
        )

    await bot.state_dispenser.delete(user_id)
    logger.debug("Состояние регистрации очищено после успешной синхронизации (user_id={})", user_id)
    refreshed = await db.get_user(user_id)
    await show_main_menu(message, user_name=(refreshed.first_name_input if refreshed else None) or "Гость")


def register_registration_handlers(bot: Bot) -> None:
    """Регистрирует весь набор обработчиков регистрации."""

    @bot.on.private_message(
        payload_contains={"cmd": CMD_ACCEPT_RULES},
        state=RegistrationState.WAITING_FOR_RULES_CONSENT,
    )
    async def process_rules_consent(message: Message) -> None:
        """Фиксирует согласие с правилами и переводит на шаг ввода телефона."""

        user_id = int(message.from_id)
        logger.info("Пользователь принял правила (user_id={})", user_id)

        await db.update_user(
            user_id,
            rules_accepted=True,
            rules_accepted_at=datetime.now(timezone.utc),
        )
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_CONTACT)
        logger.debug("Переход в WAITING_FOR_CONTACT (user_id={})", user_id)
        await message.answer(
            "✅ Спасибо! Теперь введите номер телефона в формате +79991234567."
        )

    @bot.on.private_message(
        payload_contains={"cmd": CMD_GENDER_MALE},
        state=RegistrationState.WAITING_FOR_GENDER,
    )
    @bot.on.private_message(
        payload_contains={"cmd": CMD_GENDER_FEMALE},
        state=RegistrationState.WAITING_FOR_GENDER,
    )
    async def process_gender(message: Message) -> None:
        """Сохраняет выбранный пол и запрашивает дату рождения."""

        user_id = int(message.from_id)
        command = message.get_payload_json().get("cmd")
        gender = "male" if command == CMD_GENDER_MALE else "female"
        logger.info("Выбран пол в регистрации (user_id={}, gender={})", user_id, gender)

        await db.update_user(user_id, gender=gender)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_BIRTH_DATE)
        logger.debug("Переход в WAITING_FOR_BIRTH_DATE (user_id={})", user_id)
        await message.answer("🎂 Введите дату рождения в формате ДД.ММ.ГГГГ.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_CONTACT)
    async def process_contact(message: Message) -> None:
        """Обрабатывает шаг ввода телефона.

        В VK отсутствует универсальная кнопка безопасной передачи контакта,
        поэтому на этом шаге используется ручной ввод номера.
        """

        if not await confirm_text(message, "📱 Введите номер телефона текстом (пример: +79991234567)."):
            return

        user_id = int(message.from_id)
        text = message.text.strip()
        logger.debug("Получен ввод телефона в регистрации (user_id={}, raw='{}')", user_id, text)
        valid, error = await validate_phone(text)
        if not valid:
            logger.warning("Некорректный телефон в регистрации (user_id={}): {}", user_id, error)
            await message.answer(error)
            return

        normalized = await normalize_phone(text)
        await db.update_user(user_id, phone_number=normalized)
        logger.info(
            "Телефон сохранён в регистрации (user_id={}, phone={})",
            user_id,
            _mask_phone(normalized),
        )
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_FIRST_NAME)
        logger.debug("Переход в WAITING_FOR_FIRST_NAME (user_id={})", user_id)
        await message.answer("✅ Телефон сохранён. Теперь введите ваше имя.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_FIRST_NAME)
    async def process_first_name(message: Message) -> None:
        """Проверяет и сохраняет имя пользователя."""

        if not await confirm_text(message, "👤 Введите имя текстом."):
            return

        user_id = int(message.from_id)
        text = message.text.strip()
        logger.debug("Получено имя в регистрации (user_id={}, value='{}')", user_id, text)
        valid, error = await validate_first_name(text)
        if not valid:
            logger.warning("Некорректное имя в регистрации (user_id={}): {}", user_id, error)
            await message.answer(error)
            return

        cleaned = await clean_name(text)
        await db.update_user(user_id, first_name_input=cleaned)
        logger.info("Имя сохранено (user_id={}, value='{}')", user_id, cleaned)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_LAST_NAME)
        logger.debug("Переход в WAITING_FOR_LAST_NAME (user_id={})", user_id)
        await message.answer("✅ Имя сохранено. Теперь введите фамилию.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_LAST_NAME)
    async def process_last_name(message: Message) -> None:
        """Проверяет и сохраняет фамилию пользователя."""

        if not await confirm_text(message, "👥 Введите фамилию текстом."):
            return

        user_id = int(message.from_id)
        text = message.text.strip()
        logger.debug("Получена фамилия в регистрации (user_id={}, value='{}')", user_id, text)
        valid, error = await validate_last_name(text)
        if not valid:
            logger.warning("Некорректная фамилия в регистрации (user_id={}): {}", user_id, error)
            await message.answer(error)
            return

        cleaned = await clean_name(text)
        await db.update_user(user_id, last_name_input=cleaned)
        logger.info("Фамилия сохранена (user_id={}, value='{}')", user_id, cleaned)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_GENDER)
        logger.debug("Переход в WAITING_FOR_GENDER (user_id={})", user_id)
        await message.answer("✅ Фамилия сохранена. Выберите пол.", keyboard=get_gender_keyboard())

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_BIRTH_DATE)
    async def process_birth_date(message: Message) -> None:
        """Проверяет дату рождения и запрашивает email."""

        if not await confirm_text(message, "🎂 Введите дату рождения текстом в формате ДД.ММ.ГГГГ."):
            return

        user_id = int(message.from_id)
        text = message.text.strip()
        logger.debug("Получена дата рождения в регистрации (user_id={}, value='{}')", user_id, text)
        valid, error = await validate_birth_date(text)
        if not valid:
            logger.warning("Некорректная дата рождения (user_id={}): {}", user_id, error)
            await message.answer(error)
            return

        birth_date = datetime.strptime(text, "%d.%m.%Y").date()
        await db.update_user(user_id, birth_date=birth_date)
        logger.info("Дата рождения сохранена (user_id={}, birth_date={})", user_id, birth_date)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EMAIL)
        logger.debug("Переход в WAITING_FOR_EMAIL (user_id={})", user_id)
        await message.answer("✅ Дата рождения сохранена. Теперь введите email.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EMAIL)
    async def process_email(message: Message) -> None:
        """Проверяет email и переводит пользователя на экран ревью."""

        if not await confirm_text(message, "📧 Введите email текстом."):
            return

        user_id = int(message.from_id)
        text = message.text.strip()
        logger.debug("Получен email в регистрации (user_id={}, value='{}')", user_id, text)
        valid, error = await validate_email(text)
        if not valid:
            logger.warning("Некорректный email в регистрации (user_id={}): {}", user_id, error)
            await message.answer(error)
            return

        await db.update_user(user_id, email=text)
        logger.info("Email сохранён (user_id={}, email={})", user_id, _mask_email(text))
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
        logger.debug("Переход в WAITING_FOR_REVIEW (user_id={})", user_id)
        await _show_review(message)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_REVIEW_OK},
        state=RegistrationState.WAITING_FOR_REVIEW,
    )
    async def review_ok(message: Message) -> None:
        """Обрабатывает подтверждение корректности анкеты."""
        user_id = int(message.from_id)
        logger.info("Анкета подтверждена пользователем (user_id={})", user_id)
        await bot.state_dispenser.set(
            user_id,
            RegistrationState.WAITING_FOR_NOTIFICATIONS_CONSENT,
        )
        logger.debug("Переход в WAITING_FOR_NOTIFICATIONS_CONSENT (user_id={})", user_id)
        await message.answer(
            "📢 Ознакомьтесь с условиями уведомлений и выберите вариант:",
            keyboard=get_notifications_keyboard(),
        )

    @bot.on.private_message(
        payload_contains={"cmd": CMD_REVIEW_EDIT},
        state=RegistrationState.WAITING_FOR_REVIEW,
    )
    async def review_edit(message: Message) -> None:
        """Открывает выбор поля для редактирования анкеты."""
        user_id = int(message.from_id)
        logger.info("Пользователь открыл редактирование анкеты (user_id={})", user_id)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_CHOICE)
        logger.debug("Переход в WAITING_FOR_EDIT_CHOICE (user_id={})", user_id)
        await message.answer("✏️ Выберите поле для редактирования:", keyboard=get_edit_choice_keyboard())

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_CHOICE)
    async def process_edit_choice(message: Message) -> None:
        """Обрабатывает выбор редактируемого поля из клавиатуры."""

        payload = message.get_payload_json()
        command = payload.get("cmd") if isinstance(payload, dict) else None
        user_id = int(message.from_id)
        logger.debug("Выбор поля редактирования (user_id={}, cmd={})", user_id, command)

        if command == CMD_EDIT_CANCEL:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
            logger.debug("Отмена редактирования, возврат в WAITING_FOR_REVIEW (user_id={})", user_id)
            await _show_review(message)
            return

        if command == CMD_EDIT_FIRST_NAME:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_FIRST_NAME)
            logger.debug("Переход в WAITING_FOR_EDIT_FIRST_NAME (user_id={})", user_id)
            await message.answer("👤 Введите новое имя.")
            return
        if command == CMD_EDIT_LAST_NAME:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_LAST_NAME)
            logger.debug("Переход в WAITING_FOR_EDIT_LAST_NAME (user_id={})", user_id)
            await message.answer("👥 Введите новую фамилию.")
            return
        if command == CMD_EDIT_GENDER:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_GENDER)
            logger.debug("Переход в WAITING_FOR_EDIT_GENDER (user_id={})", user_id)
            await message.answer("⚥ Выберите пол.", keyboard=get_gender_keyboard())
            return
        if command == CMD_EDIT_BIRTH_DATE:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_BIRTH_DATE)
            logger.debug("Переход в WAITING_FOR_EDIT_BIRTH_DATE (user_id={})", user_id)
            await message.answer("🎂 Введите новую дату рождения в формате ДД.ММ.ГГГГ.")
            return
        if command == CMD_EDIT_EMAIL:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_EMAIL)
            logger.debug("Переход в WAITING_FOR_EDIT_EMAIL (user_id={})", user_id)
            await message.answer("📧 Введите новый email.")
            return

        await message.answer("⚠️ Не удалось определить выбранное поле. Выберите действие снова.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_FIRST_NAME)
    async def edit_first_name(message: Message) -> None:
        """Редактирует поле имени."""
        user_id = int(message.from_id)
        if not await confirm_text(message, "👤 Введите имя текстом."):
            return
        valid, error = await validate_first_name(message.text.strip())
        if not valid:
            await message.answer(error)
            return
        cleaned = await clean_name(message.text.strip())
        await db.update_user(user_id, first_name_input=cleaned)
        logger.info("Обновлено имя в анкете (user_id={}, value='{}')", user_id, cleaned)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
        logger.debug("Возврат в WAITING_FOR_REVIEW (user_id={})", user_id)
        await _show_review(message)

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_LAST_NAME)
    async def edit_last_name(message: Message) -> None:
        """Редактирует поле фамилии."""
        user_id = int(message.from_id)
        if not await confirm_text(message, "👥 Введите фамилию текстом."):
            return
        valid, error = await validate_last_name(message.text.strip())
        if not valid:
            await message.answer(error)
            return
        cleaned = await clean_name(message.text.strip())
        await db.update_user(user_id, last_name_input=cleaned)
        logger.info("Обновлена фамилия в анкете (user_id={}, value='{}')", user_id, cleaned)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
        logger.debug("Возврат в WAITING_FOR_REVIEW (user_id={})", user_id)
        await _show_review(message)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_GENDER_MALE},
        state=RegistrationState.WAITING_FOR_EDIT_GENDER,
    )
    @bot.on.private_message(
        payload_contains={"cmd": CMD_GENDER_FEMALE},
        state=RegistrationState.WAITING_FOR_EDIT_GENDER,
    )
    async def edit_gender(message: Message) -> None:
        """Редактирует поле пола."""

        user_id = int(message.from_id)
        cmd = message.get_payload_json().get("cmd")
        gender = "male" if cmd == CMD_GENDER_MALE else "female"
        await db.update_user(user_id, gender=gender)
        logger.info("Обновлён пол в анкете (user_id={}, gender={})", user_id, gender)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
        logger.debug("Возврат в WAITING_FOR_REVIEW (user_id={})", user_id)
        await _show_review(message)

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_BIRTH_DATE)
    async def edit_birth_date(message: Message) -> None:
        """Редактирует поле даты рождения."""
        user_id = int(message.from_id)
        if not await confirm_text(message, "🎂 Введите дату рождения текстом."):
            return
        text = message.text.strip()
        valid, error = await validate_birth_date(text)
        if not valid:
            await message.answer(error)
            return
        birth_date = datetime.strptime(text, "%d.%m.%Y").date()
        await db.update_user(user_id, birth_date=birth_date)
        logger.info("Обновлена дата рождения в анкете (user_id={}, birth_date={})", user_id, birth_date)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
        logger.debug("Возврат в WAITING_FOR_REVIEW (user_id={})", user_id)
        await _show_review(message)

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_EMAIL)
    async def edit_email(message: Message) -> None:
        """Редактирует поле email."""
        user_id = int(message.from_id)
        if not await confirm_text(message, "📧 Введите email текстом."):
            return
        text = message.text.strip()
        valid, error = await validate_email(text)
        if not valid:
            await message.answer(error)
            return
        await db.update_user(user_id, email=text)
        logger.info("Обновлён email в анкете (user_id={}, email={})", user_id, _mask_email(text))
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
        logger.debug("Возврат в WAITING_FOR_REVIEW (user_id={})", user_id)
        await _show_review(message)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_NOTIFY_YES},
        state=RegistrationState.WAITING_FOR_NOTIFICATIONS_CONSENT,
    )
    @bot.on.private_message(
        payload_contains={"cmd": CMD_NOTIFY_NO},
        state=RegistrationState.WAITING_FOR_NOTIFICATIONS_CONSENT,
    )
    async def process_notifications(message: Message) -> None:
        """Сохраняет выбор по уведомлениям и запускает синхронизацию с iiko."""

        user_id = int(message.from_id)
        command = message.get_payload_json().get("cmd")
        allowed = command == CMD_NOTIFY_YES
        logger.info(
            "Выбор уведомлений в регистрации (user_id={}, notifications_allowed={})",
            user_id,
            allowed,
        )

        await db.update_user(
            user_id,
            notifications_allowed=allowed,
            notifications_allowed_at=datetime.now(timezone.utc),
        )

        await bot.state_dispenser.set(
            user_id,
            RegistrationState.WAITING_FOR_IIKO_REGISTRATION,
        )
        logger.debug("Переход в WAITING_FOR_IIKO_REGISTRATION (user_id={})", user_id)
        await _run_iiko_sync(message, bot)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_RETRY_IIKO},
        state=RegistrationState.WAITING_FOR_IIKO_REGISTRATION,
    )
    async def retry_iiko_sync(message: Message) -> None:
        """Повторно запускает iiko-синхронизацию после предыдущей ошибки."""
        logger.info("Повторный запуск iiko-синхронизации (user_id={})", int(message.from_id))
        await _run_iiko_sync(message, bot)

    @bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent, blocking=False)
    async def registration_callback_router(event: MessageEvent) -> None:
        """Обрабатывает callback-кнопки регистрационного сценария.

        Важный момент:
        - В разделе регистрации payload-команды пересекаются с legacy-потоком.
        - Поэтому обработчик работает только если текущее FSM-состояние
          относится именно к `RegistrationState`.
        """

        payload: dict[str, Any] = event.get_payload_json() or {}
        user_id = int(event.user_id)
        state_peer = await bot.state_dispenser.get(user_id)
        state_value = state_peer.state if state_peer else None
        command, _started_at = start_callback_trace(
            "registration",
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
                "registration",
                event,
                reason="unsupported_cmd",
                command=command,
                state=state_value,
            )
            return

        adapter = EventMessageAdapter(event)

        def in_state(state: RegistrationState) -> bool:
            return state_value == str(state)

        if command == CMD_ACCEPT_RULES and in_state(RegistrationState.WAITING_FOR_RULES_CONSENT):
            await event.send_empty_answer()
            mark_callback_matched("registration", event, command=command, state=state_value)
            logger.info("Callback: пользователь принял правила (user_id={})", user_id)
            await db.update_user(
                user_id,
                rules_accepted=True,
                rules_accepted_at=datetime.now(timezone.utc),
            )
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_CONTACT)
            await edit_or_send_event_message(
                event,
                "✅ Спасибо! Теперь введите номер телефона в формате +79991234567.",
            )
            return

        if command in {CMD_GENDER_MALE, CMD_GENDER_FEMALE} and in_state(RegistrationState.WAITING_FOR_GENDER):
            await event.send_empty_answer()
            mark_callback_matched("registration", event, command=command, state=state_value)
            gender = "male" if command == CMD_GENDER_MALE else "female"
            logger.info("Callback: выбран пол в регистрации (user_id={}, gender={})", user_id, gender)
            await db.update_user(user_id, gender=gender)
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_BIRTH_DATE)
            await edit_or_send_event_message(event, "🎂 Введите дату рождения в формате ДД.ММ.ГГГГ.")
            return

        if command in {CMD_GENDER_MALE, CMD_GENDER_FEMALE} and in_state(RegistrationState.WAITING_FOR_EDIT_GENDER):
            await event.send_empty_answer()
            mark_callback_matched("registration", event, command=command, state=state_value)
            gender = "male" if command == CMD_GENDER_MALE else "female"
            logger.info("Callback: обновлён пол в анкете (user_id={}, gender={})", user_id, gender)
            await db.update_user(user_id, gender=gender)
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
            await edit_or_send_event_message(
                event,
                await get_profile_review_text(user_id),
                keyboard=get_review_keyboard(),
            )
            return

        if command == CMD_REVIEW_OK and in_state(RegistrationState.WAITING_FOR_REVIEW):
            await event.send_empty_answer()
            mark_callback_matched("registration", event, command=command, state=state_value)
            logger.info("Callback: анкета подтверждена пользователем (user_id={})", user_id)
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_NOTIFICATIONS_CONSENT)
            await edit_or_send_event_message(
                event,
                "📢 Ознакомьтесь с условиями уведомлений и выберите вариант:",
                keyboard=get_notifications_keyboard(),
            )
            return

        if command == CMD_REVIEW_EDIT and in_state(RegistrationState.WAITING_FOR_REVIEW):
            await event.send_empty_answer()
            mark_callback_matched("registration", event, command=command, state=state_value)
            logger.info("Callback: пользователь открыл редактирование анкеты (user_id={})", user_id)
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_CHOICE)
            await edit_or_send_event_message(
                event,
                "✏️ Выберите поле для редактирования:",
                keyboard=get_edit_choice_keyboard(),
            )
            return

        if in_state(RegistrationState.WAITING_FOR_EDIT_CHOICE) and command in {
            CMD_EDIT_FIRST_NAME,
            CMD_EDIT_LAST_NAME,
            CMD_EDIT_GENDER,
            CMD_EDIT_BIRTH_DATE,
            CMD_EDIT_EMAIL,
            CMD_EDIT_CANCEL,
        }:
            await event.send_empty_answer()
            mark_callback_matched("registration", event, command=command, state=state_value)
            logger.debug("Callback: выбор поля редактирования (user_id={}, cmd={})", user_id, command)
            if command == CMD_EDIT_CANCEL:
                await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
                await edit_or_send_event_message(
                    event,
                    await get_profile_review_text(user_id),
                    keyboard=get_review_keyboard(),
                )
                return
            if command == CMD_EDIT_FIRST_NAME:
                await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_FIRST_NAME)
                await edit_or_send_event_message(event, "👤 Введите новое имя.")
                return
            if command == CMD_EDIT_LAST_NAME:
                await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_LAST_NAME)
                await edit_or_send_event_message(event, "👥 Введите новую фамилию.")
                return
            if command == CMD_EDIT_GENDER:
                await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_GENDER)
                await edit_or_send_event_message(event, "⚥ Выберите пол.", keyboard=get_gender_keyboard())
                return
            if command == CMD_EDIT_BIRTH_DATE:
                await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_BIRTH_DATE)
                await edit_or_send_event_message(event, "🎂 Введите новую дату рождения в формате ДД.ММ.ГГГГ.")
                return
            if command == CMD_EDIT_EMAIL:
                await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_EMAIL)
                await edit_or_send_event_message(event, "📧 Введите новый email.")
                return

        if command in {CMD_NOTIFY_YES, CMD_NOTIFY_NO} and in_state(RegistrationState.WAITING_FOR_NOTIFICATIONS_CONSENT):
            await event.send_empty_answer()
            mark_callback_matched("registration", event, command=command, state=state_value)
            allowed = command == CMD_NOTIFY_YES
            logger.info(
                "Callback: выбор уведомлений в регистрации (user_id={}, notifications_allowed={})",
                user_id,
                allowed,
            )
            await db.update_user(
                user_id,
                notifications_allowed=allowed,
                notifications_allowed_at=datetime.now(timezone.utc),
            )
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_IIKO_REGISTRATION)
            await edit_or_send_event_message(event, "⏳ Выполняю синхронизацию профиля с iiko...")
            await _run_iiko_sync(adapter, bot)
            return

        if command == CMD_RETRY_IIKO and in_state(RegistrationState.WAITING_FOR_IIKO_REGISTRATION):
            await event.send_empty_answer()
            mark_callback_matched("registration", event, command=command, state=state_value)
            logger.info("Callback: повторный запуск iiko-синхронизации (user_id={})", user_id)
            await _run_iiko_sync(adapter, bot)
            return

        mark_callback_skipped(
            "registration",
            event,
            reason="state_mismatch_or_unhandled",
            command=command,
            state=state_value,
        )
