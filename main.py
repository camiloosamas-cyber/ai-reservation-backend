# /backend/main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv

# --- Database integration ---
from database import init_db, add_reservation, get_reservations, update_status
init_db()

# Local imports
from chatbase_bridge import router as chatbase_router  # ✅ Chatbase integration

# --- Load environment variables ---
load_dotenv()

# --- App setup ---
app = FastAPI(title="AI Reservation Backend")

# Allow dashboard JavaScript to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins (for local dev)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static + Templates ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Models ---
class Customer(BaseModel):
    name: str
    email: str

class BookingRequest(BaseModel):
    business_id: str
    datetime: str
    party_size: int
    customer: Customer

class CancelRequest(BaseModel):
    reservation_id: str
    customer_email: Optional[str] = None


# --- Endpoints ---

@app.post("/book")
def book(request: BookingRequest):
    """Create a new reservation."""
    reservation = {
        "reservation_id": "RES-" + datetime.now().strftime("%H%M%S"),
        "datetime": request.datetime,
        "business": request.business_id,
        "party_size": request.party_size,
        "customer_name": request.customer.name,
        "customer_email": request.customer.email,
        "status": "confirmed",
    }

    add_reservation(reservation)
    return {"success": True, "message": "Reservation saved successfully.", **reservation}


@app.post("/cancelReservation")
def cancel_reservation(data: dict):
    """Cancel an existing reservation."""
    print("🧾 Cancel request received:", data)
    reservation_id = data.get("reservation_id")

    if not reservation_id:
        return {"success": False, "error": "Missing reservation_id"}

    success = update_status(reservation_id, "cancelled")
    if success:
        print(f"✅ Reservation {reservation_id} was cancelled.")
        return {"success": True, "message": f"Reservation {reservation_id} cancelled successfully."}
    else:
        print(f"⚠️ Reservation {reservation_id} not found.")
        return {"success": False, "error": "Reservation not found"}


@app.post("/updateReservation")
def update_reservation(data: dict):
    """Update an existing reservation's datetime or party size."""
    reservation_id = data.get("reservation_id")
    new_datetime = data.get("datetime")
    new_party_size = data.get("party_size")

    if not reservation_id:
        return {"success": False, "error": "Missing reservation_id"}

    import sqlite3
    conn = sqlite3.connect("reservations.db")
    cur = conn.cursor()

    # Update fields if provided
    fields = []
    values = []
    if new_datetime:
        fields.append("datetime = ?")
        values.append(new_datetime)
    if new_party_size:
        fields.append("party_size = ?")
        values.append(new_party_size)
    if fields:
        fields.append("status = ?")
        values.append("updated")
        values.append(reservation_id)
        cur.execute(f"UPDATE reservations SET {', '.join(fields)} WHERE reservation_id = ?", tuple(values))
        conn.commit()

    updated = cur.rowcount > 0
    conn.close()

    if updated:
        return {"success": True, "message": f"Reservation {reservation_id} updated successfully."}
    return {"success": False, "error": "Reservation not found"}


@app.get("/getAvailability")
def get_availability(business_id: str, date: Optional[str] = None):
    """Return available time slots for a business."""
    slots = ["18:00", "19:00", "20:00", "21:00"]
    return {"success": True, "business_id": business_id, "date": date or "today", "available_slots": slots}


@app.post("/process_message")
def process_message(data: dict):
    """Mock endpoint used for testing message intent logic."""
    message = data.get("message", "").lower()
    print("💬 Message received:", message)

    if "book" in message:
        return {"reply": "Got it! How many people and what time?"}
    elif "cancel" in message:
        return {"reply": "Sure, please provide your reservation ID."}
    else:
        return {"reply": "I'm your restaurant assistant — you can say 'book a table' or 'cancel my booking'."}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the reservations dashboard."""
    reservations = get_reservations()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "reservations": reservations}
    )

# ✅ Include Chatbase bridge routes
app.include_router(chatbase_router)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Redirect the root URL to the dashboard page."""
    reservations = get_reservations()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "reservations": reservations}
    )

@app.get("/ping")
def ping():
    """Health check route to confirm backend is running."""
    return {"status": "✅ Online", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
