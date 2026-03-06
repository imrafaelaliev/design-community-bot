import os
import json
import hmac
import hashlib
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TRIBUTE_API_KEY = os.getenv("TRIBUTE_API_KEY", "")

app = FastAPI()


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

    event_name = webhook.get("name")
    event_payload = webhook.get("payload", {})

    logger.info("Tribute event name: %s", event_name)
    logger.info("Tribute event payload: %s", event_payload)

    telegram_user_id = event_payload.get("telegram_user_id")
    expires_at = event_payload.get("expires_at")

    if event_name == "new_subscription":
        logger.info(
            "NEW SUBSCRIPTION | telegram_user_id=%s | expires_at=%s",
            telegram_user_id,
            expires_at,
        )

    elif event_name == "renewed_subscription":
        logger.info(
            "RENEWED SUBSCRIPTION | telegram_user_id=%s | expires_at=%s",
            telegram_user_id,
            expires_at,
        )

    elif event_name == "cancelled_subscription":
        logger.info(
            "CANCELLED SUBSCRIPTION | telegram_user_id=%s | expires_at=%s",
            telegram_user_id,
            expires_at,
        )

    else:
        logger.warning("Unknown event: %s", event_name)

    return {"status": "ok"}
