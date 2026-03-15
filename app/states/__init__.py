"""Пакет групп состояний (FSM) приложения."""

from app.states.admin import AdminState
from app.states.legacy import LegacyState
from app.states.registration import RegistrationState
from app.states.tickets import TicketState

__all__ = ["RegistrationState", "LegacyState", "TicketState", "AdminState"]
