import json
from pathlib import Path
from typing import List, Dict, Any

DATA_FILE = Path("reservations.json")


def load_reservations() -> List[Dict[str, Any]]:
    """Return all reservations as a list of dicts."""
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_reservation(reservation: Dict[str, Any]) -> None:
    """Append a reservation to the file."""
    data = load_reservations()
    data.append(reservation)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_reservation_status(reservation_id: str, new_status: str) -> bool:
    """Update the status of a reservation in the JSON file."""
    data = load_reservations()
    updated = False

    for r in data:
        if r.get("reservation_id") == reservation_id:
            r["status"] = new_status
            updated = True
            break

    if updated:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return updated

