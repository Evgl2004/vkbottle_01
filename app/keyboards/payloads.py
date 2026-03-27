"""Константы payload-команд для VK-кнопок.

Единая точка хранения строковых идентификаторов нужна для того, чтобы:
1. избежать опечаток между клавиатурой и хендлерами;
2. централизованно менять контракт payload;
3. сделать код более читаемым.
"""

# Универсальная навигация
CMD_START = "start"
CMD_MAIN_MENU = "main_menu"
CMD_BACK_TO_MAIN = "back_to_main"
CMD_BACK_TO_SUPPORT = "back_to_support"

# Регистрация
CMD_ACCEPT_RULES = "accept_rules"
CMD_GENDER_MALE = "gender_male"
CMD_GENDER_FEMALE = "gender_female"
CMD_REVIEW_OK = "review_ok"
CMD_REVIEW_EDIT = "review_edit"
CMD_EDIT_FIRST_NAME = "edit_first_name"
CMD_EDIT_LAST_NAME = "edit_last_name"
CMD_EDIT_GENDER = "edit_gender"
CMD_EDIT_BIRTH_DATE = "edit_birth_date"
CMD_EDIT_EMAIL = "edit_email"
CMD_EDIT_CANCEL = "edit_cancel"
CMD_NOTIFY_YES = "notify_yes"
CMD_NOTIFY_NO = "notify_no"
CMD_RETRY_IIKO = "retry_iiko"
CMD_PHONE_MANUAL = "phone_manual"
CMD_PHONE_VIA_MINI_APP = "phone_via_mini_app"
CMD_OPEN_MINI_APP = "open_mini_app"

# Главное меню
CMD_BALANCE = "balance"
CMD_VIRTUAL_CARD = "virtual_card"
CMD_SUPPORT = "support"
CMD_VACANCIES = "vacancies"
CMD_SUPPORT_FEEDBACK = "support_feedback"
CMD_SUPPORT_QUESTION = "support_question"
CMD_SUPPORT_CONTACTS = "support_contacts"
CMD_MY_TICKETS = "my_tickets"

# Пользовательские тикеты
CMD_USER_TICKET = "user_ticket"
CMD_USER_TICKETS_PAGE = "user_tickets_page"
CMD_USER_REPLY = "user_reply"

# Модерация
CMD_MOD_MAIN = "mod_main"
CMD_MOD_TICKETS = "mod_tickets"
CMD_MOD_TICKETS_PAGE = "mod_tickets_page"
CMD_MOD_TICKET = "mod_ticket"
CMD_MOD_REPLY = "mod_reply"
CMD_MOD_CLOSE = "mod_close"
