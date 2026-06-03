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
    cursor.execute('CREATE TABLE IF NOT EXISTS players (uuid TEXT PRIMARY KEY, username TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS skyblock_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, profile_id TEXT, profile_name TEXT,
        is_selected INTEGER DEFAULT 0, date TEXT,
        farming_xp REAL DEFAULT 0, mining_xp REAL DEFAULT 0, combat_xp REAL DEFAULT 0,
        foraging_xp REAL DEFAULT 0, fishing_xp REAL DEFAULT 0, enchanting_xp REAL DEFAULT 0,
        alchemy_xp REAL DEFAULT 0, taming_xp REAL DEFAULT 0, carpentry_xp REAL DEFAULT 0,
        catacombs_xp REAL DEFAULT 0, UNIQUE(uuid, profile_id, date))''')
    conn.commit()
    return conn

def get_summary_data(days):
    conn = get_connection()
    cutoff_str = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    query = """
        SELECT
            COALESCE(p.username, g.uuid) as Player,
            SUM(g.daily_gexp) as Total_GEXP,
            COUNT(g.date) as Days_Active
        FROM daily_gexp g
        LEFT JOIN players p ON g.uuid = p.uuid
        WHERE g.date >= ?
        GROUP BY g.uuid
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
    # Most recent snapshot of each player's selected profile
    query = f"""
        SELECT
            COALESCE(p.username, s.uuid) as Player,
            s.profile_name as Profile,
            s.{stat_col} as XP,
            s.date as Snapshot
        FROM skyblock_stats s
        LEFT JOIN players p ON s.uuid = p.uuid
        WHERE s.is_selected = 1
          AND s.date = (
              SELECT MAX(date) FROM skyblock_stats
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
            AND s_start.date = ?
        LEFT JOIN players p ON s_end.uuid = p.uuid
        WHERE s_end.is_selected = 1
          AND s_end.date = ?
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
        SELECT g.date, g.daily_gexp, COALESCE(p.username, g.uuid) as name
        FROM daily_gexp g
        LEFT JOIN players p ON g.uuid = p.uuid
        WHERE g.uuid LIKE ? OR p.username LIKE ?
        ORDER BY g.date DESC
    """
    user_df = pd.read_sql_query(gexp_query, conn, params=(f"%{search_input}%", f"%{search_input}%"))

    sb_query = """
        SELECT s.date, s.profile_name as Profile, s.is_selected as Active,
               s.farming_xp, s.mining_xp, s.combat_xp, s.foraging_xp,
               s.fishing_xp, s.enchanting_xp, s.alchemy_xp, s.taming_xp,
               s.carpentry_xp, s.catacombs_xp
        FROM skyblock_stats s
        LEFT JOIN players p ON s.uuid = p.uuid
        WHERE s.uuid LIKE ? OR p.username LIKE ?
        ORDER BY s.date DESC, s.is_selected DESC
    """
    sb_df = pd.read_sql_query(sb_query, conn, params=(f"%{search_input}%", f"%{search_input}%"))
    conn.close()

    if not user_df.empty:
        player_name = user_df['name'].iloc[0]
        st.success(f"History for {player_name}")

        st.subheader("GEXP")
        chart_data = user_df.set_index('date').sort_index()
        st.line_chart(chart_data['daily_gexp'])
        st.dataframe(user_df[['date', 'daily_gexp']], use_container_width=True, hide_index=True)
    else:
        st.error("No data found.")

    if not sb_df.empty:
        st.subheader("SkyBlock XP History")
        profiles = sb_df['Profile'].unique().tolist()
        selected_profile = st.selectbox("Profile", options=profiles, key="dive_profile")
        filtered = sb_df[sb_df['Profile'] == selected_profile].drop(columns=['Profile', 'Active'])
        st.dataframe(filtered, use_container_width=True, hide_index=True)
