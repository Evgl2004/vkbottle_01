"""FSM-состояния тикетной системы."""

from vkbottle import BaseStateGroup


class TicketState(BaseStateGroup):
    """Состояния для создания тикетов и ответов модератора."""

    WAITING_FOR_QUESTION = "waiting_for_question"
    WAITING_FOR_MODERATOR_REPLY = "waiting_for_moderator_reply"
    WAITING_FOR_USER_REPLY = "waiting_for_user_reply"
