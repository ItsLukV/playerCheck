import os
import sqlite3
import time
from datetime import datetime

import requests

# CONFIGURATION
API_KEY = os.getenv("HYPIXEL_API_KEY")
GUILD_NAME = "Specialstyrken"
DB_NAME = os.getenv("DB_NAME", "/app/data/guild_data.db")

_print = print


def print(*args, **kwargs):
    # Get the current time formatted as HH:MM:SS
    current_time = datetime.now().strftime("[%H:%M:%S]")

    # Call the original print, passing the timestamp first
    _print(current_time, *args, **kwargs)


# --- Test it out ---
print("Hello, world!")
print("This has a timestamp.")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_gexp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            daily_gexp INTEGER,
            date TEXT,
            UNIQUE(uuid, date)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hourly_gexp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            gexp INTEGER,
            date TEXT,
            hour TEXT,
            UNIQUE(uuid, hour)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            uuid TEXT PRIMARY KEY,
            username TEXT
        )
    """)

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='skyblock_stats'"
    )
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(skyblock_stats)")
        columns = {row[1] for row in cursor.fetchall()}
        if "profile_id" not in columns:
            print("[*] Migrating skyblock_stats table to add profile support...")
            cursor.execute("DROP TABLE skyblock_stats")
        elif "hour" not in columns:
            print("[*] Migrating skyblock_stats table to add hourly support...")
            cursor.execute("ALTER TABLE skyblock_stats RENAME TO skyblock_stats_old")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skyblock_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            profile_id TEXT,
            profile_name TEXT,
            is_selected INTEGER DEFAULT 0,
            date TEXT,
            hour TEXT,
            farming_xp REAL DEFAULT 0,
            mining_xp REAL DEFAULT 0,
            combat_xp REAL DEFAULT 0,
            foraging_xp REAL DEFAULT 0,
            fishing_xp REAL DEFAULT 0,
            enchanting_xp REAL DEFAULT 0,
            alchemy_xp REAL DEFAULT 0,
            taming_xp REAL DEFAULT 0,
            carpentry_xp REAL DEFAULT 0,
            catacombs_xp REAL DEFAULT 0,
            UNIQUE(uuid, profile_id, hour)
        )
    """)

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='skyblock_stats_old'"
    )
    if cursor.fetchone():
        cursor.execute("""
            INSERT OR IGNORE INTO skyblock_stats
                (uuid, profile_id, profile_name, is_selected, date, hour,
                 farming_xp, mining_xp, combat_xp, foraging_xp, fishing_xp,
                 enchanting_xp, alchemy_xp, taming_xp, carpentry_xp, catacombs_xp)
            SELECT uuid, profile_id, profile_name, is_selected, date, date || ' 00:00',
                   farming_xp, mining_xp, combat_xp, foraging_xp, fishing_xp,
                   enchanting_xp, alchemy_xp, taming_xp, carpentry_xp, catacombs_xp
            FROM skyblock_stats_old
        """)
        cursor.execute("DROP TABLE skyblock_stats_old")
        print("[*] Migration to hourly skyblock_stats complete.")
    migrate_daily_gexp(cursor)
    conn.commit()
    return conn


def migrate_daily_gexp(cursor):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_gexp'"
    )
    if cursor.fetchone():
        cursor.execute("""
            INSERT OR IGNORE INTO hourly_gexp (uuid, gexp, date, hour)
            SELECT uuid, daily_gexp, date, date || ' 23:00'
            FROM daily_gexp
        """)


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
                cursor.execute(
                    "INSERT INTO players (uuid, username) VALUES (?, ?)", (uuid, name)
                )
                new_names += 1
                print(f"[+] Discovered new player: {name}")
                time.sleep(0.5)  # Prevent Mojang API spam
    conn.commit()
    if new_names > 0:
        print(f"[*] Added {new_names} new names to the database.")


def save_to_db(conn, member_list):
    cursor = conn.cursor()
    now = datetime.now()
    today_key = now.strftime("%Y-%m-%d")
    hour_key = now.strftime("%Y-%m-%d %H:00")
    for member in member_list:
        uuid = member.get("uuid")
        exp_history = member.get("expHistory", {})
        today_exp = exp_history.get(today_key, 0)

        cursor.execute(
            """
            INSERT OR IGNORE INTO hourly_gexp (uuid, gexp, date, hour)
            VALUES (?, ?, ?, ?)
            """,
            (uuid, today_exp, today_key, hour_key),
        )
    conn.commit()
    print(f"[*] Logged hourly GEXP for {len(member_list)} members.")


