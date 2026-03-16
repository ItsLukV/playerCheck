import requests
import sqlite3
import os
from datetime import datetime

# --- CONFIGURATION ---
API_KEY = os.getenv("HYPIXEL_API_KEY", "f1ef289e-d862-41d0-8ad7-dc6a0f9a04d5")
GUILD_NAME = "Specialstyrken"
DB_NAME = os.getenv("DB_NAME", "data/guild_data.db")
# ---------------------

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_gexp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            daily_gexp INTEGER,
            date TEXT,
            UNIQUE(uuid, date) -- Prevents duplicate entries if run twice
        )
    ''')
    conn.commit()
    return conn

def backfill():
    url = f"https://api.hypixel.net/v2/guild?name={GUILD_NAME}"
    headers = {"Api-Key": API_KEY}
    response = requests.get(url, headers=headers).json()

    if not response.get("success") or not response.get("guild"):
        print("Error: Could not fetch guild data.")
        return

    conn = init_db()
    cursor = conn.cursor()
    members = response["guild"]["members"]
    entries_added = 0

    for member in members:
        uuid = member.get("uuid")
        exp_history = member.get("expHistory", {})

        for date_str, gexp_value in exp_history.items():
            try:
                # Use INSERT OR IGNORE to avoid errors if the date already exists
                cursor.execute('''
                    INSERT OR IGNORE INTO daily_gexp (uuid, daily_gexp, date)
                    VALUES (?, ?, ?)
                ''', (uuid, gexp_value, date_str))
                if cursor.rowcount > 0:
                    entries_added += 1
            except sqlite3.Error as e:
                print(f"DB Error: {e}")

    conn.commit()
    conn.close()
    print(f"[*] Backfill complete! Added {entries_added} historical records.")

if __name__ == "__main__":
    backfill()
