import os
import json
import hmac
import hashlib
import logging
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from aiogram import Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    Update,
)
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv
from database import get_subscription, init_db, update_subscription

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TRIBUTE_API_KEY = os.getenv("TRIBUTE_API_KEY", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
COMMUNITY_INVITE_URL = os.getenv("COMMUNITY_INVITE_URL", "")
TRIBUTE_SUBSCRIBE_URL = os.getenv("TRIBUTE_SUBSCRIBE_URL", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "") or os.getenv("RENDER_EXTERNAL_URL", "")
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
TELEGRAM_WEBHOOK_PATH = os.getenv("TELEGRAM_WEBHOOK_PATH", "/telegram/webhook")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "")

if not TELEGRAM_WEBHOOK_URL:
    if APP_BASE_URL:
        TELEGRAM_WEBHOOK_URL = f"{APP_BASE_URL.rstrip('/')}{TELEGRAM_WEBHOOK_PATH}"
    elif RENDER_EXTERNAL_HOSTNAME:
        TELEGRAM_WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}{TELEGRAM_WEBHOOK_PATH}"

app = FastAPI()
bot: Any = None
dp = Dispatcher()
polling_task: asyncio.Task[Any] | None = None

BTN_INSIDE = "Что внутри"
BTN_BENEFITS = "Что я получу"
BTN_PRICE = "Сколько стоит"
BTN_JOIN = "Вступить"
BTN_ENTER_COMMUNITY = "Войти в сообщество"
BTN_MY_SUBSCRIPTION = "Моя подписка"

UNKNOWN_COMMAND_TEXT = (
    "К сожалению, такой команды не существует\n\n"
    "Доступные команды:\n"
    "/about\n"
    "/get\n"
    "/join"
)


def _parse_expires_at(expires_at: str | None) -> datetime | None:
    if not expires_at:
        return None

    normalized = expires_at.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_active_until(telegram_user_id: int) -> datetime | None:
    subscription = get_subscription(telegram_user_id)
    if subscription is None:
        return None

    _, status, expires_at_raw = subscription
    if status != "active":
        return None

    expires_at = _parse_expires_at(expires_at_raw)
    if expires_at is None:
        return None

    if expires_at <= datetime.now(timezone.utc):
        return None

    return expires_at


def _build_main_reply_keyboard(include_enter_button: bool) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = [
        [KeyboardButton(text=BTN_INSIDE), KeyboardButton(text=BTN_BENEFITS)],
        [KeyboardButton(text=BTN_PRICE), KeyboardButton(text=BTN_JOIN)],
        [KeyboardButton(text=BTN_MY_SUBSCRIPTION)],
    ]
    if include_enter_button:
        keyboard.insert(1, [KeyboardButton(text=BTN_ENTER_COMMUNITY)])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )


def _build_url_inline_button(title: str, url: str, fallback_callback: str) -> InlineKeyboardMarkup:
    if url:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=title, url=url)]]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=title, callback_data=fallback_callback)]]
    )


def _format_active_until(expires_at: datetime) -> str:
    return expires_at.strftime("%d.%m.%Y %H:%M UTC")


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    await show_start_screen(message)


async def show_start_screen(message: Message) -> None:
    if message.from_user is None:
        return

    telegram_user_id = message.from_user.id
    active_until = _get_active_until(telegram_user_id)

    if active_until is not None:
        await message.answer(
            f"Подписка активна до {_format_active_until(active_until)}",
            reply_markup=_build_main_reply_keyboard(include_enter_button=True),
        )
        return

    await message.answer(
        (
            "Привет! Это закрытое сообщество для дизайнеров.\n"
            "Здесь — практика, разборы, лекции и сильное окружение,\n"
            "которое помогает расти быстрее и не вариться в одиночку.\n\n"
            "Выбирай, что хочешь узнать."
        ),
        reply_markup=_build_main_reply_keyboard(include_enter_button=False),
    )


@dp.callback_query(F.data == "community_link_unavailable")
async def community_link_unavailable_handler(callback: CallbackQuery) -> None:
    await callback.answer("Ссылка на сообщество пока не настроена", show_alert=True)


@dp.message(F.text == BTN_INSIDE)
async def inside_handler(message: Message) -> None:
    await message.answer(
        (
            "Внутри сообщества:\n"
            "— регулярные design lab и практические разборы\n"
            "— лекции и вебинары по дизайну и карьере\n"
            "— разборы портфолио\n"
            "— общение с дизайнерами разного уровня\n"
            "— среда для системного развития"
        )
    )


@dp.message(Command("about"))
async def about_command_handler(message: Message) -> None:
    await inside_handler(message)


