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
    # Ensure tables exist to prevent query crashes
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS daily_gexp (id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, daily_gexp INTEGER, date TEXT, UNIQUE(uuid, date))')
    cursor.execute('CREATE TABLE IF NOT EXISTS players (uuid TEXT PRIMARY KEY, username TEXT)')
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

# --- UI Layout ---
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

# --- Individual Search ---
st.divider()
st.header("🔍 Player Deep Dive")
search_input = st.text_input("Enter Username or UUID").strip()

if search_input:
    conn = get_connection()
    query = """
        SELECT g.date, g.daily_gexp, COALESCE(p.username, g.uuid) as name
        FROM daily_gexp g
        LEFT JOIN players p ON g.uuid = p.uuid
        WHERE g.uuid LIKE ? OR p.username LIKE ?
        ORDER BY g.date DESC
    """
    user_df = pd.read_sql_query(query, conn, params=(f"%{search_input}%", f"%{search_input}%"))
    conn.close()

    if not user_df.empty:
        player_name = user_df['name'].iloc[0]
        st.success(f"History for {player_name}")
        chart_data = user_df.set_index('date').sort_index()
        st.line_chart(chart_data['daily_gexp'])
        st.dataframe(user_df[['date', 'daily_gexp']], use_container_width=True, hide_index=True)
    else:
        st.error("No data found.")
