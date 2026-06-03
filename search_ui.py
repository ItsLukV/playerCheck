import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta

st.set_page_config(page_title="Guild Analytics", layout="wide")
st.title("📊 Guild GEXP Totals")

def get_connection():
    db_path = os.getenv("DB_NAME", "/app/data/guild_data.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS daily_gexp (id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, daily_gexp INTEGER, date TEXT, UNIQUE(uuid, date))')
    cursor.execute('CREATE TABLE IF NOT EXISTS hourly_gexp (id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, gexp INTEGER, date TEXT, hour TEXT, UNIQUE(uuid, hour))')
    cursor.execute('CREATE TABLE IF NOT EXISTS players (uuid TEXT PRIMARY KEY, username TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS skyblock_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, profile_id TEXT, profile_name TEXT,
        is_selected INTEGER DEFAULT 0, date TEXT, hour TEXT,
        farming_xp REAL DEFAULT 0, mining_xp REAL DEFAULT 0, combat_xp REAL DEFAULT 0,
        foraging_xp REAL DEFAULT 0, fishing_xp REAL DEFAULT 0, enchanting_xp REAL DEFAULT 0,
        alchemy_xp REAL DEFAULT 0, taming_xp REAL DEFAULT 0, carpentry_xp REAL DEFAULT 0,
        catacombs_xp REAL DEFAULT 0, UNIQUE(uuid, profile_id, hour))''')
    cursor.execute("""
        INSERT OR IGNORE INTO hourly_gexp (uuid, gexp, date, hour)
        SELECT uuid, daily_gexp, date, date || ' 23:00'
        FROM daily_gexp
    """)
    conn.commit()
    return conn

def get_summary_data(days):
    conn = get_connection()
    cutoff_str = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    query = """
        WITH daily_totals AS (
            SELECT uuid, date, MAX(gexp) as daily_gexp
            FROM hourly_gexp
            WHERE date >= ?
            GROUP BY uuid, date
        )
        SELECT
            COALESCE(p.username, d.uuid) as Player,
            SUM(d.daily_gexp) as Total_GEXP,
            COUNT(d.date) as Days_Active
        FROM daily_totals d
        LEFT JOIN players p ON d.uuid = p.uuid
        GROUP BY d.uuid
        ORDER BY Total_GEXP DESC
    """
    df = pd.read_sql_query(query, conn, params=(cutoff_str,))
    conn.close()
    return df

SKILL_COLUMNS = [
    "farming_xp", "mining_xp", "combat_xp", "foraging_xp", "fishing_xp",
    "enchanting_xp", "alchemy_xp", "taming_xp", "carpentry_xp", "catacombs_xp",
]

def get_skyblock_leaderboard(stat_col):
    conn = get_connection()
    query = f"""
        SELECT
            COALESCE(p.username, s.uuid) as Player,
            s.profile_name as Profile,
            s.{stat_col} as XP,
            s.hour as Snapshot
        FROM skyblock_stats s
        LEFT JOIN players p ON s.uuid = p.uuid
        WHERE s.is_selected = 1
          AND s.hour = (
              SELECT MAX(hour) FROM skyblock_stats
              WHERE uuid = s.uuid AND is_selected = 1
          )
        ORDER BY s.{stat_col} DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_skyblock_event(stat_col, start_date, end_date):
    conn = get_connection()
    query = f"""
        SELECT
            COALESCE(p.username, s_end.uuid) as Player,
            s_end.profile_name as Profile,
            s_end.{stat_col} - COALESCE(s_start.{stat_col}, 0) as XP_Gained,
            s_end.{stat_col} as End_XP,
            COALESCE(s_start.{stat_col}, 0) as Start_XP
        FROM skyblock_stats s_end
        LEFT JOIN skyblock_stats s_start
            ON s_start.uuid = s_end.uuid
            AND s_start.profile_id = s_end.profile_id
            AND s_start.hour = (
                SELECT MIN(hour) FROM skyblock_stats
                WHERE uuid = s_end.uuid AND profile_id = s_end.profile_id AND date = ?
            )
        LEFT JOIN players p ON s_end.uuid = p.uuid
        WHERE s_end.is_selected = 1
          AND s_end.hour = (
              SELECT MAX(hour) FROM skyblock_stats
              WHERE uuid = s_end.uuid AND profile_id = s_end.profile_id AND date = ?
          )
        ORDER BY XP_Gained DESC
    """
    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()
    return df

# --- GEXP Tabs ---
tab1, tab2, tab3 = st.tabs(["7 Days", "14 Days", "31 Days"])

with tab1:
    st.header("Last 7 Days")
    st.dataframe(get_summary_data(7), use_container_width=True, hide_index=True)

with tab2:
    st.header("Last 14 Days")
    st.dataframe(get_summary_data(14), use_container_width=True, hide_index=True)

with tab3:
    st.header("Last 31 Days")
    st.dataframe(get_summary_data(31), use_container_width=True, hide_index=True)

# --- SkyBlock Section ---
st.divider()
st.header("⚔️ SkyBlock Stats")

sb_tab1, sb_tab2 = st.tabs(["Leaderboard", "Event Tracker"])

with sb_tab1:
    stat_label = st.selectbox(
        "Stat",
        options=SKILL_COLUMNS,
        format_func=lambda x: x.replace("_xp", "").capitalize(),
        key="lb_stat",
    )
    lb_df = get_skyblock_leaderboard(stat_label)
    if lb_df.empty:
        st.info("No SkyBlock data collected yet.")
    else:
        st.dataframe(lb_df, use_container_width=True, hide_index=True)

with sb_tab2:
    st.caption("Compare XP gained between two snapshot dates.")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start date", value=datetime.now() - timedelta(days=7), key="ev_start")
    with col2:
        end_date = st.date_input("End date", value=datetime.now(), key="ev_end")

    event_stat = st.selectbox(
        "Stat",
        options=SKILL_COLUMNS,
        format_func=lambda x: x.replace("_xp", "").capitalize(),
        key="ev_stat",
    )

    if st.button("Calculate Gains"):
        ev_df = get_skyblock_event(event_stat, str(start_date), str(end_date))
        if ev_df.empty:
            st.warning("No data found for that date range.")
        else:
            st.dataframe(ev_df, use_container_width=True, hide_index=True)

# --- Individual Search ---
st.divider()
st.header("🔍 Player Deep Dive")
search_input = st.text_input("Enter Username or UUID").strip()

if search_input:
    conn = get_connection()

    gexp_query = """
        SELECT h.hour, h.gexp, h.date, COALESCE(p.username, h.uuid) as name
        FROM hourly_gexp h
        LEFT JOIN players p ON h.uuid = p.uuid
        WHERE h.uuid LIKE ? OR p.username LIKE ?
        ORDER BY h.hour DESC
    """
    user_df = pd.read_sql_query(gexp_query, conn, params=(f"%{search_input}%", f"%{search_input}%"))

    sb_query = """
        SELECT s.hour as Hour, s.profile_name as Profile, s.is_selected as Active,
               s.farming_xp, s.mining_xp, s.combat_xp, s.foraging_xp,
               s.fishing_xp, s.enchanting_xp, s.alchemy_xp, s.taming_xp,
               s.carpentry_xp, s.catacombs_xp
        FROM skyblock_stats s
        LEFT JOIN players p ON s.uuid = p.uuid
        WHERE s.uuid LIKE ? OR p.username LIKE ?
        ORDER BY s.hour DESC, s.is_selected DESC
    """
    sb_df = pd.read_sql_query(sb_query, conn, params=(f"%{search_input}%", f"%{search_input}%"))
    conn.close()

    if not user_df.empty:
        player_name = user_df['name'].iloc[0]
        st.success(f"History for {player_name}")

        st.subheader("GEXP")
        user_df['hour'] = pd.to_datetime(user_df['hour'])
        user_df = user_df.sort_values('hour')
        user_df['hourly_gain'] = user_df.groupby('date')['gexp'].diff()
        user_df['hourly_gain'] = user_df['hourly_gain'].fillna(user_df['gexp'])
        chart_data = user_df.set_index('hour').sort_index()
        st.line_chart(chart_data['gexp'])
        st.dataframe(user_df[['hour', 'gexp', 'hourly_gain']], use_container_width=True, hide_index=True)
    else:
        st.error("No data found.")

    if not sb_df.empty:
        st.subheader("SkyBlock XP History")
        profiles = sb_df['Profile'].unique().tolist()
        selected_profile = st.selectbox("Profile", options=profiles, key="dive_profile")
        filtered = sb_df[sb_df['Profile'] == selected_profile].drop(columns=['Profile', 'Active'])
        st.dataframe(filtered, use_container_width=True, hide_index=True)
