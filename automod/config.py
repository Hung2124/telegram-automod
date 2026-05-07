"""App configuration via pydantic-settings (reads .env)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = ""

    # LLM
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    # Storage
    database_url: str = "postgresql+asyncpg://automod:automod@localhost:5432/automod"
    redis_url: str = "redis://localhost:6379/0"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_monthly_price_id: str = ""
    stripe_enterprise_monthly_price_id: str = ""
    stripe_success_url: str = "https://example.com/subscribe/success"
    stripe_cancel_url: str = "https://example.com/subscribe/cancel"

    # App
    secret_key: str = "changeme"
    log_level: str = "INFO"
    admin_telegram_ids: str = ""  # CSV of int

    # Plan limits (msg/day)
    free_daily_limit: int = 200
    pro_daily_limit: int = 5000
    free_group_limit: int = 1
    pro_group_limit: int = 10

    @property
    def admin_ids(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_telegram_ids.split(",") if x.strip()]


settings = Settings()  # type: ignore[call-arg]
