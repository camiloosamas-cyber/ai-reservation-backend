import sqlite3
from datetime import datetime

DB_FILE = "reservations.db"

def init_db():
    """Create table if it doesn’t exist."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id TEXT UNIQUE,
            business TEXT,
            datetime TEXT,
            party_size INTEGER,
            customer_name TEXT,
            customer_email TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_reservation(res):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO reservations (reservation_id, business, datetime, party_size, customer_name, customer_email, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        res["reservation_id"],
        res["business"],
        res["datetime"],
        res["party_size"],
        res["customer_name"],
        res["customer_email"],
        res["status"],
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

def get_reservations():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT reservation_id, datetime, business, party_size, customer_name, customer_email, status FROM reservations ORDER BY datetime DESC")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "reservation_id": r[0],
            "datetime": r[1],
            "business": r[2],
            "party_size": r[3],
            "customer_name": r[4],
            "customer_email": r[5],
            "status": r[6],
        }
        for r in rows
    ]

def update_status(reservation_id, new_status):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE reservations SET status=? WHERE reservation_id=?", (new_status, reservation_id))
    conn.commit()
    conn.close()
    return cur.rowcount > 0
