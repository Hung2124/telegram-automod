# CLAUDE.md — Instructions for Claude Code

## Project
Telegram Auto-Mod SaaS — Python 3.11+, FastAPI, python-telegram-bot v21, SQLAlchemy 2 async, Alembic, Redis, Stripe, pytest.

## Your Task
Read SPEC.md fully, then implement every feature described there. Work **feature by feature**, committing after each.

## Rules

### Workflow
1. Read SPEC.md, then the existing scaffold in `automod/` and `tests/`.
2. Implement each section of SPEC.md in order (DB → commands → Stripe → API → tests).
3. After each feature: `pytest tests/ -x -q`. Fix failures before moving on.
4. Commit after each working feature: `git add -A && git commit -m "feat: <short description>"`.
5. Do NOT open a PR. Push to `main`: `git push origin main`.

### Code Style
- Use `from __future__ import annotations` in every file.
- Type-annotate all function signatures.
- Use `structlog.get_logger()` for logging (never `print`).
- Async everywhere — `async def`, `await`, `AsyncSession`.
- Use `select()` / `insert()` from `sqlalchemy` (no ORM `.query()`).

### Database
- Models in `automod/models.py` (SQLAlchemy `DeclarativeBase`, async).
- Alembic config in `alembic/` — run `alembic init alembic` if not exists.
- Always use `async with AsyncSession(engine) as session:` pattern.
- For tests, use SQLite `sqlite+aiosqlite:///:memory:` via `conftest.py` fixture.

### Redis
- Quota counter key: `quota:{group_id}:{YYYY-MM-DD}`, TTL 86400.
- Use `redis.asyncio` client.
- Mock Redis in tests with `fakeredis.aioredis`.

### Stripe
- Use `stripe` Python SDK (sync calls are fine — wrap in `asyncio.to_thread` if needed).
- Webhook endpoint must verify signature before processing.
- All event processing must be idempotent (check `stripe_events` table).

### Bot Commands
- Each command in its own `async def cmd_XXX(update, context)` function in `automod/commands.py`.
- Check `is_admin` via `update.effective_chat.get_member(user_id)` — only `ChatMemberAdministrator` or `ChatMemberOwner` can use admin commands.
- For quota-blocked messages: silently skip (do NOT send message to group).

### Tests
- Use `pytest-asyncio` with `asyncio_mode = "auto"` (already in pyproject.toml if not, add it).
- Mock LLM calls with `pytest-mock` / `unittest.mock.AsyncMock`.
- Mock Telegram bot API with `python-telegram-bot`'s `MagicMock` update helpers.
- Every new file gets a corresponding test file.
- Run full suite with `pytest tests/ -q --tb=short`.

### Do NOT
- Do NOT use `requests` (use `httpx` or `openai`/`anthropic` SDKs).
- Do NOT hardcode secrets — read from `config.py` (`settings.*`).
- Do NOT delete existing scaffold code unless it's replaced by a better version.
- Do NOT use `/resume` slash command.
- Use `rg` / `Select-String` for searching, not `grep`.

## Commit Message Format
```
feat: add DB models and alembic initial migration
feat: implement /automod on|off commands with DB persistence
feat: add Redis quota enforcement (free plan 200/day)
feat: implement Stripe /subscribe flow and webhook handler
feat: add REST API endpoints with JWT auth
feat: complete test suite ≥80% coverage
```

## Done When
- `alembic upgrade head` runs cleanly.
- `pytest tests/ -q` passes with ≥ 80% coverage.
- `docker-compose up` starts all services.
- All acceptance criteria in SPEC.md are checked.
