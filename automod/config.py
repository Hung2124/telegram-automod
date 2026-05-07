"""App configuration via pydantic-settings (reads .env)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""          # e.g. https://yourapp.railway.app
    telegram_webhook_secret: str = "automod-secret-2024"

    # LLM (Xiaomi MiMo — OpenAI-compatible)
    llm_provider: str = "xiaomi"
    xiaomi_api_key: str = ""
    xiaomi_base_url: str = "https://token-plan-sgp.xiaomimimo.com/v1"
    xiaomi_model: str = "mimo-v2.5-pro"
    # Legacy OpenAI/Anthropic fallback (optional)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    # Quota limits
    free_daily_limit: int = 100
    pro_daily_limit: int = 5000
    enterprise_daily_limit: int = 999999

    database_url: str = "postgresql+asyncpg://automod:automod@localhost:5432/automod"
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # LemonSqueezy billing
    lemonsqueezy_api_key: str = ""
    lemonsqueezy_webhook_secret: str = ""   # set in LS dashboard → Webhooks
    lemonsqueezy_store_id: str = "368020"
    lemonsqueezy_pro_variant_id: str = ""       # fill after creating product
    lemonsqueezy_enterprise_variant_id: str = ""  # fill after creating product
    lemonsqueezy_pro_checkout_url: str = ""     # auto-generated or manual
    lemonsqueezy_enterprise_checkout_url: str = ""

    # Admin
    admin_telegram_ids: str = ""

    # App
    log_level: str = "INFO"

    @property
    def admin_ids(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_telegram_ids.split(",") if x.strip()]


settings = Settings()  # type: ignore[call-arg]
