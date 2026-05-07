# Telegram Auto-Mod — Feature Specification

## Overview
A SaaS bot that group admins add to their Telegram groups. The bot uses an LLM classifier
to detect spam/scam/hate/nsfw messages and takes automated action. Admins manage settings
via a web dashboard or Telegram commands. Monetised via Stripe subscriptions.

---

## 1. Database Schema (SQLAlchemy async + Alembic)

### `groups` table
| column | type | notes |
|--------|------|-------|
| id | BIGINT PK | Telegram chat_id (can be negative) |
| title | TEXT | group name, updated on each event |
| owner_user_id | BIGINT | first admin who ran /automod |
| plan | TEXT | "free" / "pro" / "enterprise" |
| stripe_customer_id | TEXT nullable | |
| stripe_subscription_id | TEXT nullable | |
| is_active | BOOL default TRUE | set FALSE to pause bot in group |
| rules_text | TEXT default "" | custom rules injected into LLM prompt |
| action_thresholds | JSONB | `{"high":"delete_and_mute","medium":"delete","low":"warn"}` |
| mute_duration_minutes | INT default 60 | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `users` table
| column | type | notes |
|--------|------|-------|
| id | BIGINT PK | Telegram user_id |
| username | TEXT nullable | |
| first_name | TEXT | |
| is_admin | BOOL default FALSE | superadmin flag |
| created_at | TIMESTAMPTZ | |

### `group_members` table
| column | type | notes |
|--------|------|-------|
| group_id | BIGINT FK groups.id | |
| user_id | BIGINT FK users.id | |
| role | TEXT | "admin" / "member" / "banned" |
| warn_count | INT default 0 | incremented on each "warn" action |
| PRIMARY KEY | (group_id, user_id) | |

### `audit_log` table
| column | type | notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| group_id | BIGINT FK groups.id | |
| user_id | BIGINT FK users.id | |
| message_text | TEXT | original message (truncated to 1000 chars) |
| verdict_category | TEXT | spam/scam/nsfw/hate/off_topic/advertising/ok |
| verdict_severity | TEXT | none/low/medium/high |
| verdict_confidence | FLOAT | 0.0–1.0 |
| verdict_reason | TEXT | |
| action_taken | TEXT | noop/warn/delete/delete_and_mute |
| created_at | TIMESTAMPTZ | |

### `stripe_events` table
| column | type | notes |
|--------|------|-------|
| id | TEXT PK | Stripe event id |
| type | TEXT | e.g. "customer.subscription.created" |
| payload | JSONB | full event |
| processed_at | TIMESTAMPTZ | |

---

## 2. Plan Limits

| plan | msg/day | groups | custom rules | advanced actions |
|------|---------|--------|--------------|-----------------|
| free | 200 | 1 | ✗ | ✗ |
| pro | 5 000 | 10 | ✓ | ✓ |
| enterprise | unlimited | unlimited | ✓ | ✓ |

Counter stored in Redis key `quota:{group_id}:{YYYY-MM-DD}` with TTL 86400.

---

## 3. Bot Commands

| command | who | description |
|---------|-----|-------------|
| `/start` | any | show welcome + setup instructions |
| `/automod on\|off` | group admin | enable or disable moderation in this group |
| `/automod rules <text>` | group admin | set custom rules (pro+) |
| `/automod status` | group admin | show current config + quota |
| `/automod reset_warns @user` | group admin | reset warn count for a user |
| `/stats` | group admin | last 24h: N messages scanned, N violations, breakdown by category |
| `/subscribe` | group admin | generate Stripe Checkout URL for pro plan |
| `/unsubscribe` | group admin | cancel subscription |

---

## 4. Stripe Integration

**Flow:**
1. Admin runs `/subscribe` → bot creates Stripe Customer + Checkout Session → sends link
2. User pays → Stripe sends `checkout.session.completed` webhook → bot updates `groups.plan = 'pro'`
3. `customer.subscription.deleted` webhook → downgrade to `free`

**Price IDs** (read from env):
- `STRIPE_PRO_MONTHLY_PRICE_ID`
- `STRIPE_ENTERPRISE_MONTHLY_PRICE_ID`

**Webhook endpoint:** `POST /stripe/webhook`
- Validate signature via `stripe.Webhook.construct_event`
- Idempotent: skip if `stripe_events.id` already exists

---

## 5. API Endpoints (FastAPI)

| method | path | auth | description |
|--------|------|------|-------------|
| POST | /webhook | secret header | Telegram bot webhook |
| GET | /healthz | none | liveness check |
| POST | /stripe/webhook | Stripe-Signature | Stripe events |
| GET | /api/groups | Bearer JWT | list groups the caller admins |
| GET | /api/groups/{id} | Bearer JWT | group detail + recent audit log |
| PATCH | /api/groups/{id} | Bearer JWT | update rules / thresholds |
| GET | /api/groups/{id}/stats | Bearer JWT | stats (24h / 7d / 30d window) |

JWT: HS256, secret = `SECRET_KEY` env var, payload `{"user_id": int, "exp": ...}`.

---

## 6. Database Migrations

Use **Alembic** with async SQLAlchemy. Migration files in `alembic/versions/`.
Initial migration creates all tables above.

---

## 7. Tests (pytest + pytest-asyncio)

Write tests for:
- `classify()` — mock LLM call, assert Verdict fields
- `on_group_message()` — mock PTB update, assert correct action called
- Each bot command handler (start, automod on/off, stats, subscribe)
- Stripe webhook handler — `checkout.session.completed` and `subscription.deleted`
- Quota enforcement — message blocked when daily limit hit
- API endpoints (using httpx AsyncClient)
- DB CRUD operations (use SQLite for test isolation)

Coverage target: ≥ 80%.

---

## 8. Environment Variables (add to .env.example)

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_URL=https://yourapp.railway.app/webhook
TELEGRAM_WEBHOOK_SECRET=

LLM_PROVIDER=openai          # openai | anthropic
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-haiku-latest

DATABASE_URL=postgresql+asyncpg://automod:automod@localhost:5432/automod
REDIS_URL=redis://localhost:6379/0

STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRO_MONTHLY_PRICE_ID=
STRIPE_ENTERPRISE_MONTHLY_PRICE_ID=
STRIPE_SUCCESS_URL=https://yourapp.railway.app/subscribe/success
STRIPE_CANCEL_URL=https://yourapp.railway.app/subscribe/cancel

SECRET_KEY=changeme
ADMIN_TELEGRAM_IDS=123456789
LOG_LEVEL=INFO
```

---

## 9. Acceptance Criteria

- [ ] All tables created via Alembic migration (run `alembic upgrade head`)
- [ ] Bot correctly classifies and deletes a spam message in a test chat
- [ ] `/automod on` registers group in DB; `/automod off` sets `is_active=False`
- [ ] Free plan blocks classification once quota exceeded (200/day)
- [ ] `/subscribe` returns a valid Stripe Checkout URL
- [ ] Stripe `checkout.session.completed` upgrades group to `pro`
- [ ] All API endpoints return correct status codes
- [ ] `pytest` passes with ≥ 80% coverage
- [ ] `docker-compose up` starts bot + postgres + redis with no errors
