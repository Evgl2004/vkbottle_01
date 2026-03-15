"""Клавиатуры для сценариев регистрации и legacy-апгрейда."""

from __future__ import annotations

from vkbottle import Keyboard, KeyboardButtonColor, OpenLink, Text

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


def get_rules_keyboard() -> str:
    """Возвращает inline-клавиатуру для принятия правил.

    Содержит:
    1. кнопку-ссылку на документы;
    2. кнопку подтверждения согласия.
    """

    keyboard = Keyboard(inline=True)
    keyboard.add(OpenLink("https://sagur.24vds.ru/agreement/", "Открыть документы"))
    keyboard.row()
    keyboard.add(
        Text("Согласен", payload={"cmd": CMD_ACCEPT_RULES}),
        color=KeyboardButtonColor.POSITIVE,
    )
    return keyboard.get_json()


def get_gender_keyboard() -> str:
    """Возвращает inline-клавиатуру выбора пола."""

    keyboard = Keyboard(inline=True)
    keyboard.add(
        Text("Мужской", payload={"cmd": CMD_GENDER_MALE}),
        color=KeyboardButtonColor.PRIMARY,
    )
    keyboard.add(
        Text("Женский", payload={"cmd": CMD_GENDER_FEMALE}),
        color=KeyboardButtonColor.PRIMARY,
    )
    return keyboard.get_json()


def get_notifications_keyboard() -> str:
    """Возвращает клавиатуру согласия на уведомления."""

    keyboard = Keyboard(inline=True)
    keyboard.add(OpenLink("https://sagur.24vds.ru/notifications/", "Условия уведомлений"))
    keyboard.row()
    keyboard.add(
        Text("Согласен на уведомления", payload={"cmd": CMD_NOTIFY_YES}),
        color=KeyboardButtonColor.POSITIVE,
    )
    keyboard.row()
    keyboard.add(
        Text("Отказываюсь от уведомлений", payload={"cmd": CMD_NOTIFY_NO}),
        color=KeyboardButtonColor.NEGATIVE,
    )
    return keyboard.get_json()


def get_review_keyboard() -> str:
    """Возвращает клавиатуру подтверждения или редактирования анкеты."""

    keyboard = Keyboard(inline=True)
    keyboard.add(Text("Всё верно", payload={"cmd": CMD_REVIEW_OK}), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()
    keyboard.add(Text("Изменить", payload={"cmd": CMD_REVIEW_EDIT}), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def get_edit_choice_keyboard() -> str:
    """Возвращает клавиатуру выбора редактируемого поля анкеты."""

    keyboard = Keyboard(inline=True)
    keyboard.add(Text("Имя", payload={"cmd": CMD_EDIT_FIRST_NAME}))
    keyboard.row()
    keyboard.add(Text("Фамилия", payload={"cmd": CMD_EDIT_LAST_NAME}))
    keyboard.row()
    keyboard.add(Text("Пол", payload={"cmd": CMD_EDIT_GENDER}))
    keyboard.row()
    keyboard.add(Text("Дата рождения", payload={"cmd": CMD_EDIT_BIRTH_DATE}))
    keyboard.row()
    keyboard.add(Text("Email", payload={"cmd": CMD_EDIT_EMAIL}))
    keyboard.row()
    keyboard.add(Text("Отмена", payload={"cmd": CMD_EDIT_CANCEL}), color=KeyboardButtonColor.NEGATIVE)
    return keyboard.get_json()


def get_retry_iiko_keyboard() -> str:
    """Клавиатура повторной попытки синхронизации с iiko."""

    keyboard = Keyboard(inline=True)
    keyboard.add(
        Text("Повторить попытку", payload={"cmd": CMD_RETRY_IIKO}),
        color=KeyboardButtonColor.PRIMARY,
    )
    return keyboard.get_json()
