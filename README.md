# 🛡️ Telegram Auto-Mod

> AI-powered moderation bot for Telegram groups. Auto-detect spam, scams, NSFW, and rule violations using LLM classification.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

---

## ✨ Features

- 🤖 **LLM-powered classification** — uses GPT-4o-mini / Claude Haiku to classify each message in 200ms
- 🚫 **Auto-actions** — delete, warn, mute, kick, or ban based on rule severity
- 📊 **Per-group config** — admins customize rules via `/automod` command
- 💰 **Free tier** — 1 group, 500 messages/month
- 🔥 **Pro tier ($9/group/month)** — unlimited messages, custom rule prompts, audit log, webhook
- 📈 **Stats dashboard** — daily moderation report sent to admin DM

## 🎯 Why?

Telegram public groups grow fast → spam scams (crypto, fake CEO DMs, NSFW links) explode. Existing tools (Combot, Shieldy) use keyword/regex blacklists that scammers easily bypass. **Auto-Mod uses LLM context understanding** — catches paraphrased scams, multi-language abuse, and zero-day patterns.

## 🏗️ Architecture

```
┌─────────────────┐    webhook    ┌──────────────────┐
│  Telegram API   │──────────────▶│  FastAPI server  │
└─────────────────┘                │  (telegram-bot)  │
                                   └────────┬─────────┘
                                            │
                          ┌─────────────────┼─────────────────┐
                          ▼                 ▼                 ▼
                   ┌────────────┐    ┌────────────┐    ┌────────────┐
                   │  Postgres  │    │  Redis     │    │  LLM API   │
                   │  (config)  │    │  (cache)   │    │  (gpt/cld) │
                   └────────────┘    └────────────┘    └────────────┘
```

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/Hung2124/telegram-automod.git
cd telegram-automod

# 2. Copy env template
cp .env.example .env
# Edit: TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, DATABASE_URL

# 3. Install
pip install -e .[dev]

# 4. Run
docker compose up -d  # Postgres + Redis
python -m automod.main
```

## 📦 Tech Stack

- **Python 3.11+**
- **python-telegram-bot v21** — async Telegram API client
- **FastAPI + uvicorn** — webhook server
- **PostgreSQL + SQLAlchemy** — group config, audit log
- **Redis** — rate limiting, message cache
- **OpenAI / Anthropic SDK** — LLM classification (configurable)
- **Stripe** — billing (Pro tier)

## 🛣️ Roadmap

- [x] Repo scaffold + license
- [ ] Week 1: Core moderation loop (webhook → classify → action)
- [ ] Week 1: Per-group config DB + `/automod` admin commands
- [ ] Week 2: Stripe billing + free tier limits
- [ ] Week 2: Landing page + onboarding
- [ ] Week 3: Beta launch on r/Telegram, IndieHackers, Telegram dev groups
- [ ] Week 4: Public launch + Product Hunt

## 📜 License

MIT © 2026 Hung Nguyen

## 🤝 Contributing

Issues and PRs welcome. For paid plan signup: see [landing page] (coming soon).
