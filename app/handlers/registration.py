"""Хендлеры сценария регистрации нового пользователя."""

from __future__ import annotations

from datetime import datetime, timezone

from vkbottle.bot import Bot, Message

from app.database import db
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


async def _show_review(message: Message) -> None:
    """Показывает пользователю экран проверки введённой анкеты."""
    text = await get_profile_review_text(int(message.from_id))
    await message.answer(text, keyboard=get_review_keyboard())


async def _run_iiko_sync(message: Message, bot: Bot) -> None:
    """Запускает синхронизацию пользователя с iiko и завершает регистрацию."""

    user_id = int(message.from_id)
    user = await db.get_user(user_id)
    if not user:
        await bot.state_dispenser.delete(user_id)
        await message.answer("Не удалось загрузить профиль пользователя. Введите /start.")
        return

    result = await sync_user_with_iiko(user)
    if not result.success:
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_IIKO_REGISTRATION)
        await message.answer(
            f"Ошибка синхронизации с iiko:\n{result.message}",
            keyboard=get_retry_iiko_keyboard(),
        )
        return

    card_text = (
        "\n".join(f"- {number}" for number in result.card_numbers)
        if result.card_numbers
        else "Карты не найдены."
    )
    await message.answer(
        "\n".join(
            [
                "Регистрация успешно завершена.",
                result.message,
                "Ваши карты:",
                card_text,
            ]
        )
    )
    await bot.state_dispenser.delete(user_id)
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

        await db.update_user(
            int(message.from_id),
            rules_accepted=True,
            rules_accepted_at=datetime.now(timezone.utc),
        )
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_CONTACT)
        await message.answer(
            "Спасибо. Теперь введите номер телефона в формате +79991234567."
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

        command = message.get_payload_json().get("cmd")
        gender = "male" if command == CMD_GENDER_MALE else "female"

        await db.update_user(int(message.from_id), gender=gender)
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_BIRTH_DATE)
        await message.answer("Введите дату рождения в формате ДД.ММ.ГГГГ.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_CONTACT)
    async def process_contact(message: Message) -> None:
        """Обрабатывает шаг ввода телефона.

        В VK отсутствует универсальная кнопка безопасной передачи контакта,
        поэтому на этом шаге используется ручной ввод номера.
        """

        if not await confirm_text(message, "Введите номер телефона текстом (пример: +79991234567)."):
            return

        text = message.text.strip()
        valid, error = await validate_phone(text)
        if not valid:
            await message.answer(error)
            return

        normalized = await normalize_phone(text)
        await db.update_user(int(message.from_id), phone_number=normalized)
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_FIRST_NAME)
        await message.answer("Телефон сохранён. Теперь введите ваше имя.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_FIRST_NAME)
    async def process_first_name(message: Message) -> None:
        """Проверяет и сохраняет имя пользователя."""

        if not await confirm_text(message, "Введите имя текстом."):
            return

        text = message.text.strip()
        valid, error = await validate_first_name(text)
        if not valid:
            await message.answer(error)
            return

        await db.update_user(int(message.from_id), first_name_input=await clean_name(text))
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_LAST_NAME)
        await message.answer("Имя сохранено. Теперь введите фамилию.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_LAST_NAME)
    async def process_last_name(message: Message) -> None:
        """Проверяет и сохраняет фамилию пользователя."""

        if not await confirm_text(message, "Введите фамилию текстом."):
            return

        text = message.text.strip()
        valid, error = await validate_last_name(text)
        if not valid:
            await message.answer(error)
            return

        await db.update_user(int(message.from_id), last_name_input=await clean_name(text))
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_GENDER)
        await message.answer("Фамилия сохранена. Выберите пол.", keyboard=get_gender_keyboard())

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_BIRTH_DATE)
    async def process_birth_date(message: Message) -> None:
        """Проверяет дату рождения и запрашивает email."""

        if not await confirm_text(message, "Введите дату рождения текстом в формате ДД.ММ.ГГГГ."):
            return

        text = message.text.strip()
        valid, error = await validate_birth_date(text)
        if not valid:
            await message.answer(error)
            return

        birth_date = datetime.strptime(text, "%d.%m.%Y").date()
        await db.update_user(int(message.from_id), birth_date=birth_date)
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_EMAIL)
        await message.answer("Дата рождения сохранена. Теперь введите email.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EMAIL)
    async def process_email(message: Message) -> None:
        """Проверяет email и переводит пользователя на экран ревью."""

        if not await confirm_text(message, "Введите email текстом."):
            return

        text = message.text.strip()
        valid, error = await validate_email(text)
        if not valid:
            await message.answer(error)
            return

        await db.update_user(int(message.from_id), email=text)
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_REVIEW)
        await _show_review(message)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_REVIEW_OK},
        state=RegistrationState.WAITING_FOR_REVIEW,
    )
    async def review_ok(message: Message) -> None:
        """Обрабатывает подтверждение корректности анкеты."""
        await bot.state_dispenser.set(
            int(message.from_id),
            RegistrationState.WAITING_FOR_NOTIFICATIONS_CONSENT,
        )
        await message.answer(
            "Ознакомьтесь с условиями уведомлений и выберите вариант:",
            keyboard=get_notifications_keyboard(),
        )

    @bot.on.private_message(
        payload_contains={"cmd": CMD_REVIEW_EDIT},
        state=RegistrationState.WAITING_FOR_REVIEW,
    )
    async def review_edit(message: Message) -> None:
        """Открывает выбор поля для редактирования анкеты."""
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_EDIT_CHOICE)
        await message.answer("Выберите поле для редактирования:", keyboard=get_edit_choice_keyboard())

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_CHOICE)
    async def process_edit_choice(message: Message) -> None:
        """Обрабатывает выбор редактируемого поля из клавиатуры."""

        payload = message.get_payload_json()
        command = payload.get("cmd") if isinstance(payload, dict) else None
        user_id = int(message.from_id)

        if command == CMD_EDIT_CANCEL:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_REVIEW)
            await _show_review(message)
            return

        if command == CMD_EDIT_FIRST_NAME:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_FIRST_NAME)
            await message.answer("Введите новое имя.")
            return
        if command == CMD_EDIT_LAST_NAME:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_LAST_NAME)
            await message.answer("Введите новую фамилию.")
            return
        if command == CMD_EDIT_GENDER:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_GENDER)
            await message.answer("Выберите пол.", keyboard=get_gender_keyboard())
            return
        if command == CMD_EDIT_BIRTH_DATE:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_BIRTH_DATE)
            await message.answer("Введите новую дату рождения в формате ДД.ММ.ГГГГ.")
            return
        if command == CMD_EDIT_EMAIL:
            await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_EDIT_EMAIL)
            await message.answer("Введите новый email.")
            return

        await message.answer("Не удалось определить выбранное поле. Выберите действие снова.")

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_FIRST_NAME)
    async def edit_first_name(message: Message) -> None:
        """Редактирует поле имени."""
        if not await confirm_text(message, "Введите имя текстом."):
            return
        valid, error = await validate_first_name(message.text.strip())
        if not valid:
            await message.answer(error)
            return
        await db.update_user(int(message.from_id), first_name_input=await clean_name(message.text.strip()))
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_REVIEW)
        await _show_review(message)

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_LAST_NAME)
    async def edit_last_name(message: Message) -> None:
        """Редактирует поле фамилии."""
        if not await confirm_text(message, "Введите фамилию текстом."):
            return
        valid, error = await validate_last_name(message.text.strip())
        if not valid:
            await message.answer(error)
            return
        await db.update_user(int(message.from_id), last_name_input=await clean_name(message.text.strip()))
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_REVIEW)
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

        cmd = message.get_payload_json().get("cmd")
        gender = "male" if cmd == CMD_GENDER_MALE else "female"
        await db.update_user(int(message.from_id), gender=gender)
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_REVIEW)
        await _show_review(message)

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_BIRTH_DATE)
    async def edit_birth_date(message: Message) -> None:
        """Редактирует поле даты рождения."""
        if not await confirm_text(message, "Введите дату рождения текстом."):
            return
        text = message.text.strip()
        valid, error = await validate_birth_date(text)
        if not valid:
            await message.answer(error)
            return
        await db.update_user(int(message.from_id), birth_date=datetime.strptime(text, "%d.%m.%Y").date())
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_REVIEW)
        await _show_review(message)

    @bot.on.private_message(state=RegistrationState.WAITING_FOR_EDIT_EMAIL)
    async def edit_email(message: Message) -> None:
        """Редактирует поле email."""
        if not await confirm_text(message, "Введите email текстом."):
            return
        text = message.text.strip()
        valid, error = await validate_email(text)
        if not valid:
            await message.answer(error)
            return
        await db.update_user(int(message.from_id), email=text)
        await bot.state_dispenser.set(int(message.from_id), RegistrationState.WAITING_FOR_REVIEW)
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

        command = message.get_payload_json().get("cmd")
        allowed = command == CMD_NOTIFY_YES

        await db.update_user(
            int(message.from_id),
            notifications_allowed=allowed,
            notifications_allowed_at=datetime.now(timezone.utc),
        )

        await bot.state_dispenser.set(
            int(message.from_id),
            RegistrationState.WAITING_FOR_IIKO_REGISTRATION,
        )
        await _run_iiko_sync(message, bot)

    @bot.on.private_message(
        payload_contains={"cmd": CMD_RETRY_IIKO},
        state=RegistrationState.WAITING_FOR_IIKO_REGISTRATION,
    )
    async def retry_iiko_sync(message: Message) -> None:
        """Повторно запускает iiko-синхронизацию после предыдущей ошибки."""
        await _run_iiko_sync(message, bot)
