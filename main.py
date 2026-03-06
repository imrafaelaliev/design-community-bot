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
COMMUNITY_INVITE_LINK = os.getenv("COMMUNITY_INVITE_LINK", "")

app = FastAPI()


def verify_tribute_signature(raw_body: bytes, signature: str | None) -> bool:
    if not signature or not TRIBUTE_API_KEY:
        return False

    expected_signature = hmac.new(
        TRIBUTE_API_KEY.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


def parse_expires_at(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        # Tribute обычно шлет ISO-дату
        # Поддержим формат с Z
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:
        logger.warning("Could not parse expires_at: %s", value)
        return None


def handle_new_subscription(payload: dict) -> None:
    data = payload.get("data", payload)

    telegram_user_id = data.get("telegram_user_id")
    expires_at = parse_expires_at(data.get("expires_at"))

    logger.info(
        "NEW SUBSCRIPTION | user_id=%s | expires_at=%s",
        telegram_user_id,
        expires_at,
    )

    # TODO:
    # 1. сохранить/обновить пользователя в БД
    # 2. выставить subscription_status = "active"
    # 3. сохранить expires_at
    # 4. при желании отправить человеку welcome-сообщение / ссылку в сообщество


def handle_renewed_subscription(payload: dict) -> None:
    data = payload.get("data", payload)

    telegram_user_id = data.get("telegram_user_id")
    expires_at = parse_expires_at(data.get("expires_at"))

    logger.info(
        "RENEWED SUBSCRIPTION | user_id=%s | expires_at=%s",
        telegram_user_id,
        expires_at,
    )

    # TODO:
    # 1. обновить expires_at в БД
    # 2. оставить subscription_status = "active"


def handle_cancelled_subscription(payload: dict) -> None:
    data = payload.get("data", payload)

    telegram_user_id = data.get("telegram_user_id")
    expires_at = parse_expires_at(data.get("expires_at"))

    logger.info(
        "CANCELLED SUBSCRIPTION | user_id=%s | expires_at=%s",
        telegram_user_id,
        expires_at,
    )

    # TODO:
    # 1. обновить subscription_status = "cancelled"
    # 2. expires_at оставить, чтобы доступ жил до конца оплаченного периода
    # 3. не удалять доступ мгновенно, если период еще не закончился


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

    if not verify_tribute_signature(raw_body, trbt_signature):
        raise HTTPException(status_code=401, detail="Invalid Tribute signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event")

    logger.info("Tribute webhook received: %s", event)
    logger.info("Payload: %s", payload)

    if event == "new_subscription":
        handle_new_subscription(payload)

    elif event == "renewed_subscription":
        handle_renewed_subscription(payload)

    elif event == "cancelled_subscription":
        handle_cancelled_subscription(payload)

    else:
        logger.warning("Unknown Tribute event: %s", event)

    return {"ok": True}
