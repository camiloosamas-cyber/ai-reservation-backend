# /backend/chatbase_bridge.py
import os, json, shutil, httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(tags=["Chatbase Integration"])

MEMORY_FILE = "chat_memory.json"

# ---------- Models ----------
class ChatbaseIn(BaseModel):
    message: str
    user_id: str | None = "guest"

class ChatbaseOut(BaseModel):
    reply: str
    context_summary: str
    raw: dict


# ---------- Memory Handling ----------
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_memory(messages):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages[-15:], f, indent=2)
    shutil.copy(MEMORY_FILE, "static/chat_memory.json")


# ---------- Context Builder ----------
def build_context(memory):
    """Turn last messages into a natural readable conversation."""
    if not memory:
        return "User just started chatting for the first time."
    context = ""
    for msg in memory[-10:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        context += f"{role}: {msg['content']}\n"
    return context.strip()


# ---------- Chatbase API Call ----------
async def call_chatbase(agent_id, api_key, message, memory):
    """Send message to Chatbase but include our own memory context."""
    url = "https://www.chatbase.co/api/v1/chat"
    context = build_context(memory)
    combined_prompt = (
        f"Context of previous conversation:\n{context}\n\n"
        f"Now user says: {message}\n"
        "Please respond naturally, staying consistent with past conversation."
    )

    payload = {
        "messages": [{"role": "user", "content": combined_prompt}],
        "chatbotId": agent_id,
        "stream": False
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


# ---------- Main Route ----------
@router.post("/chatbase_bridge", response_model=ChatbaseOut)
async def chatbase_bridge(body: ChatbaseIn):
    """Handles AI messages with local memory context."""
    agent_id = os.getenv("CHATBASE_AGENT_ID")
    api_key = os.getenv("CHATBASE_API_KEY")
    if not agent_id or not api_key:
        raise HTTPException(status_code=500, detail="Missing Chatbase credentials")

    # Load chat memory
    memory = load_memory()

    # Call Chatbase with context
    response = await call_chatbase(agent_id, api_key, body.message, memory)
    reply = response.get("text") or response.get("output_text") or "I'm not sure, could you clarify?"

    # Save updated memory
    memory.append({"role": "user", "content": body.message})
    memory.append({"role": "assistant", "content": reply})
    save_memory(memory)

    # Create summary text for dashboard display
    summary = f"💬 Memory length: {len(memory)} messages. Last updated: {datetime.now().strftime('%H:%M:%S')}."

    return ChatbaseOut(reply=reply, context_summary=summary, raw=response)
