"""Хендлеры главного меню и раздела поддержки."""

from __future__ import annotations

from vkbottle.bot import Bot, Message

from app.database import db
from app.keyboards.menu import (
    get_back_to_main_keyboard,
    get_back_to_support_keyboard,
    get_feedback_link_keyboard,
    get_main_menu_keyboard,
    get_support_keyboard,
)
from app.keyboards.payloads import (
    CMD_BACK_TO_MAIN,
    CMD_BACK_TO_SUPPORT,
    CMD_BALANCE,
    CMD_MAIN_MENU,
    CMD_SUPPORT,
    CMD_SUPPORT_CONTACTS,
    CMD_SUPPORT_FEEDBACK,
    CMD_SUPPORT_QUESTION,
    CMD_VACANCIES,
    CMD_VIRTUAL_CARD,
)
from app.services import iiko_service
from app.services.tickets import ticket_service
from app.states.tickets import TicketState


async def show_main_menu(message: Message, user_name: str = "Гость") -> None:
    """Отправляет пользователю главное меню.

    Параметр `user_name` вынесен отдельно, чтобы:
    - использовать имя из анкеты (приоритетно);
    - fallback на дефолтный вариант при отсутствии данных.
    """

    await message.answer(
        f"Здравствуйте, {user_name}.\nВы находитесь в главном меню. Выберите раздел:",
        keyboard=get_main_menu_keyboard(),
    )


async def show_support_menu(message: Message) -> None:
    """Отправляет меню раздела поддержки с учетом наличия тикетов."""

    user_id = int(message.from_id)
    count = await ticket_service.get_user_tickets_count(user_id)
    await message.answer(
        "Раздел «Отдел заботы».\nВыберите действие:",
        keyboard=get_support_keyboard(has_tickets=count > 0),
    )


