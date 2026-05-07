"""Telegram command handlers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Xin chào! Tôi là **Auto-Mod** — bot kiểm duyệt group bằng AI.\n\n"
        "Thêm tôi vào group, cấp quyền **Delete messages + Restrict users**, "
        "rồi gõ /automod để cấu hình.\n\n"
        "📦 Free: 1 group, 500 tin/tháng. Pro $9/group/tháng.",
        parse_mode="Markdown",
    )


async def cmd_automod(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Lệnh này chỉ dùng trong group.")
        return
    # TODO: show inline keyboard for rule config
    await update.message.reply_text(
        f"⚙️ Cấu hình Auto-Mod cho **{chat.title}**\n\n"
        "(coming soon — đang build inline keyboard cho rules)",
        parse_mode="Markdown",
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    # TODO: query audit_log table
    await update.message.reply_text(
        f"📊 Stats {chat.title or 'this chat'}\n\n"
        "Tính năng sẽ available sau khi DB schema xong.",
    )