@dp.message(F.text == BTN_BENEFITS)
async def benefits_handler(message: Message) -> None:
    await message.answer(
        (
            "Что ты получишь:\n"
            "— больше практики, а не только теории\n"
            "— обратную связь на свои работы\n"
            "— доступ к опыту практикующих дизайнеров\n"
            "— понятную среду для роста\n"
            "— сильное профессиональное окружение"
        )
    )


@dp.message(Command("get"))
async def get_command_handler(message: Message) -> None:
    await benefits_handler(message)


@dp.message(F.text == BTN_PRICE)
async def price_handler(message: Message) -> None:
    await message.answer(
        (
            "Подписка на сообщество — 790 ₽ в месяц.\n\n"
            "Оплата происходит внутри Telegram через Tribute.\n"
            "Подписку можно отменить в любой момент."
        )
    )


@dp.message(Command("price"))
async def price_command_handler(message: Message) -> None:
    await price_handler(message)


@dp.message(F.text == BTN_JOIN)
async def join_handler(message: Message) -> None:
    await message.answer(
        "Готово. Нажми кнопку ниже, чтобы оплатить подписку и вступить в сообщество.",
        reply_markup=_build_url_inline_button(
            title="Оплатить подписку",
            url=TRIBUTE_SUBSCRIBE_URL,
            fallback_callback="subscribe_link_unavailable",
        ),
    )


@dp.message(Command("join"))
async def join_command_handler(message: Message) -> None:
    await join_handler(message)


@dp.message(F.text == BTN_MY_SUBSCRIPTION)
async def my_subscription_handler(message: Message) -> None:
    if message.from_user is None:
        return
    active_until = _get_active_until(message.from_user.id)
    if active_until is None:
        await message.answer("У тебя пока нет активной подписки.")
        return
    await message.answer(f"Подписка активна до {_format_active_until(active_until)}")


@dp.message(Command("mysubscribe"))
async def mysubscribe_command_handler(message: Message) -> None:
    await my_subscription_handler(message)


@dp.message(F.text.regexp(r"^/[^\s]+"))
async def unknown_command_handler(message: Message) -> None:
    await message.answer(UNKNOWN_COMMAND_TEXT)


@dp.message(F.text == BTN_ENTER_COMMUNITY)
async def enter_community_handler(message: Message) -> None:
    if message.from_user is None:
        return

    active_until = _get_active_until(message.from_user.id)
    if active_until is None:
        await message.answer("Подписка не активна. Нажми «Вступить», чтобы оплатить доступ.")
        return

    await message.answer(
        f"Подписка активна до {_format_active_until(active_until)}",
        reply_markup=_build_url_inline_button(
            title=BTN_ENTER_COMMUNITY,
            url=COMMUNITY_INVITE_URL,
            fallback_callback="community_link_unavailable",
        ),
    )


@dp.callback_query(F.data == "subscribe_link_unavailable")
async def subscribe_link_unavailable_handler(callback: CallbackQuery) -> None:
    await callback.answer("Ссылка на оплату пока не настроена", show_alert=True)


@dp.callback_query()
async def menu_placeholder_handler(callback: CallbackQuery) -> None:
    await callback.answer("Раздел в разработке")


@app.on_event("startup")
async def startup_event():
    global bot, polling_task
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

            allowed_updates = dp.resolve_used_update_types()
            if TELEGRAM_WEBHOOK_URL:
                await bot.set_webhook(
                    url=TELEGRAM_WEBHOOK_URL,
                    allowed_updates=allowed_updates,
                    secret_token=TELEGRAM_WEBHOOK_SECRET or None,
                )
                logger.info("Telegram webhook set to %s", TELEGRAM_WEBHOOK_URL)
            else:
                await bot.delete_webhook(drop_pending_updates=False)
                polling_task = asyncio.create_task(
                    dp.start_polling(bot, allowed_updates=allowed_updates)
                )
                logger.info("Bot polling started (no webhook url configured)")
        except Exception:
            bot = None
            logger.exception("Invalid BOT_TOKEN; admin notifications are disabled")

    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN is empty; admin notifications are disabled")
    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID is empty; admin notifications are disabled")


@app.on_event("shutdown")
async def shutdown_event():
    global polling_task

    if polling_task is not None:
        polling_task.cancel()
        with suppress(asyncio.CancelledError):
            await polling_task
        polling_task = None

    if bot is not None:
        await bot.session.close()


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot is not initialized")

    if TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Telegram webhook payload")

    update = Update.model_validate(data)
    asyncio.create_task(_process_telegram_update(update))
    return {"ok": True}


async def _process_telegram_update(update: Update) -> None:
    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Failed to process Telegram update")


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
