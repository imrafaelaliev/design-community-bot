import os
import json
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv
from database import init_db, update_subscription

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TRIBUTE_API_KEY = os.getenv("TRIBUTE_API_KEY", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

app = FastAPI()
bot: Any = None


@app.on_event("startup")
async def startup_event():
    global bot
    try:
        init_db()
        logger.info("SQLite initialized")
    except Exception:
        logger.exception("Failed to initialize SQLite; service will keep running")

    if BOT_TOKEN:
        try:
            from aiogram import Bot as AiogramBot

            bot = AiogramBot(token=BOT_TOKEN)
            logger.info("Bot client initialized")
        except Exception:
            bot = None
            logger.exception("Invalid BOT_TOKEN; admin notifications are disabled")

    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN is empty; admin notifications are disabled")
    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID is empty; admin notifications are disabled")


@app.on_event("shutdown")
async def shutdown_event():
    if bot is not None:
        await bot.session.close()


async def notify_admin_about_cancelled_subscription(
    telegram_user_id: int,
    expires_at: str | None,
) -> None:
    if bot is None or not ADMIN_CHAT_ID:
        return

    text = (
        "Отмена подписки\n"
        f"user_id: {telegram_user_id}\n"
        f"expires_at: {expires_at or 'не передан'}"
    )

    try:
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)
    except Exception:
        logger.exception(
            "Failed to send cancellation notification to ADMIN_CHAT_ID=%s",
            ADMIN_CHAT_ID,
        )


def verify_tribute_signature(raw_body: bytes, signature: str | None) -> bool:
    if not signature:
        logger.warning("Missing trbt-signature header")
        return False

    if not TRIBUTE_API_KEY:
        logger.warning("TRIBUTE_API_KEY is empty")
        return False

    expected_signature = hmac.new(
        TRIBUTE_API_KEY.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    is_valid = hmac.compare_digest(expected_signature, signature)

    if not is_valid:
        logger.warning("Invalid signature")
        logger.warning("Expected: %s", expected_signature)
        logger.warning("Received: %s", signature)

    return is_valid


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "design-community-bot",
        "time_utc": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/tribute/webhook")
async def tribute_webhook(
    request: Request,
    trbt_signature: str | None = Header(default=None),
):
    raw_body = await request.body()

    logger.info("Webhook request received")

    if not verify_tribute_signature(raw_body, trbt_signature):
        raise HTTPException(status_code=401, detail="Invalid Tribute signature")

    try:
        webhook = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_name = webhook.get("name") or webhook.get("event")
    event_payload = webhook.get("payload", {})

    logger.info("Tribute event name: %s", event_name)
    logger.info("Tribute event payload: %s", event_payload)

    telegram_user_id = event_payload.get("telegram_user_id")
    expires_at = event_payload.get("expires_at")

    if telegram_user_id is None:
        raise HTTPException(status_code=400, detail="telegram_user_id is missing")
    try:
        telegram_user_id = int(telegram_user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="telegram_user_id must be integer")

    if event_name == "new_subscription":
        update_subscription(telegram_user_id, "active", expires_at)
        logger.info(
            "NEW SUBSCRIPTION | telegram_user_id=%s | expires_at=%s",
            telegram_user_id,
            expires_at,
        )

    elif event_name == "renewed_subscription":
        update_subscription(telegram_user_id, "active", expires_at)
        logger.info(
            "RENEWED SUBSCRIPTION | telegram_user_id=%s | expires_at=%s",
            telegram_user_id,
            expires_at,
        )

    elif event_name == "cancelled_subscription":
        update_subscription(telegram_user_id, "cancelled", expires_at)
        await notify_admin_about_cancelled_subscription(telegram_user_id, expires_at)
        logger.info(
            "CANCELLED SUBSCRIPTION | telegram_user_id=%s | expires_at=%s",
            telegram_user_id,
            expires_at,
        )

    else:
        logger.warning("Unknown event: %s", event_name)

    return {"status": "ok"}
