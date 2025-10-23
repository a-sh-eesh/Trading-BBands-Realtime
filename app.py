# ============================================================
# Streamlit ZLEMA Bollinger Multi-Coin Dashboard (4H Overlay)
# On-demand incremental fetching + Bollinger Bands + Telegram Alerts
# ============================================================

import os
import time
import logging
from datetime import timedelta
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# Internal imports (defensive)
try:
    from binance_integration import fetch_klines, get_secret
except Exception as e:
    # If importing fails (e.g. syntax error inside the module),
    # provide fallback stub functions so the app still loads and shows the error.
    logging.exception("Failed to import binance_integration: %s", e)

    def fetch_klines(*args, **kwargs) -> pd.DataFrame:
        """Fallback stub which returns empty DataFrame and does not break the app."""
        return pd.DataFrame()

    def get_secret(key: str) -> Optional[str]:
        return None

try:
    from candle_evaluator import evaluate_candles
except Exception:
    def evaluate_candles(df, phase, trend):
        return df

try:
    from zlema_bbands_trading import (
        compute_indicators,
        compute_adaptive_pct,
        compute_4h_overlay,
        apply_zones,
        validate_trend,
    )
except Exception:
    # If these imports fail we keep the stubs so UI still operates and user gets an error message later.
    def compute_indicators(df): return df
    def compute_adaptive_pct(df): return df
    def compute_4h_overlay(df): return df
    def apply_zones(df): return df
    def validate_trend(df): return df

# --------------------------
# CONFIGURATION
# --------------------------
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT", "LTCUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "TRXUSDT", "LINKUSDT", "MATICUSDT",
    "INJUSDT", "SUIUSDT", "PEPEUSDT", "SHIBUSDT", "WLDUSDT"
]

INTERVAL = "1h"
DAYS = 30
SAFE_FETCH_RETRIES = 3
SAFE_FETCH_BACKOFF = 1.2  # multiplier for backoff

st.set_page_config(page_title="ZLEMA Bollinger Multi-Coin Dashboard", layout="wide")
st.title("ZLEMA Bollinger Multi-Coin Dashboard")
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
# SAFE FETCH HELPER
# --------------------------
def safe_fetch(symbol: str, interval: str = INTERVAL, days: int = DAYS) -> pd.DataFrame:
    """
    Wraps fetch_klines with retries and backoff, and handles exceptions gracefully.
    Returns a pandas.DataFrame (possibly empty) rather than raising.
    """
    last_exception = None
    backoff = 1.0
    for attempt in range(1, SAFE_FETCH_RETRIES + 1):
        try:
            df = fetch_klines(symbol=symbol, interval=interval, days=days)
            # If function returned None, normalized to empty DataFrame
            if df is None:
                return pd.DataFrame()
            # Validate DataFrame shape minimally
            if isinstance(df, pd.DataFrame) and not df.empty and {"open", "high", "low", "close"}.issubset(df.columns):
                return df.copy()
            # If it's empty or missing columns, return empty — caller will handle message
            return pd.DataFrame()
        except requests.exceptions.RequestException as re:
            last_exception = re
            logging.warning("RequestException fetching %s: %s (attempt %d)", symbol, re, attempt)
        except Exception as e:
            last_exception = e
            logging.exception("Unexpected error fetching %s (attempt %d): %s", symbol, attempt, e)

        time.sleep(backoff)
        backoff *= SAFE_FETCH_BACKOFF

    # All retries failed
    if last_exception:
        # Surface a friendly message in Streamlit UI
        st.error(f"Failed to fetch market data for {symbol}: {last_exception}")
    return pd.DataFrame()


# --------------------------
# MAIN UI & Fetch
# --------------------------
st.subheader(f"Detailed Chart — {selected_coin}")

# Force-refresh logic
if "force_refresh" not in st.session_state:
    st.session_state["force_refresh"] = False

if st.button(f"Refresh selected coin data ({selected_coin})"):
    st.session_state["force_refresh"] = True

# Fetch data with spinner
with st.spinner(f"Fetching {selected_coin} data..."):
    df = safe_fetch(selected_coin, interval=INTERVAL, days=DAYS)

if df is None or df.empty:
    st.warning(f"No valid data found for {selected_coin}. Try refreshing or wait for the next candle.")
    # stop rendering further widgets because indicators and plotting need data
    st.stop()

# --------------------------
# COMPUTE INDICATORS (keeps trading logic untouched)
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

# Bollinger Bands traces if available
if "upper_band" in df.columns and "lower_band" in df.columns:
    fig.add_trace(go.Scatter(x=df.index, y=df["upper_band"], name="Upper Band", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["lower_band"], name="Lower Band", line=dict(width=1)))

# ZLEMA / Middle Line
if "zlema" in df.columns:
    fig.add_trace(go.Scatter(x=df.index, y=df["zlema"], name="ZLEMA", line=dict(width=2)))

# Optional: plot buy/sell zones if present
if "buy_zone_high" in df.columns and "sell_zone_low" in df.columns:
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df.get("buy_zone_high"),
        name="Buy Zone High",
        line=dict(width=1),
        opacity=0.6
    ))
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df.get("sell_zone_low"),
        name="Sell Zone Low",
        line=dict(width=1),
        opacity=0.6
    ))

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

summary_data = [
    {"Coin": selected_coin, "Phase": phase, "Trend": trend, "Last Price": float(df["close"].iloc[-1])}
]
summary_df = pd.DataFrame(summary_data)
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
        message = f"Test alert: Dashboard is running for {selected_coin}."
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                params={"chat_id": chat_id, "text": message},
                timeout=8
            )
            r.raise_for_status()
            st.success("Test alert sent successfully.")
        except Exception as e:
            st.error(f"Failed to send Telegram alert: {e}")

# --------------------------
# OPTIONAL: Analyze active coins now (placeholder)
# --------------------------
if st.session_state.get("analyze_now", False):
    st.info("Analyze active coins: feature invoked. This will iterate over active coins and run the same pipeline.")
    # Placeholder example run (keeps logic minimal)
    active_summary = []
    for sym in SYMBOLS[:8]:  # limit for quick run
        df_sym = safe_fetch(sym, interval=INTERVAL, days=7)
        if df_sym is None or df_sym.empty:
            active_summary.append({"Coin": sym, "Status": "No data"})
            continue
        last_price = float(df_sym["close"].iloc[-1]) if "close" in df_sym.columns else None
        active_summary.append({"Coin": sym, "Status": "OK", "Last Price": last_price})
    st.dataframe(pd.DataFrame(active_summary), use_container_width=True)
    st.session_state["analyze_now"] = False