def get_skyblock_profiles(uuid):
    """Returns a list of stats dicts, one per SkyBlock profile."""
    url = f"https://api.hypixel.net/v2/skyblock/profiles?uuid={uuid}"
    headers = {"Api-Key": API_KEY}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 429:
            print(f"Rate limited fetching SkyBlock for {uuid}. Sleeping 10s...")
            time.sleep(10)
            return []
        data = res.json()
    except Exception as e:
        print(f"Failed to fetch SkyBlock data for {uuid}: {e}")
        return []

    if not data.get("success") or not data.get("profiles"):
        return []

    results = []
    for profile in data["profiles"]:
        member = profile.get("members", {}).get(uuid, {})
        exp = member.get("player_data", {}).get("experience", {})
        cata_xp = (
            member.get("dungeons", {})
            .get("dungeon_types", {})
            .get("catacombs", {})
            .get("experience", 0)
            or 0
        )
        results.append(
            {
                "profile_id": profile.get("profile_id"),
                "profile_name": profile.get("cute_name", "Unknown"),
                "is_selected": 1 if profile.get("selected") else 0,
                "farming_xp": exp.get("SKILL_FARMING", 0) or 0,
                "mining_xp": exp.get("SKILL_MINING", 0) or 0,
                "combat_xp": exp.get("SKILL_COMBAT", 0) or 0,
                "foraging_xp": exp.get("SKILL_FORAGING", 0) or 0,
                "fishing_xp": exp.get("SKILL_FISHING", 0) or 0,
                "enchanting_xp": exp.get("SKILL_ENCHANTING", 0) or 0,
                "alchemy_xp": exp.get("SKILL_ALCHEMY", 0) or 0,
                "taming_xp": exp.get("SKILL_TAMING", 0) or 0,
                "carpentry_xp": exp.get("SKILL_CARPENTRY", 0) or 0,
                "catacombs_xp": cata_xp,
            }
        )
    return results


def save_skyblock_stats(conn, uuid, profiles, hour):
    cursor = conn.cursor()
    date = hour[:10]
    for p in profiles:
        cursor.execute(
            """
            INSERT OR IGNORE INTO skyblock_stats
                (uuid, profile_id, profile_name, is_selected, date, hour,
                 farming_xp, mining_xp, combat_xp, foraging_xp, fishing_xp,
                 enchanting_xp, alchemy_xp, taming_xp, carpentry_xp, catacombs_xp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid,
                p["profile_id"],
                p["profile_name"],
                p["is_selected"],
                date,
                hour,
                p["farming_xp"],
                p["mining_xp"],
                p["combat_xp"],
                p["foraging_xp"],
                p["fishing_xp"],
                p["enchanting_xp"],
                p["alchemy_xp"],
                p["taming_xp"],
                p["carpentry_xp"],
                p["catacombs_xp"],
            ),
        )
    conn.commit()


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

        print(f"[*] Fetching SkyBlock stats for {len(members)} members...")
        fetch_start = time.time()
        cursor = conn.cursor()
        hour_key = datetime.now().strftime("%Y-%m-%d %H:00")
        cursor.execute(
            "SELECT DISTINCT uuid FROM skyblock_stats WHERE hour = ?", (hour_key,)
        )
        skyblock_done = {row[0] for row in cursor.fetchall()}
        fetched = 0
        skipped = 0
        for member in members:
            uuid = member.get("uuid")
            if uuid in skyblock_done:
                skipped += 1
                continue
            profiles = get_skyblock_profiles(uuid)
            if profiles:
                save_skyblock_stats(conn, uuid, profiles, hour_key)
                fetched += 1
            else:
                print(f"[!] No SkyBlock data for {uuid}")
            time.sleep(0.5)
        elapsed = time.time() - fetch_start
        if skipped:
            print(
                f"[*] Skipped SkyBlock stats for {skipped} members already saved this hour."
            )
        print(
            f"[*] Saved SkyBlock stats for {fetched}/{len(members) - skipped} members in {elapsed:.1f}s."
        )

        conn.close()
    else:
        print("Error: Could not fetch data. Check API key/Guild name.")


if __name__ == "__main__":
    main()
