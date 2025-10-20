# ============================================================
# Streamlit Dashboard — ZLEMA Bollinger Trading System
# Live Binance Data (1-hour refresh, Cloud + Mobile Ready)
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.graph_objects as go
import time

# Auto-refresh every 1 hour
if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = time.time()

if time.time() - st.session_state["last_refresh"] > 3600:  # 1 hour in seconds
    st.session_state["last_refresh"] = time.time()
    st.rerun()


# Internal imports
from binance_integration import fetch_klines
from candle_evaluator import evaluate_candles
from zlema_bbands_trading import (
    compute_indicators,
    compute_adaptive_pct,
    compute_6h_overlay,
    apply_zones,
    validate_trend,
)

# ------------------------------------------------------------
# Streamlit Configuration
# ------------------------------------------------------------
st.set_page_config(page_title="ZLEMA Bollinger Dashboard", layout="wide")
st.title("ZLEMA Bollinger Trading Dashboard")
st.caption("Live Binance Data — Adaptive PCT + 6H Overlay + Cloud Ready")

# Auto-refresh every 1 hour (3600 * 1000 ms)
interval_minutes = 60
st_autorefresh(interval=interval_minutes * 60 * 1000, key="hourly_refresh")

st.sidebar.markdown(f"Auto-refresh every {interval_minutes} minutes")

# ------------------------------------------------------------
# Sidebar Inputs
# ------------------------------------------------------------
st.sidebar.header("Control Panel")
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LTCUSDT"]
symbol = st.sidebar.selectbox("Select Symbol", SYMBOLS, index=0)
phase = st.sidebar.selectbox("Market Phase", ["TTR", "BTR", "Sideways"])
trend = st.sidebar.selectbox("Market Trend", ["Bullish", "Bearish", "Sideways"])
run_button = st.sidebar.button("Run / Refresh Now")

# ------------------------------------------------------------
# Cache to store symbol data
# ------------------------------------------------------------
if "symbol_data" not in st.session_state:
    st.session_state["symbol_data"] = {}

# ------------------------------------------------------------
# Fetch and update Binance data
# ------------------------------------------------------------
def get_symbol_data(symbol):
    cache = st.session_state["symbol_data"]
    now = pd.Timestamp.utcnow()

    if symbol not in cache or cache[symbol].empty:
        df = fetch_klines(symbol, interval="1h", days=30)
        cache[symbol] = df
        return df, True
    else:
        df_old = cache[symbol]
        last_time = df_old["open_time"].max()
        start_time = last_time + pd.Timedelta(hours=1)
        df_new = fetch_klines(symbol, interval="1h", start_time=start_time, end_time=now)
        if not df_new.empty:
            df = pd.concat([df_old, df_new]).drop_duplicates(subset=["open_time"]).sort_values("open_time")
            df = df[df["open_time"] >= (now - pd.Timedelta(days=30))]
            cache[symbol] = df
            return df, True
        else:
            return df_old, False

# ------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------
if run_button:
    with st.spinner(f"Fetching {symbol} data from Binance..."):
        df, updated = get_symbol_data(symbol)
        if df.empty:
            st.error("No data available.")
        else:
            trend = validate_trend(trend)

            # Indicator pipeline
            df = compute_indicators(df)
            df = compute_adaptive_pct(df)
            df = compute_6h_overlay(df)
            df = apply_zones(df, phase, trend)
            df = evaluate_candles(df, phase, trend)

            latest = df.iloc[-1]

            st.success(f"{symbol} updated successfully.")
            st.write(f"Last Updated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

            col1, col2, col3 = st.columns(3)
            col1.metric("Signal", latest.get("entry_signal", "N/A"))
            col2.metric("Price", f"{latest['close']:.2f} USDT")
            col3.metric("ZLEMA", f"{latest['zlema']:.2f}")

            # ----------------------------------------------------
            # Chart Setup
            # ----------------------------------------------------
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df["open_time"],
                open=df["open"], high=df["high"], low=df["low"], close=df["close"],
                name="Candles",
                increasing_line_color="green",
                decreasing_line_color="red",
            ))

            # ZLEMA Line
            fig.add_trace(go.Scatter(
                x=df["open_time"],
                y=df["zlema"],
                mode="lines",
                name="ZLEMA",
                line=dict(color="orange", width=1.6)
            ))

            # --- Hide buy/sell zones if TTR phase ---
            if phase != "TTR":
                if "buy_zone_lower" in df.columns and "buy_zone_upper" in df.columns:
                    fig.add_trace(go.Scatter(
                        x=pd.concat([df["open_time"], df["open_time"][::-1]]),
                        y=pd.concat([df["buy_zone_lower"], df["buy_zone_upper"][::-1]]),
                        fill="toself", fillcolor="rgba(0,255,0,0.1)", line=dict(width=0),
                        name="Buy Zone"
                    ))
                if "sell_zone_lower" in df.columns and "sell_zone_upper" in df.columns:
                    fig.add_trace(go.Scatter(
                        x=pd.concat([df["open_time"], df["open_time"][::-1]]),
                        y=pd.concat([df["sell_zone_lower"], df["sell_zone_upper"][::-1]]),
                        fill="toself", fillcolor="rgba(255,0,0,0.1)", line=dict(width=0),
                        name="Sell Zone"
                    ))

            # --- 6H Overlay (always visible) ---
            if all(x in df.columns for x in ["zlema_6h", "upper_band_6h", "lower_band_6h"]):
                fig.add_trace(go.Scatter(
                    x=pd.concat([df["open_time"], df["open_time"][::-1]]),
                    y=pd.concat([df["upper_band_6h"], df["lower_band_6h"][::-1]]),
                    fill="toself", fillcolor="rgba(138,43,226,0.08)", line=dict(width=0),
                    name="6H Range"
                ))
                fig.add_trace(go.Scatter(
                    x=df["open_time"],
                    y=df["zlema_6h"],
                    mode="lines",
                    line=dict(color="violet", width=1.2),
                    name="ZLEMA 6H"
                ))

            # --- Entry Markers ---
            if "entry_signal" in df.columns:
                buys = df[df["entry_signal"] == "BUY"]
                sells = df[df["entry_signal"] == "SELL"]
                fig.add_trace(go.Scatter(
                    x=buys["open_time"], y=buys["low"] * 0.995, mode="markers",
                    marker=dict(symbol="triangle-up", color="lime", size=10), name="BUY"
                ))
                fig.add_trace(go.Scatter(
                    x=sells["open_time"], y=sells["high"] * 1.005, mode="markers",
                    marker=dict(symbol="triangle-down", color="red", size=10), name="SELL"
                ))

            # --- Chart Layout ---
            fig.update_layout(
                template="plotly_dark",
                height=620,
                hovermode="x unified",
                xaxis=dict(rangeslider_visible=False),
                yaxis=dict(showspikes=True, spikecolor="gray", spikemode="across"),
                legend=dict(x=0.01, y=0.99, bgcolor="rgba(0,0,0,0)")
            )

            st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Select symbol, phase, and trend, then click Run / Refresh Now.")

st.markdown("---")
st.caption("ZLEMA Bollinger System © 2025 — Hosted on Streamlit Cloud")
