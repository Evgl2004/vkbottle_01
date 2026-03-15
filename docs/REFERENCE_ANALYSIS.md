# Reference Bot Deep Analysis (Telegram -> VK)

Source analyzed:
- local clone: `reference_aiogram_bot_01`
- original: `https://github.com/Evgl2004/aiogram_bot_01`

## 1. High-Level Architecture

The reference bot follows a layered architecture:

- `handlers/`: user interaction and routing
- `states/`: FSM states for registration, legacy upgrade, admin broadcast, ticket replies
- `services/`: business use cases (`tickets`, `broadcast`, `user_sync`, `iiko`)
- `database/`: SQLAlchemy models + async database access + custom migration runner
- `middlewares/`: cross-cutting concerns (user upsert, request logging)
- `keyboards/`: all UI callback payload sources

Storage split:
- Persistent data: PostgreSQL
- Ephemeral conversational context: Redis FSM storage

## 2. Main Functional Domains

### 2.1 User Onboarding and Registration

Primary entrypoint:
- `/start` handler in `handlers/start.py`

Decision logic on start:
1. Upsert user base profile from messenger metadata.
2. If user is `is_registered && is_legacy`: run legacy upgrade flow.
3. If user has not accepted rules: show consent docs and wait for approval.
4. If rules accepted but registration incomplete: collect contact and profile fields.
5. If fully registered: show main menu.

Registration data collected:
- phone number
- first/last name
- gender
- birth date (age constraints: 18..100)
- email
- notification consent

After profile confirmation and notification choice:
- sync with iiko
- create/update iiko customer
- issue loyalty card if absent
- mark `is_registered=True`
- show main menu

### 2.2 Legacy Upgrade Flow

Legacy users are identified via `is_legacy=True`.

Flow behavior:
1. Ask for rules consent again (legal consent refresh).
2. Detect missing or invalid profile fields.
3. Request only missing fields in sequence.
4. Show profile review with editable fields.
5. Ask notification consent.
6. Set `is_legacy=False`.
7. Sync with iiko and complete registration.

Key property:
- Delta collection: only incomplete fields are requested.

### 2.3 Main Menu and Support

Main menu sections:
- balance
- virtual card
- support
- vacancies

Support submenu:
- feedback link
- create ticket ("ask question")
- my tickets (shown only if user has at least one ticket)
- contacts

### 2.4 Ticketing and Moderation

Core entities:
- `tickets`
- `ticket_messages`

User capabilities:
- create ticket
- list own tickets with pagination
- view ticket details and message thread
- reply while ticket is not closed

Moderator capabilities:
- view queue by filters (`all`, `open`, `in_progress`)
- paginate and inspect details
- reply to ticket
- close ticket

Business rules:
- first moderator reply sets `first_response_at`
- closing sets `closed_at`
- stats include open/in-progress counts and average first-response time

### 2.5 Admin Broadcast

Admin flow:
1. receive outbound message content (many media types supported)
2. optional URL button
3. confirmation with recipient count
4. batch sending with progress updates

Batch strategy:
- chunked sends (30 recipients per batch)
- inter-batch delay
- progress callback to update admin status message
- counters: sent/failed/blocked

### 2.6 External iiko Integration

iiko adapter responsibilities:
- obtain auth token with retries
- fetch customer info by phone
- create or update customer profile
- add loyalty card
- attach customer to loyalty program

Operational characteristics:
- explicit retry strategy only for token retrieval
- business flow retries via user callback "retry_iiko_registration"

## 3. FSM Inventory and Transitions

### 3.1 Registration FSM

States (ordered path):
1. `waiting_for_rules_consent`
2. `waiting_for_contact`
3. `waiting_for_first_name`
4. `waiting_for_last_name`
5. `waiting_for_gender`
6. `waiting_for_birth_date`
7. `waiting_for_email`
8. `waiting_for_review`
9. `waiting_for_notifications_consent`
10. `waiting_for_iiko_registration`

Editable branch from review:
- `waiting_for_edit_choice`
- `waiting_for_edit_first_name`
- `waiting_for_edit_last_name`
- `waiting_for_edit_gender`
- `waiting_for_edit_birth_date`
- `waiting_for_edit_email`

### 3.2 Legacy FSM

States:
- rules consent
- missing field collection
- review
- edit choice / edit field
- notification consent
- iiko registration wait

### 3.3 Tickets FSM

States:
- user question creation wait
- moderator reply wait
- user reply wait

### 3.4 Admin FSM

States:
- broadcast content wait
- button definition wait
- broadcast confirmation

## 4. Data Model Analysis

Primary tables:

- `users`
  - identity and messenger metadata
  - registration profile fields
  - legal consent fields and timestamps
  - flags: `is_registered`, `is_legacy`, `is_moderator`, `is_active`
- `tickets`
  - user question, status, lifecycle timestamps
- `ticket_messages`
  - full threaded conversation by `ticket_id`
- `bot_stats`
  - aggregate counters and last restart
- `migration_history`
  - custom migration bookkeeping

Important relationships:
- `ticket_messages.ticket_id -> tickets.id` (FK in migrations)

Persistence boundaries:
- PostgreSQL stores business truth.
- Redis stores conversational progress only.

## 5. Control and Routing Observations

Router order in dispatcher is meaningful:
- start and help are loaded first
- domain flows follow
- moderation and user tickets are loaded near the end

Callbacks are contract-based through keyboard payloads.
Any migration to VK must preserve callback contract semantics, even if payload encoding changes.

## 6. VK Migration Impact

### 6.1 Direct Mappings

- Telegram handlers -> VK message/callback handlers
- SQLAlchemy layer can be reused almost 1:1
- ticket/broadcast business services are mostly platform-agnostic

### 6.2 Non-Direct Mappings

1. Contact collection:
   - Telegram supports native contact share button.
   - VK does not provide an equivalent universal flow in the same way.
   - Required change: manual phone entry + validation and normalization.

2. Callback mechanism:
   - Telegram inline callback data differs from VK keyboard payload events.
   - Required change: payload schema adapter.

3. Message editing semantics:
   - Telegram flow relies heavily on editing messages.
   - VK edit support differs by event and message context.
   - Required change: safe send/edit abstraction with fallback.

4. Attachments and file id model:
   - Telegram uses `file_id`; VK uses attachment identifiers and upload steps.
   - Broadcast media logic needs a dedicated VK sender adapter.

5. Command UX:
   - Slash commands are native in Telegram.
   - VK UX is mostly text triggers and keyboard navigation.
   - Required change: command aliases + entry phrase handling.

## 7. Target Migration Strategy

Recommended approach:

1. Keep domain/services and data models as shared core.
2. Rebuild transport layer (`handlers`, `ui payloads`, `message helpers`) for VK.
3. Introduce platform adapter interfaces:
   - `MessageGateway`
   - `KeyboardFactory`
   - `UserIdentityAdapter`
4. Implement compatibility tests for flow parity:
   - registration path
   - legacy path
   - ticket lifecycle
   - moderator workflow
   - admin broadcast

## 8. Critical Risks to Plan For

- Legal consent logging parity (must keep timestamp fields).
- Phone capture reliability without native contact share.
- Callback payload schema drift between keyboard definitions and handlers.
- Attachment handling complexity in VK broadcasts.
- FSM race conditions under retries and repeated button clicks.

## 9. What Was Initialized in This Repository

This repository now includes:
- new VK project scaffold
- PostgreSQL and Redis runtime wiring
- baseline DB schema matching core entities
- startup bootstrap checks
- phased migration plan document

See `docs/VK_PORTING_PLAN.md` for next implementation phases.
