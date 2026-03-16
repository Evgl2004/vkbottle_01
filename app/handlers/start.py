"""Хендлеры входа в бота и первичной маршрутизации пользователя."""

from __future__ import annotations

from loguru import logger
from vkbottle.bot import Bot, Message

from app.database import db
from app.handlers.legacy import start_legacy_upgrade
from app.handlers.menu import show_main_menu
from app.keyboards.registration import get_rules_keyboard
from app.states.registration import RegistrationState

_START_TEXT_VARIANTS = {"/start", "start", "начать"}


async def _handle_start_logic(message: Message, bot: Bot) -> None:
    """Единая логика обработки команды `/start`.

    Алгоритм:
    1. Гарантирует наличие пользователя в БД.
    2. Восстанавливает актуальную ветку сценария:
       - legacy-обновление;
       - регистрация;
       - готовое главное меню.
    """

    user_id = int(message.from_id)
    logger.info("Обработка команды start (user_id={}, peer_id={})", user_id, message.peer_id)

    # Базовый апсерт по ID пользователя.
    await db.add_or_update_user(user_id=user_id)
    logger.debug("Пользователь апсерчен в БД (user_id={})", user_id)
    user = await db.get_user(user_id)
    if not user:
        logger.error("Пользователь не найден после апсерта (user_id={})", user_id)
        await message.answer("❌ Не удалось инициализировать профиль пользователя.")
        return

    # Ветка legacy-обновления.
    if user.is_registered and user.is_legacy:
        logger.info("Запуск legacy-сценария из start (user_id={})", user_id)
        await start_legacy_upgrade(message, bot, user)
        return

    # Ветка нового пользователя: запрос согласия.
    if not user.rules_accepted:
        logger.debug("Переход в WAITING_FOR_RULES_CONSENT (user_id={})", user_id)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_RULES_CONSENT)
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Перед началом работы подтвердите согласие с правилами и обработкой персональных данных.",
            keyboard=get_rules_keyboard(),
        )
        return

    # Ветка неполной регистрации.
    if not user.is_registered:
        logger.debug("Переход в WAITING_FOR_CONTACT (user_id={})", user_id)
        await bot.state_dispenser.set(user_id, RegistrationState.WAITING_FOR_CONTACT)
        await message.answer("📱 Введите номер телефона в формате +79991234567.")
        return

    # Пользователь уже зарегистрирован.
    await bot.state_dispenser.delete(user_id)
    logger.debug("Состояние пользователя очищено, показываем меню (user_id={})", user_id)
    await show_main_menu(message, user_name=user.first_name_input or "Гость")


def register_start_handlers(bot: Bot) -> None:
    """Регистрирует хендлеры команды запуска и вспомогательной помощи."""

    @bot.on.private_message(text=["/start", "start", "Start", "начать", "Начать"])
    async def start_handler(message: Message) -> None:
        """Точка входа пользователя в бота."""
        await _handle_start_logic(message, bot)

    @bot.on.private_message(text=["/help", "help", "помощь", "Помощь"])
    async def help_handler(message: Message) -> None:
        """Краткая справка по доступным действиям."""
        logger.debug("Запрошена справка /help (user_id={})", int(message.from_id))
        await message.answer(
            "\n".join(
                [
                    "🧭 Команды бота:",
                    "• /start — начать работу и открыть маршрут регистрации/меню",
                    "• /help — показать эту справку",
                    "• /mod — открыть панель модератора (если есть права)",
                ]
            )
        )

    @bot.on.private_message(blocking=False)
    async def first_contact_autostart_handler(message: Message) -> None:
        """Автоматически запускает онбординг при первом некомандном сообщении.

        Проблема, которую закрывает обработчик:
        - в части VK-клиентов пользователь не всегда видит кнопку «Начать»;
        - в итоге создаётся «тихий» первый экран без явной точки входа.

        Решение:
        1. Если пользователь ещё не зарегистрирован и у него нет активного FSM-состояния,
           запускаем сценарий `/start` автоматически.
        2. Перед автозапуском даём короткую подсказку, что также работают
           команды `/start` и слово «Начать».

        Защитные условия:
        - не вмешиваемся в активные сценарии (когда состояние уже выставлено);
        - не перехватываем другие slash-команды (`/mod`, `/help` и т.д.);
        - не дублируем поведение явной команды `/start`.
        """

        user_id = int(message.from_id)
        text = (message.text or "").strip()
        normalized_text = text.lower()
        payload = message.get_payload_json() or {}

        if normalized_text in _START_TEXT_VARIANTS or payload.get("command") == "start":
            return
        if normalized_text.startswith("/"):
            return

        state_peer = await bot.state_dispenser.get(user_id)
        if state_peer:
            return

        user = await db.get_user(user_id)
        if user and user.is_registered and user.rules_accepted and not user.is_legacy:
            return

        logger.info(
            "Автозапуск start-сценария по первому контакту (user_id={}, peer_id={}, text='{}')",
            user_id,
            message.peer_id,
            text,
        )
        await message.answer(
            "👋 Похоже, кнопка «Начать» недоступна в текущем клиенте VK.\n"
            "Запускаю регистрацию автоматически. Также можно использовать /start или «Начать»."
        )
        await _handle_start_logic(message, bot)
