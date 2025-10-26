# /backend/chatbase_bridge.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import httpx
import json
from datetime import datetime
from database import add_reservation

router = APIRouter(tags=["Chatbase Integration"])

# ---------- Models ----------
class ChatbaseIn(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None

class ChatbaseOut(BaseModel):
    reply: str
    raw: dict

# ---------- Helpers ----------
def _get_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val

def _headers() -> dict:
    key = _get_env("CHATBASE_API_KEY")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

def _build_payload_openai_style(agent_id: str, message: str, session_id: str | None, user_id: str | None) -> dict:
    payload = {
        "messages": [{"role": "user", "content": message}],
        "agent_id": agent_id,
    }
    if session_id:
        payload["session_id"] = session_id
    if user_id:
        payload["user_id"] = user_id
    return payload

# ---------- Route ----------
@router.post("/chatbase_bridge", response_model=ChatbaseOut)
async def chatbase_bridge(data: ChatbaseIn):
    CHATBASE_API_KEY = _get_env("CHATBASE_API_KEY")
    CHATBASE_AGENT_ID = _get_env("CHATBASE_AGENT_ID")

    payload = _build_payload_openai_style(
        CHATBASE_AGENT_ID, data.message, data.session_id, data.user_id
    )

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://www.chatbase.co/api/v1/chat",
            headers=_headers(),
            json=payload,
        )

    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)

    raw_response = res.json()
    reply = raw_response.get("message", "No reply received.")

    # --- 🔥 Try to detect reservation intent ---
    try:
        parsed = json.loads(reply)
        if isinstance(parsed, dict) and parsed.get("intent") == "book_reservation":
            data = parsed.get("data", {})
            reservation = {
                "reservation_id": "RES-" + datetime.now().strftime("%H%M%S"),
                "datetime": data.get("datetime", datetime.now().strftime("%Y-%m-%dT%H:%M")),
                "business": data.get("business_id", "DefaultBiz"),
                "party_size": int(data.get("party_size", 2)),
                "customer_name": data.get("name", "Guest"),
                "customer_email": data.get("email", "guest@example.com"),
                "status": "confirmed",
            }
            add_reservation(reservation)
            reply = f"✅ Reservation created for {reservation['customer_name']} on {reservation['datetime']} for {reservation['party_size']} people."
    except Exception:
        pass  # Normal text replies continue as usual

    return ChatbaseOut(reply=reply, raw=raw_response)
