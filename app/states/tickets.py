"""Ticket and moderation state identifiers."""


class TicketState:
    WAITING_FOR_QUESTION = "tickets:waiting_for_question"
    WAITING_FOR_MODERATOR_REPLY = "tickets:waiting_for_moderator_reply"
    WAITING_FOR_USER_REPLY = "tickets:waiting_for_user_reply"
