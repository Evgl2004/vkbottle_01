"""Хендлеры главного меню и раздела поддержки.

Модуль отвечает за пользовательские разделы после регистрации:
1. Главное меню.
2. Отдел заботы (поддержка и тикеты).
3. Показ бонусного баланса.
4. Показ виртуальных карт и отправка QR-кодов карт в чат.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from vkbottle.bot import Bot, Message, MessageEvent
from vkbottle_types.events import GroupEventType

from app.database import db
from app.handlers.common import EventMessageAdapter, edit_or_send_event_message
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
from app.services.vk_qr import send_card_qr
from app.states.tickets import TicketState


async def show_main_menu(message: Message, user_name: str = "Гость") -> None:
    """Отправляет пользователю главное меню."""

    logger.debug("Показ главного меню (user_id={}, user_name='{}')", int(message.from_id), user_name)
    await message.answer(
        f"👋 Здравствуйте, {user_name}!\n"
        "Вы в главном меню. Выберите раздел:",
        keyboard=get_main_menu_keyboard(),
    )


async def show_support_menu(message: Message) -> None:
    """Отправляет меню раздела поддержки с учетом наличия тикетов."""

    user_id = int(message.from_id)
    count = await ticket_service.get_user_tickets_count(user_id)
    logger.debug("Показ меню поддержки (user_id={}, tickets_count={})", user_id, count)
    await message.answer(
        "🆘 Раздел «Отдел заботы».\nВыберите действие:",
        keyboard=get_support_keyboard(has_tickets=count > 0),
    )


async def _show_main_menu_event(event: MessageEvent) -> None:
    """Показывает/перерисовывает главное меню в callback-режиме."""

    user_id = int(event.user_id)
    user = await db.get_user(user_id)
    if not user:
        await edit_or_send_event_message(
            event,
            "❌ Профиль не найден. Введите /start для повторной инициализации.",
            keyboard=get_back_to_main_keyboard(),
        )
        return

    if user.is_legacy or not user.rules_accepted or not user.is_registered:
        await edit_or_send_event_message(
            event,
            "⚠️ Чтобы открыть главное меню, сначала завершите регистрацию через /start.",
            keyboard=get_back_to_main_keyboard(),
        )
        return

    await edit_or_send_event_message(
        event,
        f"👋 Здравствуйте, {user.first_name_input or 'Гость'}!\nВы в главном меню. Выберите раздел:",
        keyboard=get_main_menu_keyboard(),
    )


async def _show_support_menu_event(event: MessageEvent) -> None:
    """Показывает/перерисовывает меню поддержки в callback-режиме."""

    user_id = int(event.user_id)
    user = await db.get_user(user_id)
    if not user or user.is_legacy or not user.rules_accepted or not user.is_registered:
        await edit_or_send_event_message(
            event,
            "⚠️ Раздел поддержки доступен после завершения регистрации. Введите /start.",
            keyboard=get_back_to_main_keyboard(),
        )
        return

    count = await ticket_service.get_user_tickets_count(user_id)
    await edit_or_send_event_message(
        event,
        "🆘 Раздел «Отдел заботы».\nВыберите действие:",
        keyboard=get_support_keyboard(has_tickets=count > 0),
    )


async def _show_virtual_cards_for_actor(
    actor: Any,
    user_id: int,
    *,
    send_intro: bool = True,
) -> None:
    """Показывает виртуальные карты и отправляет QR-коды для `Message`/`MessageEvent`.

    `actor` должен поддерживать контракт:
    - `answer(...)`;
    - поля `from_id`, `peer_id`, `ctx_api`.
    """

    logger.debug("Запрошен раздел виртуальных карт (user_id={})", user_id)

    user = await db.get_user(user_id)
    if not user or not user.phone_number:
        logger.warning(
            "Невозможно показать виртуальные карты: у пользователя нет телефона (user_id={})",
            user_id,
        )
        await actor.answer(
            "❌ Телефон пользователя не найден. Пройдите регистрацию через /start.",
            keyboard=get_back_to_main_keyboard(),
        )
        return

    info = await iiko_service.get_customer_info(user.phone_number)
    if info is None:
        logger.debug(
            "Клиент не найден в iiko, запускаем регистрацию (user_id={})",
            user_id,
        )
        customer_id, msg = await iiko_service.register_customer(user)
        if not customer_id:
            logger.error(
                "Ошибка регистрации клиента в iiko при запросе карт (user_id={}): {}",
                user_id,
                msg,
            )
            await actor.answer(
                f"❌ Не удалось зарегистрировать клиента в iiko.\nПричина: {msg}",
                keyboard=get_back_to_main_keyboard(),
            )
            return
        info = {"customer_id": customer_id, "cards": []}

    cards = info.get("cards", []) or []
    logger.debug(
        "Получены данные карт из iiko (user_id={}, cards_count={})",
        user_id,
        len(cards),
    )

    if not cards:
        logger.debug("Карт нет, запускаем выпуск новой карты (user_id={})", user_id)
        ok, msg, card_number = await iiko_service.issue_card_for_customer(
            user.phone_number,
            info["customer_id"],
        )
        if not ok:
            logger.error(
                "Ошибка выпуска карты iiko (user_id={}): {}",
                user_id,
                msg,
            )
            await actor.answer(
                f"❌ Не удалось выпустить карту.\nПричина: {msg}",
                keyboard=get_back_to_main_keyboard(),
            )
            return
        cards = [{"number": card_number}] if card_number else []
        logger.debug(
            "Выпуск карты завершён (user_id={}, cards_count_after_issue={})",
            user_id,
            len(cards),
        )

    if not cards:
        logger.warning("После выпуска карта не найдена (user_id={})", user_id)
        await actor.answer(
            "⚠️ Карты не найдены. Обратитесь к администратору.",
            keyboard=get_back_to_main_keyboard(),
        )
        return

    if send_intro:
        await actor.answer(
            "🪪 Отправляю QR-коды ваших виртуальных карт.",
            keyboard=get_back_to_main_keyboard(),
        )

    sent_qr_count = 0
    for idx, card in enumerate(cards, start=1):
        card_number = (card.get("number") or "").strip()
        if not card_number:
            logger.debug(
                "Пропуск карты без номера при отправке QR (user_id={}, idx={})",
                user_id,
                idx,
            )
            continue

        if await send_card_qr(actor, card_number, title=f"QR-код карты №{idx}"):
            sent_qr_count += 1

    logger.debug(
        "Отправка QR завершена (user_id={}, sent_qr_count={}, cards_count={})",
        user_id,
        sent_qr_count,
        len(cards),
    )
    if sent_qr_count == 0:
        await actor.answer(
            "❌ Не удалось сформировать QR-код карты. Попробуйте позже или обратитесь в поддержку.",
            keyboard=get_back_to_main_keyboard(),
        )


def register_menu_handlers(bot: Bot) -> None:
    """Регистрирует набор хендлеров главного меню."""

    @bot.on.private_message(payload_contains={"cmd": CMD_MAIN_MENU})
    @bot.on.private_message(payload_contains={"cmd": CMD_BACK_TO_MAIN})
    @bot.on.private_message(text=["menu", "меню", "главное меню"])
    async def open_main_menu(message: Message) -> None:
        """Открывает главное меню по payload-кнопке или текстовой команде."""

        user_id = int(message.from_id)
        logger.debug("Запрошено открытие главного меню (user_id={})", user_id)
        user = await db.get_user(user_id)
        if not user:
            logger.warning("Невозможно открыть меню: профиль не найден (user_id={})", user_id)
            await message.answer("❌ Профиль не найден. Введите /start для повторной инициализации.")
            return

        if user.is_legacy or not user.rules_accepted or not user.is_registered:
            logger.info(
                "Отказ в открытии меню: регистрация не завершена (user_id={}, is_legacy={}, rules_accepted={}, is_registered={})",
                user_id,
                user.is_legacy,
                user.rules_accepted,
                user.is_registered,
            )
            await message.answer(
                "⚠️ Чтобы открыть главное меню, сначала завершите регистрацию через /start."
            )
            return

        user_name = user.first_name_input or "Гость"
        await bot.state_dispenser.delete(user_id)
        await show_main_menu(message, user_name=user_name)

    @bot.on.private_message(payload_contains={"cmd": CMD_SUPPORT})
    @bot.on.private_message(payload_contains={"cmd": CMD_BACK_TO_SUPPORT})
    async def open_support_menu(message: Message) -> None:
        """Открывает раздел поддержки."""

        user_id = int(message.from_id)
        logger.debug("Запрошено открытие раздела поддержки (user_id={})", user_id)
        user = await db.get_user(user_id)
        if not user or user.is_legacy or not user.rules_accepted or not user.is_registered:
            logger.info("Отказ в открытии поддержки: регистрация не завершена (user_id={})", user_id)
            await message.answer(
                "⚠️ Раздел поддержки доступен после завершения регистрации. Введите /start."
            )
            return

        await bot.state_dispenser.delete(user_id)
        await show_support_menu(message)

    @bot.on.private_message(payload_contains={"cmd": CMD_BALANCE})
    async def show_balance(message: Message) -> None:
        """Показывает баланс бонусов пользователя по данным iiko."""

        user_id = int(message.from_id)
        user = await db.get_user(user_id)
        if not user or not user.phone_number:
            logger.warning(
                "Запрос баланса отклонён: отсутствует телефон пользователя (user_id={})",
                user_id,
            )
            await message.answer(
                "❌ Номер телефона не найден. Пожалуйста, пройдите регистрацию заново через команду /start.",
                keyboard=get_back_to_main_keyboard(),
            )
            return

        logger.debug("Запрошен бонусный баланс (user_id={})", user_id)
        info = await iiko_service.get_customer_info(user.phone_number)
        if not info:
            logger.error("Не удалось получить бонусный баланс из iiko (user_id={})", user_id)
            await message.answer(
                "❌ Не удалось получить баланс бонусов. Попробуйте позже.",
                keyboard=get_back_to_main_keyboard(),
            )
            return

        balance = info.get("balance", 0)
        logger.info("Показан бонусный баланс (user_id={}, balance={})", user_id, balance)
        await message.answer(
            "\n".join(
                [
                    "💰 Ваш бонусный баланс:",
                    f"• Доступно бонусов: {balance}",
                    f"• Программа: {info.get('program_name') or 'не указана'}",
                ]
            ),
            keyboard=get_back_to_main_keyboard(),
        )

    @bot.on.private_message(payload_contains={"cmd": CMD_VIRTUAL_CARD})
    async def show_virtual_cards(message: Message) -> None:
        """Показывает карты пользователя и отправляет QR-коды карт.

        Поведение:
        1. Пытаемся получить клиента/карты из iiko.
        2. Если клиента нет — регистрируем.
        3. Если карт нет — выпускаем новую.
        4. Отправляем список карт текстом.
        5. Отправляем QR-картинку для каждой найденной карты.
        """

        await _show_virtual_cards_for_actor(message, int(message.from_id), send_intro=True)

    @bot.on.private_message(payload_contains={"cmd": CMD_VACANCIES})
    async def show_vacancies(message: Message) -> None:
        """Показывает краткую информацию о вакансиях."""

        logger.debug("Открыт раздел вакансий (user_id={})", int(message.from_id))
        await message.answer(
            "\n".join(
                [
                    "💼 Вакансии:",
                    "Мы ищем ответственных и энергичных сотрудников.",
                    "Подробности: https://team.sobolevalliance.su/vacancy",
                ]
            ),
            keyboard=get_back_to_main_keyboard(),
        )

    @bot.on.private_message(payload_contains={"cmd": CMD_SUPPORT_FEEDBACK})
    async def show_feedback(message: Message) -> None:
        """Отправляет ссылку на форму обратной связи."""

        logger.debug("Открыт раздел обратной связи (user_id={})", int(message.from_id))
        await message.answer(
            "✍️ Оставить отзыв можно по кнопке ниже.",
            keyboard=get_feedback_link_keyboard(),
        )

    @bot.on.private_message(payload_contains={"cmd": CMD_SUPPORT_CONTACTS})
    async def show_contacts(message: Message) -> None:
        """Показывает контактные данные компании."""

        logger.debug("Открыт раздел контактов (user_id={})", int(message.from_id))
        await message.answer(
            "\n".join(
                [
                    "📇 Контакты:",
                    "• Почта: info@sobolev.rest",
                    "• Сайт: https://sobolevalliance.su",
                    "• Соцсети: @sobolevalliance",
                ]
            ),
            keyboard=get_back_to_support_keyboard(),
        )

    @bot.on.private_message(payload_contains={"cmd": CMD_SUPPORT_QUESTION})
    async def start_question_flow(message: Message) -> None:
        """Запускает создание нового тикета из раздела поддержки."""

        user_id = int(message.from_id)
        logger.info("Переход в режим создания тикета (user_id={})", user_id)
        await bot.state_dispenser.set(user_id, TicketState.WAITING_FOR_QUESTION)
        await message.answer(
            "❓ Опишите ваш вопрос одним сообщением.\n"
            "Модератор увидит обращение и ответит в ближайшее время.",
            keyboard=get_back_to_support_keyboard(),
        )

    @bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent, blocking=False)
    async def menu_callback_router(event: MessageEvent) -> None:
        """Обрабатывает callback-кнопки меню через `message_event`.

        Этот роутер нужен для UX в стиле Telegram:
        - пользователь нажимает inline callback;
        - бот перерисовывает текущее сообщение меню вместо отправки новой реплики.
        """

        payload: dict[str, Any] = event.get_payload_json() or {}
        command = payload.get("cmd")
        if command not in {
            CMD_MAIN_MENU,
            CMD_BACK_TO_MAIN,
            CMD_SUPPORT,
            CMD_BACK_TO_SUPPORT,
            CMD_BALANCE,
            CMD_VIRTUAL_CARD,
            CMD_VACANCIES,
            CMD_SUPPORT_FEEDBACK,
            CMD_SUPPORT_CONTACTS,
            CMD_SUPPORT_QUESTION,
        }:
            return

        # Подтверждаем callback, чтобы на клиенте не висело состояние ожидания.
        await event.send_empty_answer()
        logger.debug(
            "Обработка menu callback (user_id={}, peer_id={}, cmd={})",
            int(event.user_id),
            int(event.peer_id),
            command,
        )

        if command in {CMD_MAIN_MENU, CMD_BACK_TO_MAIN}:
            await bot.state_dispenser.delete(int(event.user_id))
            await _show_main_menu_event(event)
            return

        if command in {CMD_SUPPORT, CMD_BACK_TO_SUPPORT}:
            await bot.state_dispenser.delete(int(event.user_id))
            await _show_support_menu_event(event)
            return

        if command == CMD_BALANCE:
            user = await db.get_user(int(event.user_id))
            if not user or not user.phone_number:
                await edit_or_send_event_message(
                    event,
                    "❌ Номер телефона не найден. Пожалуйста, пройдите регистрацию заново через /start.",
                    keyboard=get_back_to_main_keyboard(),
                )
                return

            info = await iiko_service.get_customer_info(user.phone_number)
            if not info:
                await edit_or_send_event_message(
                    event,
                    "❌ Не удалось получить баланс бонусов. Попробуйте позже.",
                    keyboard=get_back_to_main_keyboard(),
                )
                return

            balance = info.get("balance", 0)
            logger.info("Показан бонусный баланс через callback (user_id={}, balance={})", int(event.user_id), balance)
            await edit_or_send_event_message(
                event,
                "\n".join(
                    [
                        "💰 Ваш бонусный баланс:",
                        f"• Доступно бонусов: {balance}",
                        f"• Программа: {info.get('program_name') or 'не указана'}",
                    ]
                ),
                keyboard=get_back_to_main_keyboard(),
            )
            return

        if command == CMD_VIRTUAL_CARD:
            await edit_or_send_event_message(
                event,
                "🪪 Загружаю виртуальные карты и формирую QR-коды...",
                keyboard=get_back_to_main_keyboard(),
            )
            await _show_virtual_cards_for_actor(
                EventMessageAdapter(event),
                int(event.user_id),
                send_intro=False,
            )
            return

        if command == CMD_VACANCIES:
            await edit_or_send_event_message(
                event,
                "\n".join(
                    [
                        "💼 Вакансии:",
                        "Мы ищем ответственных и энергичных сотрудников.",
                        "Подробности: https://team.sobolevalliance.su/vacancy",
                    ]
                ),
                keyboard=get_back_to_main_keyboard(),
            )
            return

        if command == CMD_SUPPORT_FEEDBACK:
            await edit_or_send_event_message(
                event,
                "✍️ Оставить отзыв можно по кнопке ниже.",
                keyboard=get_feedback_link_keyboard(),
            )
            return

        if command == CMD_SUPPORT_CONTACTS:
            await edit_or_send_event_message(
                event,
                "\n".join(
                    [
                        "📇 Контакты:",
                        "• Почта: info@sobolev.rest",
                        "• Сайт: https://sobolevalliance.su",
                        "• Соцсети: @sobolevalliance",
                    ]
                ),
                keyboard=get_back_to_support_keyboard(),
            )
            return

        if command == CMD_SUPPORT_QUESTION:
            await bot.state_dispenser.set(int(event.user_id), TicketState.WAITING_FOR_QUESTION)
            await edit_or_send_event_message(
                event,
                "❓ Опишите ваш вопрос одним сообщением.\n"
                "Модератор увидит обращение и ответит в ближайшее время.",
                keyboard=get_back_to_support_keyboard(),
            )