def register_menu_handlers(bot: Bot) -> None:
    """Регистрирует набор хендлеров главного меню."""

    @bot.on.private_message(payload_contains={"cmd": CMD_MAIN_MENU})
    @bot.on.private_message(payload_contains={"cmd": CMD_BACK_TO_MAIN})
    @bot.on.private_message(text=["menu", "меню", "главное меню"])
    async def open_main_menu(message: Message) -> None:
        """Открывает главное меню по payload-кнопке или текстовой команде."""
        user = await db.get_user(int(message.from_id))
        if not user:
            await message.answer("Профиль не найден. Введите /start для повторной инициализации.")
            return
        if user.is_legacy or not user.rules_accepted or not user.is_registered:
            await message.answer(
                "Чтобы открыть главное меню, сначала завершите регистрацию через /start."
            )
            return

        user_name = (user.first_name_input if user else None) or "Гость"
        await bot.state_dispenser.delete(int(message.from_id))
        await show_main_menu(message, user_name=user_name)

    @bot.on.private_message(payload_contains={"cmd": CMD_SUPPORT})
    @bot.on.private_message(payload_contains={"cmd": CMD_BACK_TO_SUPPORT})
    async def open_support_menu(message: Message) -> None:
        """Открывает раздел поддержки."""
        user = await db.get_user(int(message.from_id))
        if not user or user.is_legacy or not user.rules_accepted or not user.is_registered:
            await message.answer(
                "Раздел поддержки доступен после завершения регистрации. Введите /start."
            )
            return

        await bot.state_dispenser.delete(int(message.from_id))
        await show_support_menu(message)

    @bot.on.private_message(payload_contains={"cmd": CMD_BALANCE})
    async def show_balance(message: Message) -> None:
        """Показывает баланс бонусов пользователя по данным iiko."""

        user = await db.get_user(int(message.from_id))
        if not user or not user.phone_number:
            await message.answer(
                "Номер телефона не найден. Пожалуйста, пройдите регистрацию заново через команду /start.",
                keyboard=get_back_to_main_keyboard(),
            )
            return

        info = await iiko_service.get_customer_info(user.phone_number)
        if not info:
            await message.answer(
                "Не удалось получить баланс бонусов. Попробуйте позже.",
                keyboard=get_back_to_main_keyboard(),
            )
            return

        balance = info.get("balance", 0)
        await message.answer(
            "\n".join(
                [
                    "Ваш бонусный баланс:",
                    f"- Доступно бонусов: {balance}",
                    f"- Программа: {info.get('program_name') or 'не указана'}",
                ]
            ),
            keyboard=get_back_to_main_keyboard(),
        )

    @bot.on.private_message(payload_contains={"cmd": CMD_VIRTUAL_CARD})
    async def show_virtual_cards(message: Message) -> None:
        """Показывает список карт пользователя.

        Если карт нет, запускается выпуск новой карты через iiko.
        """

        user = await db.get_user(int(message.from_id))
        if not user or not user.phone_number:
            await message.answer(
                "Телефон пользователя не найден. Пройдите регистрацию через /start.",
                keyboard=get_back_to_main_keyboard(),
            )
            return

        info = await iiko_service.get_customer_info(user.phone_number)
        if info is None:
            customer_id, msg = await iiko_service.register_customer(user)
            if not customer_id:
                await message.answer(
                    f"Не удалось зарегистрировать клиента в iiko.\nПричина: {msg}",
                    keyboard=get_back_to_main_keyboard(),
                )
                return
            info = {"customer_id": customer_id, "cards": []}

        cards = info.get("cards", []) or []
        if not cards:
            ok, msg, card_number = await iiko_service.issue_card_for_customer(
                user.phone_number,
                info["customer_id"],
            )
            if not ok:
                await message.answer(
                    f"Не удалось выпустить карту.\nПричина: {msg}",
                    keyboard=get_back_to_main_keyboard(),
                )
                return
            cards = [{"number": card_number}] if card_number else []

        if not cards:
            await message.answer(
                "Карты не найдены. Обратитесь к администратору.",
                keyboard=get_back_to_main_keyboard(),
            )
            return

        card_lines = [f"- {card.get('number', 'неизвестный номер')}" for card in cards]
        await message.answer(
            "Ваши виртуальные карты:\n" + "\n".join(card_lines),
            keyboard=get_back_to_main_keyboard(),
        )

    @bot.on.private_message(payload_contains={"cmd": CMD_VACANCIES})
    async def show_vacancies(message: Message) -> None:
        """Показывает краткую информацию о вакансиях."""
        await message.answer(
            "\n".join(
                [
                    "Вакансии:",
                    "Мы ищем ответственных и энергичных сотрудников.",
                    "Подробности по ссылке: https://team.sobolevalliance.su/vacancy",
                ]
            ),
            keyboard=get_back_to_main_keyboard(),
        )

    @bot.on.private_message(payload_contains={"cmd": CMD_SUPPORT_FEEDBACK})
    async def show_feedback(message: Message) -> None:
        """Отправляет ссылку на форму обратной связи."""
        await message.answer(
            "Оставить отзыв можно по кнопке ниже.",
            keyboard=get_feedback_link_keyboard(),
        )

    @bot.on.private_message(payload_contains={"cmd": CMD_SUPPORT_CONTACTS})
    async def show_contacts(message: Message) -> None:
        """Показывает контактные данные компании."""
        await message.answer(
            "\n".join(
                [
                    "Контакты:",
                    "Почта: info@sobolev.rest",
                    "Сайт: https://sobolevalliance.su",
                    "Соцсети: @sobolevalliance",
                ]
            ),
            keyboard=get_back_to_support_keyboard(),
        )

    @bot.on.private_message(payload_contains={"cmd": CMD_SUPPORT_QUESTION})
    async def start_question_flow(message: Message) -> None:
        """Запускает создание нового тикета из раздела поддержки."""

        await bot.state_dispenser.set(int(message.from_id), TicketState.WAITING_FOR_QUESTION)
        await message.answer(
            "Опишите ваш вопрос одним сообщением.\n"
            "Модератор увидит обращение и ответит в ближайшее время.",
            keyboard=get_back_to_support_keyboard(),
        )
