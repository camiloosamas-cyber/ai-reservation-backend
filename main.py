from fastapi import FastAPI, Request, WebSocket, Form, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import json
import os

# ✅ OpenAI SDK (WhatsApp AI brain)
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ✅ Supabase SDK (Database)
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")  # store secret role here

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

app = FastAPI()

# Static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Models ----------------
class UpdateReservation(BaseModel):
    reservation_id: int
    datetime: Optional[str] = None
    party_size: Optional[int] = None
    table_number: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class CancelReservation(BaseModel):
    reservation_id: int


# ---------------- Utils ----------------
def parse_dt(d: str):
    """Parses ISO/normal datetime formats for analytics."""
    try:
        if d.endswith("Z"):
            d = d.replace("Z", "+00:00")
        return datetime.fromisoformat(d).replace(tzinfo=None)
    except:
        return None


# ---------------- Supabase Data Access ----------------
def supa_get_reservations():
    res = supabase.table("reservations").select("*").order("datetime", desc=True).execute()
    return res.data


def supa_get_analytics():
    rows = supa_get_reservations()
    if not rows:
        return {"weekly_count": 0, "avg_party_size": 0, "peak_time": "N/A", "cancel_rate": 0}

    now = datetime.now()
    week_ago = now - timedelta(days=7)

    weekly, cancelled = 0, 0
    times, party_vals = [], []

    for r in rows:
        if r.get("party_size"):
            party_vals.append(int(r["party_size"]))

        dt = parse_dt(r.get("datetime", ""))
        if dt:
            if dt > week_ago:
                weekly += 1
            times.append(dt.strftime("%H:%M"))

        if r.get("status") == "cancelled":
            cancelled += 1

    return {
        "weekly_count": weekly,
        "avg_party_size": round(sum(party_vals) / len(party_vals), 1) if party_vals else 0,
        "peak_time": max(set(times), key=times.count) if times else "N/A",
        "cancel_rate": round((cancelled / len(rows)) * 100, 1),
    }


# ---------------- ROUTES ----------------
@app.get("/", response_class=HTMLResponse)
def home():
    return "<h3>✅ Backend Live + Connected to Supabase</h3><p>Open <a href='/dashboard'>/dashboard</a></p>"


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "reservations": supa_get_reservations(),
            **supa_get_analytics(),
            "parse_dt": parse_dt,
            "timedelta": timedelta,
        },
    )


# ---------------- WhatsApp Webhook → AI → Supabase ----------------
@app.post("/whatsapp")
async def whatsapp_webhook(Body: str = Form(...)):
    print("📩 Incoming WhatsApp:", Body)

    prompt = """
You are an AI restaurant reservation assistant.
EXTRACT the reservation details and return ONLY JSON with this format:

{
  "customer_name": "",
  "customer_email": "",
  "contact_phone": "",
  "party_size": "",
  "datetime": "",
  "table_number": "",
  "notes": ""
}

❗ If ANY required info is missing, reply ONLY:
{"ask": "<short question>"}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": Body},
            ],
        )

        msg = resp.choices[0].message.content.strip()

        if msg.startswith("```"):
            msg = msg.replace("```json", "").replace("```", "").strip()

        print("🔍 AI JSON:", msg)
        data = json.loads(msg)

    except Exception as e:
        print("❌ AI JSON ERROR:", e)
        return Response(
            content="<Response><Message>Sorry, can you repeat that?</Message></Response>",
            media_type="application/xml",
        )

    if "ask" in data:
        return Response(
            content=f"<Response><Message>{data['ask']}</Message></Response>",
            media_type="application/xml",
        )

    # ✅ Insert into Supabase
    supabase.table("reservations").insert({
        "customer_name": data.get("customer_name"),
        "customer_email": data.get("customer_email") or "",
        "contact_phone": data.get("contact_phone") or "",
        "datetime": data.get("datetime"),
        "party_size": int(data.get("party_size")),
        "table_number": data.get("table_number") or "",
        "notes": data.get("notes") or "",
        "status": "confirmed"
    }).execute()

    await notify({"type": "refresh"})

    return Response(
        content=f"<Response><Message>✅ Reservation created for {data['customer_name']} on {data['datetime']}.</Message></Response>",
        media_type="application/xml",
    )


# ---------------- Update / Cancel Reservation ----------------
@app.post("/updateReservation")
async def update_reservation(data: UpdateReservation):
    update_data = {k: v for k, v in data.dict().items() if v is not None and k != "reservation_id"}

    supabase.table("reservations").update(update_data).eq("reservation_id", data.reservation_id).execute()

    await notify({"type": "refresh"})
    return {"message": "updated"}


@app.post("/cancelReservation")
async def cancel_reservation(data: CancelReservation):
    supabase.table("reservations").update({"status": "cancelled"}).eq("reservation_id", data.reservation_id).execute()

    await notify({"type": "refresh"})
    return {"message": "cancelled"}


# ---------------- RESET DB (Clear all) ----------------
@app.post("/resetReservations")
async def reset_reservations():
    supabase.table("reservations").delete().neq("reservation_id", 0).execute()
    return {"message": "✅ All reservations cleared"}


# ---------------- WebSocket to refresh dashboard live ----------------
clients = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        clients.remove(websocket)


async def notify(message: dict):
    for ws in clients:
        try:
            await ws.send_text(json.dumps(message))
        except:
            pass
