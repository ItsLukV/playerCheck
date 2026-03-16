import requests
import sqlite3
from datetime import datetime
import json

# --- CONFIGURATION ---
API_KEY = "f1ef289e-d862-41d0-8ad7-dc6a0f9a04d5"
GUILD_NAME = "Specialstyrken"
DB_NAME = "guild_data.db"
# ---------------------

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Simplified table to just track daily snapshots
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_gexp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            daily_gexp INTEGER,
            date TEXT
        )
    ''')
    conn.commit()
    return conn

def get_guild_data():
    url = f"https://api.hypixel.net/v2/guild?name={GUILD_NAME}"
    headers = {"Api-Key": API_KEY}
    response = requests.get(url, headers=headers)
    return response.json()

def save_to_db(conn, member_list):
    cursor = conn.cursor()
    
    # Hypixel uses YYYY-MM-DD for keys in expHistory
    today_key = datetime.now().strftime('%Y-%m-%d')
    
    for member in member_list:
        uuid = member.get("uuid")
        exp_history = member.get("expHistory", {})
        
        # Get today's value, default to 0 if the key doesn't exist yet
        today_exp = exp_history.get(today_key, 0)
        
        cursor.execute('''
            INSERT INTO daily_gexp (uuid, daily_gexp, date)
            VALUES (?, ?, ?)
        ''', (uuid, today_exp, today_key))
    
    conn.commit()
    print(f"[*] Logged today's GEXP ({today_key}) for {len(member_list)} members.")

def main():
    data = get_guild_data()
    if data.get("success") and data.get("guild"):
        print(json.dumps(data, indent=4))
        conn = init_db()
        save_to_db(conn, data["guild"]["members"])
        conn.close()
    else:
        print("Error: Could not fetch data. Check API key/Guild name.")

if __name__ == "__main__":
    main()
