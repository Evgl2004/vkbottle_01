# VKBottle Bot (PostgreSQL + Redis)

This repository is a VK messenger bot project built on:
- `vkbottle`
- `PostgreSQL`
- `Redis`

The business reference is the Telegram bot from:
- [Evgl2004/aiogram_bot_01](https://github.com/Evgl2004/aiogram_bot_01)

## Current Status

- Reference repo cloned locally to `reference_aiogram_bot_01/`
- Deep analysis completed in:
  - `docs/REFERENCE_ANALYSIS.md`
  - `docs/VK_PORTING_PLAN.md`
- Project initialized with base structure and runtime bootstrap

## Project Structure

```text
app/
  config.py
  main.py
  handlers/
  database/
  services/
  states/
docs/
scripts/
docker-compose.yml
Dockerfile
requirements.txt
```

## Quick Start

1. Copy environment file:

```bash
cp .env.example .env
```

2. Fill required env vars:
- `VK_BOT_TOKEN`
- `POSTGRES_PASSWORD`
- `ADMIN_USER_IDS` (optional)

3. Run services:

```bash
docker compose up --build
```

## Git Workflow

- `main`: project initialization baseline
- `codex/develop-cai`: active development branch for feature work

## Notes

- This initialization focuses on architecture and migration groundwork.
- Feature-complete parity with Telegram reference is planned in phases (see docs).
