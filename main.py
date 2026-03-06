from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok"}
from fastapi import FastAPI, Request, Header, HTTPException
import hmac
import hashlib
import os

app = FastAPI()

TRIBUTE_API_KEY = os.getenv("TRIBUTE_API_KEY", "")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/tribute/webhook")
async def tribute_webhook(
    request: Request,
    trbt_signature: str | None = Header(default=None)
):
    raw_body = await request.body()

    if not trbt_signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    expected_signature = hmac.new(
        TRIBUTE_API_KEY.encode(),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, trbt_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    event = payload.get("event")
    data = payload.get("data", {})

    print("Tribute webhook received:", event, data)

    return {"ok": True}
