# ============================================================
# Streamlit ZLEMA Bollinger Multi-Coin Dashboard (4H Overlay)
# On-demand incremental fetching + Bollinger Bands + Telegram Alerts
# ============================================================

import os
import time
import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta

# Internal imports
from binance_integration import fetch_klines, get_secret
from candle_evaluator import evaluate_candles
from zlema_bbands_trading import (
    compute_indicators,
    compute_adaptive_pct,
    compute_4h_overlay,
    apply_zones,
    validate_trend,
)

# --------------------------
# CONFIGURATION
# --------------------------
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT", "LTCUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "TRXUSDT", "LINKUSDT", "MATICUSDT",
    "INJUSDT", "SUIUSDT", "TIAUSDT", "PEPEUSDT", "SHIBUSDT", "WLDUSDT"
]

INTERVAL = "1h"
DAYS = 30

st.set_page_config(page_title="ZLEMA Bollinger Multi-Coin Dashboard", layout="wide")
st.title("📈 ZLEMA Bollinger Multi-Coin Dashboard")
st.caption("On-demand incremental fetching with Bollinger Bands, 4H Overlay, and Telegram Alerts.")

# --------------------------
# SIDEBAR SETTINGS
# --------------------------
with st.sidebar:
    st.header("Control Panel")
    selected_coin = st.selectbox("Select Coin to Configure", SYMBOLS, index=0)

    st.subheader(f"Settings — {selected_coin}")
    phase = st.selectbox("Phase", ["Uptrend", "Downtrend", "Sideways"], index=2)
    trend = st.selectbox("Trend", ["Uptrend", "Downtrend", "Sideways"], index=2)
    monitor_active = st.checkbox("Monitor this coin (activate for scanning)")

    st.divider()
    if st.button("Analyze Active Coins Now"):
        st.session_state["analyze_now"] = True
    if st.button("Test Telegram Alert"):
        st.session_state["test_alert"] = True

    st.caption("Activate only coins you want monitored.")

# --------------------------
# FETCH AND PROCESS DATA
# --------------------------
st.subheader(f"Detailed Chart — {selected_coin}")

if st.button(f"🔄 Refresh selected coin data ({selected_coin})"):
    st.session_state["force_refresh"] = True

# Handle caching and re-fetching logic
refresh_flag = st.session_state.get("force_refresh", False)

with st.spinner(f"Fetching {selected_coin} data from Binance..."):
    df = fetch_klines(symbol=selected_coin, interval=INTERVAL, days=DAYS)

if df is None or df.empty:
    st.warning(f"No valid data found for {selected_coin}. Try refreshing or wait for the next candle.")
    st.stop()

# --------------------------
# COMPUTE INDICATORS
# --------------------------
try:
    df = compute_indicators(df)
    df = compute_adaptive_pct(df)
    df = compute_4h_overlay(df)
    df = apply_zones(df)
    df = evaluate_candles(df, phase, trend)
    df = validate_trend(df)
except Exception as e:
    st.error(f"Indicator computation failed: {e}")
    st.stop()

# --------------------------
# PLOTLY CHART
# --------------------------
fig = go.Figure()

# Candlesticks
fig.add_trace(
    go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
    )
)

# Bollinger Bands
if "upper_band" in df.columns and "lower_band" in df.columns:
    fig.add_trace(go.Scatter(x=df.index, y=df["upper_band"], name="Upper Band", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["lower_band"], name="Lower Band", line=dict(width=1)))

# ZLEMA / Middle Line
if "zlema" in df.columns:
    fig.add_trace(go.Scatter(x=df.index, y=df["zlema"], name="ZLEMA", line=dict(width=2)))

fig.update_layout(
    title=f"{selected_coin} — ZLEMA Bollinger Overlay",
    xaxis_title="Time",
    yaxis_title="Price (USDT)",
    xaxis_rangeslider_visible=False,
    template="plotly_dark",
    height=600,
)

st.plotly_chart(fig, use_container_width=True)

# --------------------------
# SUMMARY TABLE
# --------------------------
st.subheader("Summary Table (Active Coins)")

# Example placeholder logic (you can plug your monitor logic here)
summary_data = [
    {"Coin": selected_coin, "Phase": phase, "Trend": trend, "Last Price": round(df["close"].iloc[-1], 4)}
]
summary_df = pd.DataFrame(summary_data)

if summary_df.empty:
    st.info("No active coin results to display.")
else:
    st.dataframe(summary_df, use_container_width=True)

# --------------------------
# TELEGRAM ALERT TEST
# --------------------------
if st.session_state.get("test_alert", False):
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        st.warning("Telegram credentials not found in Streamlit secrets.")
    else:
        message = f"✅ Test alert: Dashboard is running successfully for {selected_coin}."
        try:
            requests.get(f"https://api.telegram.org/bot{bot_token}/sendMessage", params={"chat_id": chat_id, "text": message})
            st.success("Test alert sent successfully.")
        except Exception as e:
            st.error(f"Failed to send Telegram alert: {e}")
