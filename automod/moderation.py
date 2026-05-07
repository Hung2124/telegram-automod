"""Group message moderation pipeline."""
from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from .classifier import classify, Verdict

log = structlog.get_logger()

# Severity → action mapping (default policy; per-group override later)
ACTION_BY_SEVERITY = {
    "high": "delete_and_mute",
    "medium": "delete",
    "low": "warn",
    "none": "noop",
}


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text:
        return
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    # TODO: load per-group rules from DB
    rules = ""

    verdict: Verdict = await classify(msg.text, group_rules=rules)
    log.info(
        "classified",
        chat_id=chat.id,
        user_id=user.id,
        category=verdict.category,
        severity=verdict.severity,
        is_violation=verdict.is_violation,
        confidence=verdict.confidence,
    )

    if not verdict.is_violation or verdict.confidence < 0.6:
        return

    action = ACTION_BY_SEVERITY.get(verdict.severity, "noop")
    try:
        if action == "delete_and_mute":
            await msg.delete()
            # 1-hour mute
            from datetime import datetime, timedelta, timezone
            until = datetime.now(timezone.utc) + timedelta(hours=1)
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                permissions={"can_send_messages": False},  # type: ignore[arg-type]
                until_date=until,
            )
        elif action == "delete":
            await msg.delete()
        elif action == "warn":
            await msg.reply_text(
                f"⚠️ @{user.username or user.first_name}: tin nhắn này có thể vi phạm "
                f"({verdict.category}). Lý do: {verdict.reason}"
            )
    except Exception as e:
        log.error("action_failed", action=action, err=str(e))

    # TODO: write to audit_log table
