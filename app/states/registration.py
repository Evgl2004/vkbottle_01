"""Registration state identifiers.

These states are framework-agnostic constants.
They are intentionally separated from transport-specific VKBottle decorators.
"""


class RegistrationState:
    WAITING_FOR_RULES_CONSENT = "registration:waiting_for_rules_consent"
    WAITING_FOR_CONTACT = "registration:waiting_for_contact"
    WAITING_FOR_FIRST_NAME = "registration:waiting_for_first_name"
    WAITING_FOR_LAST_NAME = "registration:waiting_for_last_name"
    WAITING_FOR_GENDER = "registration:waiting_for_gender"
    WAITING_FOR_BIRTH_DATE = "registration:waiting_for_birth_date"
    WAITING_FOR_EMAIL = "registration:waiting_for_email"
    WAITING_FOR_REVIEW = "registration:waiting_for_review"
    WAITING_FOR_EDIT_CHOICE = "registration:waiting_for_edit_choice"
    WAITING_FOR_EDIT_FIRST_NAME = "registration:waiting_for_edit_first_name"
    WAITING_FOR_EDIT_LAST_NAME = "registration:waiting_for_edit_last_name"
    WAITING_FOR_EDIT_GENDER = "registration:waiting_for_edit_gender"
    WAITING_FOR_EDIT_BIRTH_DATE = "registration:waiting_for_edit_birth_date"
    WAITING_FOR_EDIT_EMAIL = "registration:waiting_for_edit_email"
    WAITING_FOR_NOTIFICATIONS_CONSENT = "registration:waiting_for_notifications_consent"
    WAITING_FOR_IIKO_REGISTRATION = "registration:waiting_for_iiko_registration"
