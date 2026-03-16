# Сверка VK-реализации с Telegram-референсом (`aiogram_bot_01`)

**Дата актуализации:** 16.03.2026  
**Ветка проверки:** `codex/develop-cai`  
**Цель:** подтвердить полноту переноса бизнес-логики, состояний, хранилищ и пользовательских сценариев.

## 1. Итог ревизии

По обязательному MVP-составу перенос выполнен корректно:
1. Регистрация пользователя.
2. Legacy-обновление профиля.
3. Тикетная система (создание, список, карточка, ответы).
4. Модерация тикетов (фильтры, ответы, закрытие).
5. Интеграция iiko (поиск/создание клиента, выпуск карты, подключение лояльности).
6. PostgreSQL для бизнес-данных.
7. Redis для FSM-состояний.

Критичное ранее найденное расхождение по QR-картам закрыто:
1. QR отправляется из раздела «Виртуальная карта».
2. QR отправляется после успешной регистрации.
3. QR отправляется после успешного legacy-апгрейда.

## 2. Матрица соответствия (референс -> VK)

| Блок | Референс (Telegram) | VK-проект | Статус |
|---|---|---|---|
| Старт и маршрутизация | `handlers/start.py` | `app/handlers/start.py` | Перенесено |
| Регистрация FSM | `handlers/registration.py` + `states/registration.py` | `app/handlers/registration.py` + `app/states/registration.py` | Перенесено |
| Legacy FSM | `handlers/legacy.py` + `states/legacy.py` | `app/handlers/legacy.py` + `app/states/legacy.py` | Перенесено |
| Главное меню | `handlers/menu.py` | `app/handlers/menu.py` | Перенесено |
| Пользовательские тикеты | `handlers/user_tickets.py` | `app/handlers/user_tickets.py` | Перенесено |
| Модерация тикетов | `handlers/moderation.py` | `app/handlers/moderation.py` | Перенесено |
| iiko async/API слой | `services/iiko_async.py`, `services/iiko_service.py`, `services/user_sync.py` | `app/services/iiko_async.py`, `app/services/iiko_service.py`, `app/services/user_sync.py` | Перенесено |
| PostgreSQL-модель | `database/models.py` + миграции | `app/database/models.py` + `app/database/database.py` | Перенесено (MVP-режим `create_tables`) |
| FSM в Redis | Telegram Redis storage | `app/services/state_dispenser.py` | Перенесено (адаптировано) |
| Middleware логирования | `middlewares/logging.py` | `app/middlewares/logging.py` | Перенесено |

## 3. Состояния и переходы

### 3.1 Регистрация (`RegistrationState`)
Сохранена полная цепочка:
1. `WAITING_FOR_RULES_CONSENT`
2. `WAITING_FOR_CONTACT`
3. `WAITING_FOR_FIRST_NAME`
4. `WAITING_FOR_LAST_NAME`
5. `WAITING_FOR_GENDER`
6. `WAITING_FOR_BIRTH_DATE`
7. `WAITING_FOR_EMAIL`
8. `WAITING_FOR_REVIEW`
9. `WAITING_FOR_EDIT_*`
10. `WAITING_FOR_NOTIFICATIONS_CONSENT`
11. `WAITING_FOR_IIKO_REGISTRATION`

### 3.2 Legacy (`LegacyState`)
Сохранён дельта-подход:
1. Подтверждение правил.
2. Сбор только недостающих полей.
3. Ревью/редактирование.
4. Согласие на уведомления.
5. Синхронизация с iiko.

### 3.3 Тикеты (`TicketState`)
Сохранены рабочие состояния:
1. `WAITING_FOR_QUESTION`
2. `WAITING_FOR_USER_REPLY`
3. `WAITING_FOR_MODERATOR_REPLY`

## 4. Модель данных и хранилища

### 4.1 PostgreSQL
Сопоставление с референсом подтверждено:
1. `users` (анкета + согласия + роли + флаги жизненного цикла).
2. `tickets` (статус, метки SLA: `first_response_at`, `closed_at`).
3. `ticket_messages`.
4. `bot_stats`.
5. `migration_history` (служебная совместимость).

### 4.2 Redis FSM
Состояния и payload хранятся в Redis через кастомный `RedisStateDispenser`:
1. сохранение состояния между рестартами;
2. TTL на «забытые» сценарии;
3. явные debug-логи `get/set/delete`.

## 5. Что адаптировано под VK осознанно

1. Telegram-кнопка `request_contact` заменена на ручной ввод телефона с валидацией/нормализацией.
2. Callback-механика Telegram заменена на VK payload (`payload_contains` / `payload_map`).
3. Доставка QR реализована через VK API загрузки изображений в сообщения (`photos.getMessagesUploadServer` -> upload -> `photos.saveMessagesPhoto`).
4. Навигация оптимизирована под VK-клавиатуры (включая кнопки с emoji-маркировкой).

## 6. Усиления, внесённые в VK-проект

1. Введено сквозное middleware-логирование входящих событий:
   - user/peer/message/payload/state;
   - длительность обработки;
   - список сработавших хендлеров.
2. Добавлены подробные debug/info/warning/error логи в `handlers`, `services`, `database`.
3. Упорядочены сообщения для пользователя и кнопки с emoji в стиле референса.
4. Навигационные сценарии переведены на callback-подход `message_event`:
   - главное меню;
   - раздел «Виртуальная карта»;
   - подменю поддержки;
   - пользовательские тикеты (список/страницы/карточка/старт ответа);
   - модераторское меню и очереди тикетов;
   - кнопочные этапы регистрации и legacy-анкеты (согласия, review, выборы полей, retry iiko).

## 7. Что пока вне текущего MVP (осознанно)

1. Полноценная админ-рассылка (в референсе есть отдельный поток admin/broadcast).
2. Часть вспомогательных Telegram-специфичных модулей (`safe_edit_message`, `local Bot API mode`), которые не требуются VK-транспорту.

## 8. Оставшиеся UX-различия с Telegram

1. Для шага с вводом текста (имя, фамилия, email, ответы в тикетах) в VK неизбежно используются новые сообщения пользователя, поэтому абсолютная «экранность» как в Telegram ограничена платформой.
2. Сценарий виртуальной карты отправляет отдельные сообщения с изображениями QR (что ближе к VK-практике вложений), а не редактирует одно сообщение на весь поток.

## 9. Вывод

Ключевая бизнес-логика референса для заявленного MVP перенесена без функциональных потерь.  
Ранее проблемный участок с QR-картами закрыт, а также усилена эксплуатационная наблюдаемость через расширенное логирование и middleware-слой.
