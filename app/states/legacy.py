"""FSM-состояния апгрейда legacy-пользователей."""

from vkbottle import BaseStateGroup


class LegacyState(BaseStateGroup):
    """Группа состояний для актуализации данных пользователей из старой версии бота."""

    WAITING_FOR_RULES_CONSENT = "waiting_for_rules_consent"
    WAITING_FOR_FIELD = "waiting_for_field"
    WAITING_FOR_REVIEW = "waiting_for_review"
    WAITING_FOR_EDIT_CHOICE = "waiting_for_edit_choice"
    WAITING_FOR_EDIT_FIELD = "waiting_for_edit_field"
    WAITING_FOR_NOTIFICATIONS_CONSENT = "waiting_for_notifications_consent"
    WAITING_FOR_IIKO_REGISTRATION = "waiting_for_iiko_registration"
