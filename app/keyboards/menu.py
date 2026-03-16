"""Клавиатуры главного меню и раздела поддержки."""

from __future__ import annotations

from vkbottle import Callback, Keyboard, KeyboardButtonColor, OpenLink, Text

from app.keyboards.payloads import (
    CMD_BACK_TO_MAIN,
    CMD_BACK_TO_SUPPORT,
    CMD_BALANCE,
    CMD_MAIN_MENU,
    CMD_MY_TICKETS,
    CMD_SUPPORT,
    CMD_SUPPORT_CONTACTS,
    CMD_SUPPORT_FEEDBACK,
    CMD_SUPPORT_QUESTION,
    CMD_VACANCIES,
    CMD_VIRTUAL_CARD,
)


def get_main_menu_keyboard() -> str:
    """Основная клавиатура навигации по разделам бота."""

    keyboard = Keyboard(one_time=False, inline=True)
    keyboard.add(Callback("💰 Мой баланс", payload={"cmd": CMD_BALANCE}), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(
        Text("🪪 Виртуальная карта", payload={"cmd": CMD_VIRTUAL_CARD}),
        color=KeyboardButtonColor.PRIMARY,
    )
    keyboard.row()
    keyboard.add(Callback("🆘 Отдел заботы", payload={"cmd": CMD_SUPPORT}), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Callback("💼 Вакансии", payload={"cmd": CMD_VACANCIES}), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def get_support_keyboard(has_tickets: bool) -> str:
    """Клавиатура раздела поддержки.

    Параметр:
    - `has_tickets`: если `True`, добавляется кнопка «Мои обращения».
    """

    keyboard = Keyboard(one_time=False, inline=True)
    keyboard.add(
        Callback("✍️ Оставить отзыв", payload={"cmd": CMD_SUPPORT_FEEDBACK}),
        color=KeyboardButtonColor.SECONDARY,
    )
    keyboard.row()
    keyboard.add(
        Callback("❓ Мне только спросить", payload={"cmd": CMD_SUPPORT_QUESTION}),
        color=KeyboardButtonColor.PRIMARY,
    )
    if has_tickets:
        keyboard.row()
        keyboard.add(
            Text("📋 Мои обращения", payload={"cmd": CMD_MY_TICKETS}),
            color=KeyboardButtonColor.PRIMARY,
        )
    keyboard.row()
    keyboard.add(
        Callback("📇 Контакты", payload={"cmd": CMD_SUPPORT_CONTACTS}),
        color=KeyboardButtonColor.SECONDARY,
    )
    keyboard.row()
    keyboard.add(
        Callback("🔙 В главное меню", payload={"cmd": CMD_BACK_TO_MAIN}),
        color=KeyboardButtonColor.NEGATIVE,
    )
    return keyboard.get_json()


def get_back_to_main_keyboard() -> str:
    """Клавиатура с одной кнопкой возврата в главное меню."""

    keyboard = Keyboard(inline=True)
    keyboard.add(
        Callback("🔙 В главное меню", payload={"cmd": CMD_MAIN_MENU}),
        color=KeyboardButtonColor.PRIMARY,
    )
    return keyboard.get_json()


def get_back_to_support_keyboard() -> str:
    """Клавиатура с кнопкой возврата в раздел поддержки."""

    keyboard = Keyboard(inline=True)
    keyboard.add(
        Callback("🔙 В отдел заботы", payload={"cmd": CMD_BACK_TO_SUPPORT}),
        color=KeyboardButtonColor.PRIMARY,
    )
    return keyboard.get_json()


def get_feedback_link_keyboard() -> str:
    """Клавиатура со ссылкой на форму обратной связи и кнопкой назад."""

    keyboard = Keyboard(inline=True)
    keyboard.add(OpenLink("https://example.com/feedback", "📝 Открыть форму обратной связи"))
    keyboard.row()
    keyboard.add(
        Callback("🔙 В отдел заботы", payload={"cmd": CMD_BACK_TO_SUPPORT}),
        color=KeyboardButtonColor.SECONDARY,
    )
    return keyboard.get_json()
