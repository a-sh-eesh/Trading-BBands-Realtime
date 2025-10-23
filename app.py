# ============================================================
# Streamlit ZLEMA Bollinger Multi-Coin Dashboard (4H Overlay)
# On-demand incremental fetch + Telegram Alerts + Bollinger + 4H Bands
# ============================================================

import os
import time
import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta

# Internal imports
from binance_integration import fetch_klines, fetch_klines_incremental, get_secret
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
    "APTUSDT", "ARUSDT", "ARBUSDT", "ANKRUSDT", "ASTERUSDT", "BTCUSDT",
    "BCHUSDT", "BNBUSDT", "ETHUSDT", "ENSUSDT", "ENAUSDT", "INJUSDT",
    "JUPUSDT", "LTCUSDT", "LPTUSDT", "LDOUSDT", "LINEAUSDT", "PUMPUSDT",
    "PENDLEUSDT", "SAGAUSDT", "SEIUSDT", "STXUSDT", "TIAUSDT", "TONUSDT",
    "TAOUSDT", "WLDUSDT", "XRPUSDT", "ZETAUSDT", "AIUSDT", "JASMYUSDT",
    "GRTUSDT", "MINAUSDT", "FETUSDT", "ICPUSDT",
    "MELANIAUSDT", "TRUMPUSDT", "WIFUSDT", "BONKUSDT"
]

st.set_page_config(page_title="ZLEMA Bollinger Multi-Coin Dashboard", layout="wide")

# --------------------------
# Sidebar Controls
# --------------------------
st.sidebar.header("Control Panel")

selected_symbol = st.sidebar.selectbox("Select Coin to Configure", SYMBOLS, index=5)
phase = st.sidebar.selectbox("Phase", ["Sideways", "Bullish", "Bearish"], index=0)
trend = st.sidebar.selectbox("Trend", ["Sideways", "Uptrend", "Downtrend"], index=0)

monitor_mode = st.sidebar.checkbox("Monitor this coin (activate for scanning)")

st.sidebar.button("Analyze Active Coins Now")
st.sidebar.button("Test Telegram Alert")

# --------------------------
# MAIN DASHBOARD
# --------------------------
st.title("ZLEMA Bollinger Multi-Coin Dashboard")
st.markdown("On-demand incremental fetching with Bollinger Bands, 4H Overlay, and Telegram Alerts.")

# Initialize cache
if "data_cache" not in st.session_state:
    st.session_state["data_cache"] = {}

# --------------------------
# Refresh Data
# --------------------------
if st.button(f"Refresh selected coin data ({selected_symbol})"):
    with st.spinner(f"Fetching {selected_symbol} data from Binance..."):

        df_old = st.session_state["data_cache"].get(selected_symbol)

        if df_old is None or df_old.empty:
            df = fetch_klines(selected_symbol, interval="1h", days=30)
        else:
            last_time = df_old["open_time"].max()
            new_df = fetch_klines_incremental(selected_symbol, interval="1h", since=last_time)
            df = pd.concat([df_old, new_df]).drop_duplicates(subset=["open_time"]).reset_index(drop=True)

        # Retry once if Binance returned nothing
        if df.empty:
            time.sleep(3)
            df = fetch_klines(selected_symbol, interval="1h", days=30)

        st.session_state["data_cache"][selected_symbol] = df

# --------------------------
# Display Chart
# --------------------------
df = st.session_state["data_cache"].get(selected_symbol)

if df is None or df.empty:
    st.warning(f"No valid data found for {selected_symbol}. Try refreshing or wait for the next candle.")
else:
    st.success(f"Loaded {len(df)} candles for {selected_symbol}")

    df = compute_indicators(df)
    df = apply_zones(df)
    df = compute_4h_overlay(df)
    df = compute_adaptive_pct(df)

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["open_time"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name=selected_symbol
    ))

    fig.update_layout(
        title=f"{selected_symbol} — 1H Candles with ZLEMA Bands",
        xaxis_title="Time",
        yaxis_title="Price (USDT)",
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=600,
    )

    st.plotly_chart(fig, use_container_width=True)

# --------------------------
# Summary Table
# --------------------------
st.subheader("Summary Table (Active Coins)")
st.info("No active coin results to display yet.")
