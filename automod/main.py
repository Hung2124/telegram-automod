"""Bot entrypoint — webhook mode via FastAPI + python-telegram-bot."""
from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters

from .config import settings
from .moderation import on_group_message
from .commands import cmd_start, cmd_automod, cmd_stats, cmd_subscribe, cmd_unsubscribe

logging.basicConfig(level=settings.log_level)
log = structlog.get_logger()


def build_application() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("automod", cmd_automod))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, on_group_message))
    return app


def create_fastapi(ptb_app: Application) -> FastAPI:
    api = FastAPI(title="Telegram Auto-Mod")

    from .api import router as api_router
    api.include_router(api_router)

    @api.on_event("startup")
    async def _startup() -> None:
        await ptb_app.initialize()
        await ptb_app.start()
        if settings.telegram_webhook_url:
            await ptb_app.bot.set_webhook(
                url=settings.telegram_webhook_url,
                secret_token=settings.telegram_webhook_secret or None,
                allowed_updates=Update.ALL_TYPES,
            )
            log.info("webhook_set", url=settings.telegram_webhook_url)

    @api.on_event("shutdown")
    async def _shutdown() -> None:
        await ptb_app.stop()
        await ptb_app.shutdown()

    @api.post("/webhook")
    async def webhook(request: Request) -> dict:
        if settings.telegram_webhook_secret:
            got = request.headers.get("x-telegram-bot-api-secret-token", "")
            if got != settings.telegram_webhook_secret:
                raise HTTPException(401, "bad secret")
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        await ptb_app.process_update(update)
        return {"ok": True}

    @api.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    return api


ptb = build_application()
api = create_fastapi(ptb)


def run() -> None:
    """CLI entrypoint: `automod`."""
    import uvicorn

    uvicorn.run("automod.main:api", host="0.0.0.0", port=8000, log_level=settings.log_level.lower())


if __name__ == "__main__":
    run()
