"""FSM-состояния административных операций."""

from vkbottle import BaseStateGroup


class AdminState(BaseStateGroup):
    """Состояния для сценария массовой рассылки и вспомогательных админ-действий."""

    BROADCAST_MESSAGE = "broadcast_message"
    BROADCAST_BUTTON = "broadcast_button"
    BROADCAST_CONFIRM = "broadcast_confirm"
