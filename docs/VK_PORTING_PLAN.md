# VK Porting Plan

## Phase 0: Baseline Initialization (completed)

- [x] Clone and inspect Telegram reference
- [x] Document architecture, FSM, data model, and business flows
- [x] Initialize new VKBottle project scaffold
- [x] Connect PostgreSQL + Redis in runtime bootstrap

## Phase 1: Transport Layer Foundation

Goal: enable stable VK routing and callback payload handling.

Tasks:
1. Add common VK payload schema helpers (`action`, `entity`, `id`, `page`).
2. Implement safe send/edit abstraction for VK API behavior.
3. Add middleware for user upsert and request logging.
4. Add keyboard factories for main menu, support, moderation, and admin.

Acceptance criteria:
- bot starts and handles text triggers for `/start`, `help`, `menu`
- callback payloads are parsed and routed deterministically

## Phase 2: Registration + Legacy Flows

Goal: parity with Telegram onboarding logic.

Tasks:
1. Implement registration FSM path:
   - rules consent
   - phone input and validation
   - profile fields
   - review + edits
   - notification consent
2. Implement legacy upgrade FSM:
   - detect missing fields
   - delta field collection
   - review/edit
   - notification consent
3. Implement iiko sync adapters and retry flow.

Acceptance criteria:
- new and legacy users both reach main menu after successful flow
- all consent timestamps are persisted

## Phase 3: Support Tickets + Moderation

Goal: parity for support and moderator operations.

Tasks:
1. Implement user ticket creation and list/detail/reply flow.
2. Implement moderator dashboard with filters and pagination.
3. Implement ticket close and response-time metrics.
4. Add notifications to moderators and users.

Acceptance criteria:
- full lifecycle `open -> in_progress -> closed` works end-to-end

## Phase 4: Admin Broadcast

Goal: parity for admin mass messaging.

Tasks:
1. Implement admin-only broadcast wizard (content + optional button + confirm).
2. Implement chunked sender with rate control.
3. Persist campaign execution stats.
4. Add progress reporting during send.

Acceptance criteria:
- admin can run broadcast with final success/fail/blocked stats

## Phase 5: Hardening

Tasks:
1. Add migration scripts for schema evolution.
2. Add integration tests for critical FSM paths.
3. Add structured logging and error telemetry.
4. Add deployment profile and production checks.

Acceptance criteria:
- deterministic startup, reproducible migrations, baseline test suite green
