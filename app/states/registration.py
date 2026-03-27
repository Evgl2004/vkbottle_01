"""FSM-состояния процесса регистрации нового пользователя в VK-боте."""

from vkbottle import BaseStateGroup


class RegistrationState(BaseStateGroup):
    """Группа состояний пошаговой регистрации.

    Порядок состояний отражает реальный пользовательский маршрут:
    от согласия с правилами до синхронизации с iiko.
    """

    WAITING_FOR_RULES_CONSENT = "waiting_for_rules_consent"
    WAITING_FOR_PHONE_METHOD = "waiting_for_phone_method"
    WAITING_FOR_CONTACT = "waiting_for_contact"
    WAITING_FOR_PHONE_VIA_MINI_APP = "waiting_for_phone_via_mini_app"
    WAITING_FOR_FIRST_NAME = "waiting_for_first_name"
    WAITING_FOR_LAST_NAME = "waiting_for_last_name"
    WAITING_FOR_GENDER = "waiting_for_gender"
    WAITING_FOR_BIRTH_DATE = "waiting_for_birth_date"
    WAITING_FOR_EMAIL = "waiting_for_email"

    WAITING_FOR_REVIEW = "waiting_for_review"
    WAITING_FOR_EDIT_CHOICE = "waiting_for_edit_choice"
    WAITING_FOR_EDIT_FIRST_NAME = "waiting_for_edit_first_name"
    WAITING_FOR_EDIT_LAST_NAME = "waiting_for_edit_last_name"
    WAITING_FOR_EDIT_GENDER = "waiting_for_edit_gender"
    WAITING_FOR_EDIT_BIRTH_DATE = "waiting_for_edit_birth_date"
    WAITING_FOR_EDIT_EMAIL = "waiting_for_edit_email"

    WAITING_FOR_NOTIFICATIONS_CONSENT = "waiting_for_notifications_consent"
    WAITING_FOR_IIKO_REGISTRATION = "waiting_for_iiko_registration"
