import requests
import sqlite3
from datetime import datetime
import os
import time

# --- CONFIGURATION ---
API_KEY = os.getenv("HYPIXEL_API_KEY")
GUILD_NAME = "Specialstyrken"
# Matches the Docker volume path
DB_NAME = os.getenv("DB_NAME", "/app/data/guild_data.db")
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
            UNIQUE(uuid, date)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            uuid TEXT PRIMARY KEY,
            username TEXT
        )
    ''')
    conn.commit()
    return conn

def get_guild_data():
    url = f"https://api.hypixel.net/v2/guild?name={GUILD_NAME}"
    headers = {"Api-Key": API_KEY}
    response = requests.get(url, headers=headers)
    return response.json()

def get_username(uuid):
    try:
        url = f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
        res = requests.get(url)
        if res.status_code == 200:
            return res.json().get("name")
        elif res.status_code == 429:
            print(f"Rate limited by Mojang for {uuid}. Sleeping...")
            time.sleep(5)
    except Exception as e:
        print(f"Failed to fetch name for {uuid}: {e}")
    return None

def update_player_names(conn, member_list):
    cursor = conn.cursor()
    new_names = 0
    for member in member_list:
        uuid = member.get("uuid")
        cursor.execute("SELECT username FROM players WHERE uuid = ?", (uuid,))
        if cursor.fetchone() is None:
            name = get_username(uuid)
            if name:
                cursor.execute("INSERT INTO players (uuid, username) VALUES (?, ?)", (uuid, name))
                new_names += 1
                print(f"[+] Discovered new player: {name}")
                time.sleep(0.5) # Prevent Mojang API spam
    conn.commit()
    if new_names > 0:
        print(f"[*] Added {new_names} new names to the database.")

def save_to_db(conn, member_list):
    cursor = conn.cursor()
    today_key = datetime.now().strftime('%Y-%m-%d')
    for member in member_list:
        uuid = member.get("uuid")
        exp_history = member.get("expHistory", {})
        today_exp = exp_history.get(today_key, 0)

        cursor.execute('''
            INSERT OR IGNORE INTO daily_gexp (uuid, daily_gexp, date)
            VALUES (?, ?, ?)
        ''', (uuid, today_exp, today_key))
    conn.commit()
    print(f"[*] Logged GEXP for {len(member_list)} members.")

def main():
    if not API_KEY:
        print("Error: HYPIXEL_API_KEY environment variable not set.")
        return

    data = get_guild_data()
    if data.get("success") and data.get("guild"):
        conn = init_db()
        members = data["guild"]["members"]
        
        update_player_names(conn, members)
        save_to_db(conn, members)
        
        conn.close()
    else:
        print("Error: Could not fetch data. Check API key/Guild name.")

if __name__ == "__main__":
    main()
