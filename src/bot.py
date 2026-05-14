#!/usr/bin/env python3
"""Tara Bot — Telegram bot entry point with Webhook support for Render."""

from __future__ import annotations

import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from .config import Config
from .agents import Agent

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("tara-bot")


# ── In-memory sessions ───────────────────────────────────────────────

sessions: dict[int, Agent] = {}


def get_agent(user_id: int) -> Agent:
    """Get or create an agent session for a user."""
    if user_id not in sessions:
        sessions[user_id] = Agent()
    return sessions[user_id]


# ── Authorization ────────────────────────────────────────────────────

def is_allowed(user_id: int) -> bool:
    allowed = Config.allowed_user_id
    if not allowed:
        return True  # no restriction set
    return str(user_id) in allowed.split(",")


def authorize(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else 0
    if not is_allowed(uid):
        log.warning(f"Blocked unauthorized access: {uid}")
        return False
    return True


# ── Handlers ─────────────────────────────────────────────────────────

async def start(update: Update, _context) -> None:
    if not authorize(update):
        await update.message.reply_text(
            "⛔ Bạn không phải chủ bot này."
        )
        return

    await update.message.reply_text(
        "👋 *Tara Bot — Săn giá, tìm deal*\n\n"
        "Mình có thể:\n"
        "✈️ Tìm vé máy bay: *\"vé SG Đà Nẵng cuối tuần\"*\n"
        "🛒 So sánh giá: *\"iPhone 16 giá bao nhiêu\"*\n\n"
        "Thử đi ạ!",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, _context) -> None:
    if not authorize(update):
        return

    uid = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

    log.info(f"[{uid}] {text}")

    # Show typing while thinking
    await update.message.chat.send_action("typing")

    try:
        agent = get_agent(uid)
        reply = agent.chat(text)

        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        log.exception("Error processing message")
        await update.message.reply_text(
            f"😵 Có lỗi xảy ra: {e}\nThử lại sau nhé!"
        )


async def reset(update: Update, _context) -> None:
    """Reset conversation history."""
    if not authorize(update):
        return
    uid = update.effective_user.id
    if uid in sessions:
        del sessions[uid]
    await update.message.reply_text("🔄 Đã reset conversation.")


async def uptime(update: Update, _context) -> None:
    """Show a simple health check — useful for monitoring."""
    if not authorize(update):
        return
    await update.message.reply_text(
        f"✅ Tara Bot đang chạy | "
        f"{len(sessions)} active session(s)"
    )


# ── Health check HTTP server (for Polling mode) ──────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    """Minimal health endpoint."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, fmt, *args) -> None:
        pass  # silence log spam


def run_health_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    log.info(f"Health server listening on :{port}")
    server.serve_forever()


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    token = Config.telegram_token
    if not token:
        raise SystemExit("TELEGRAM_TOKEN not set")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("uptime", uptime))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Render detection
    port = int(os.environ.get("PORT", "8080"))
    url = os.environ.get("RENDER_EXTERNAL_URL")

    if url:
        # Webhook mode for Render
        log.info(f"🚀 Starting Webhook on {url}:{port}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"{url}/{token}",
        )
    else:
        # Polling mode for Local/Fly.io
        log.info("🚀 Starting Polling mode")
        # Start health server in background thread for health checks
        t = threading.Thread(target=run_health_server, args=(port,), daemon=True)
        t.start()
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
